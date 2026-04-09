import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from webly.chatbot.context_builder_agent import ContextBuilderAgent
from webly.pipeline.query_context import QueryContextTools
from webly.pipeline.query_retriever import QueryRetriever
from webly.pipeline.query_response_composer import QueryResponseComposer
from webly.query_result import QueryResult, SourceRef


class QueryPipeline:
    """
    Retrieval with:
    - Initial semantic search
    - Optional LLM query rewrite + second search
    - Graph-aware expansion (backlinks via anchor_text, optional section/sibling expansion)
    - Re-ranking + length trimming (dynamic context budget when possible)
    - Sectioned context assembly
    - NEW: Iterative multi-hop retrieval with answerability checks and graceful fallback

    Public API is unchanged. Constructor signature and .query(question, retry_on_empty) remain the same.
    """

    def __init__(
        self,
        chat_agent,
        recrawl_fn: Optional[Callable] = None,
        enable_rewrite: bool = True,
        enable_graph_expansion: bool = True,
        enable_section_expansion: bool = True,
        enable_hybrid: bool = True,
        enable_answerability_check: bool = True,
        allow_best_effort: bool = True,
        max_context_chars: int = 12000,
        max_results_to_consider: int = 30,  # across all passes
        top_k_first_pass: Optional[int] = None,  # default to chat_agent.top_k if None
        top_k_second_pass: Optional[int] = None,  # for rewrite/expansion passes
        anchor_boost: float = 0.10,  # boost for results sourced via anchor/backlink expansion
        section_boost: float = 0.05,  # mild boost for same-section/sibling expansion
        debug: bool = False,
        retrieval_mode: str = "builder",
        builder_max_rounds: int = 1,
        score_threshold: float = 0.0,
    ):
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn

        self.enable_rewrite = enable_rewrite
        self.enable_graph_expansion = enable_graph_expansion
        self.enable_section_expansion = enable_section_expansion
        self.enable_hybrid = enable_hybrid
        self.enable_answerability_check = enable_answerability_check
        self.allow_best_effort = allow_best_effort

        self.max_context_chars = max_context_chars
        self.top_k_first_pass = top_k_first_pass or max(self.chat_agent.top_k, 8)
        self.top_k_second_pass = top_k_second_pass or max(self.chat_agent.top_k, 10)
        self.max_results_to_consider = max(max_results_to_consider, 40)

        self.anchor_boost = anchor_boost
        self.section_boost = section_boost
        self.debug = debug
        self.retrieval_mode = retrieval_mode
        self.builder_max_rounds = max(0, int(builder_max_rounds))
        self.score_threshold = max(0.0, float(score_threshold or 0.0))
        self.context_builder = ContextBuilderAgent(planner_llm=getattr(self.chat_agent, "chatbot", None))
        self.logger = logging.getLogger(self.__class__.__name__)

        self.retriever = QueryRetriever(
            chat_agent=self.chat_agent,
            logger=self.logger,
            enable_hybrid=self.enable_hybrid,
            anchor_boost=self.anchor_boost,
            section_boost=self.section_boost,
            score_threshold=self.score_threshold,
        )
        self.context_tools = QueryContextTools()
        self.response_composer = QueryResponseComposer(
            chat_agent=self.chat_agent,
            context_tools=self.context_tools,
            max_context_chars=self.max_context_chars,
        )
        self._last_used_sources: List[Dict[str, str]] = []
        self._last_supported: bool = False
        self._last_trace: Dict[str, Any] = {}

    # ---------------- Core entrypoint ----------------
    def query(self, question: str, retry_on_empty: bool = False, memory_context: str = "") -> str:
        return self.query_result(question, retry_on_empty=retry_on_empty, memory_context=memory_context).answer

    def query_result(self, question: str, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        self._last_supported = False
        self._last_trace = {}
        self._last_used_sources = []
        if (self.retrieval_mode or "classic").lower() == "builder":
            return self._query_builder(question, retry_on_empty=retry_on_empty, memory_context=memory_context)

        if self.debug:
            self.logger.debug(f"User query: {question}")
            if memory_context:
                self.logger.debug(f"Memory context length: {len(memory_context)} chars")

        question_for_search = f"{memory_context}\n{question}".strip() if memory_context else question
        question_for_answer = f"{memory_context}\nUser: {question}".strip() if memory_context else question

        # === Pass 1: initial search ===
        initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial")
        if self.debug:
            self.logger.debug(f"Initial results ({len(initial_results)}): {[r.get('id') for r in initial_results]}")

        if retry_on_empty and not initial_results and self.recrawl_fn:
            try:
                self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            except AttributeError:
                pass
            self.recrawl_fn()
            initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial-after-recrawl")

        if not initial_results:
            answer, supported = self._fallback_payload([], question)
            return self._finalize_result(
                answer,
                supported,
                {
                    "mode": "classic",
                    "query": question,
                    "retry_on_empty": retry_on_empty,
                    "initial_result_count": 0,
                },
            )

        saved_results: List[Dict[str, Any]] = []
        saved_results.extend(initial_results)

        # Optional expansions for the initial seeds
        seeds = list(initial_results)
        if self.enable_graph_expansion:
            graph_expanded = self._expand_via_graph(question, seeds)
            if self.debug and graph_expanded:
                self.logger.debug(f"Graph expansion added {len(graph_expanded)} results")
            saved_results.extend(graph_expanded)
        if self.enable_section_expansion:
            section_expanded = self._expand_via_section(question, seeds)
            if self.debug and section_expanded:
                self.logger.debug(f"Section expansion added {len(section_expanded)} results")
            saved_results.extend(section_expanded)

        # Combine, dedupe, and prepare first context
        combined = self._combine_and_rerank(saved_results)
        combined = combined[: self.max_results_to_consider]

        context = self._assemble_context(combined, max_chars=self._compute_budget_chars(question))
        if self.debug:
            self.logger.debug(f"Context v1 length: {len(context)} chars")

        # If we can already answer, do it
        if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
            return self._finalize_result(
                self.chat_agent.answer(question_for_answer, context),
                True,
                {
                    "mode": "classic",
                    "query": question,
                    "retry_on_empty": retry_on_empty,
                    "initial_result_count": len(initial_results),
                    "combined_result_count": len(combined),
                    "answer_path": "answerable_initial",
                },
            )

        # === Iterative multi-hop: rewrite + targeted searches ===
        # We'll run up to 2 iterative hops (total 3 attempts counting initial)
        max_hops = 2
        tried_queries: List[str] = [question]

        for hop in range(1, max_hops + 1):
            if not self.enable_rewrite:
                break

            hints = self._collect_hints_for_rewrite(combined)
            rewrites = self.chat_agent.rewrite_query(question_for_search, hints)
            if self.debug:
                self.logger.debug(f"Hop {hop} rewrites: {rewrites}")

            if not rewrites:
                break

            # Support multi-queries encoded as "q1 || q2 || q3"
            subqueries = [q.strip() for q in rewrites.split("||") if q.strip()]
            subqueries = [q for q in subqueries if q not in tried_queries]
            if not subqueries:
                break

            # Run second-pass searches for each subquery
            hop_results: List[Dict[str, Any]] = []
            for q in subqueries:
                hop_results.extend(self._search(q, self.top_k_second_pass, tag="rewrite"))

            if self.debug and hop_results:
                self.logger.debug(f"Hop {hop} rewritten results: {[r.get('id') for r in hop_results]}")

            # Optional expansions on hop results
            if self.enable_graph_expansion and hop_results:
                hop_graph = self._expand_via_graph(question, hop_results)
                if self.debug and hop_graph:
                    self.logger.debug(f"Hop {hop} graph expansion added {len(hop_graph)} results")
                hop_results.extend(hop_graph)
            if self.enable_section_expansion and hop_results:
                hop_section = self._expand_via_section(question, hop_results)
                if self.debug and hop_section:
                    self.logger.debug(f"Hop {hop} section expansion added {len(hop_section)} results")
                hop_results.extend(hop_section)

            # Merge with what we already have and re-assemble context
            saved_results.extend(hop_results)
            combined = self._combine_and_rerank(saved_results)[: self.max_results_to_consider]
            context = self._assemble_context(combined, max_chars=self._compute_budget_chars(question))
            if self.debug:
                self.logger.debug(f"Context after hop {hop}: {len(context)} chars")

            if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
                return self._finalize_result(
                    self.chat_agent.answer(question_for_answer, context),
                    True,
                    {
                        "mode": "classic",
                        "query": question,
                        "retry_on_empty": retry_on_empty,
                        "initial_result_count": len(initial_results),
                        "combined_result_count": len(combined),
                        "answer_path": f"answerable_hop_{hop}",
                    },
                )

            tried_queries.extend(subqueries)

        # If we still can't answer confidently, return a natural fallback with helpful links
        if self.allow_best_effort and combined:
            return self._finalize_result(
                self.chat_agent.answer(question_for_answer, context),
                False,
                {
                    "mode": "classic",
                    "query": question,
                    "retry_on_empty": retry_on_empty,
                    "initial_result_count": len(initial_results),
                    "combined_result_count": len(combined),
                    "answer_path": "best_effort",
                },
            )
        answer, supported = self._fallback_payload(combined, question_for_answer)
        return self._finalize_result(
            answer,
            supported,
            {
                "mode": "classic",
                "query": question,
                "retry_on_empty": retry_on_empty,
                "initial_result_count": len(initial_results),
                "combined_result_count": len(combined),
                "answer_path": "fallback",
            },
        )

    def _query_builder(self, question: str, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        if self.debug:
            self.logger.debug(f"[builder] User query: {question}")
            if memory_context:
                self.logger.debug(f"[builder] Memory context length: {len(memory_context)} chars")

        route = self.context_builder.plan_initial_route(question=question, memory_context=memory_context)
        route_mode = str(route.get("mode") or "retrieve_new")
        standalone_query = str(route.get("standalone_query") or "").strip()
        concepts = route.get("concepts") if isinstance(route.get("concepts"), list) else []

        if self.debug:
            self.logger.debug(
                f"[builder] Route mode={route_mode}, "
                f"standalone_query={standalone_query}, concepts={concepts}"
            )

        if route_mode == "transform_only":
            prior = (memory_context or "").strip()
            if not prior:
                return self._finalize_result(
                    "I don't have enough prior conversation context to transform yet.",
                    False,
                    {
                        "mode": "builder",
                        "route_mode": route_mode,
                        "query": question,
                        "concepts": concepts,
                    },
                )
            prompt = (
                "You are transforming a prior answer. Follow the user's instruction exactly.\n"
                "Do not add new facts that are not present in prior context.\n\n"
                f"Instruction: {question}\n\n"
                f"Prior context:\n{prior}"
            )
            transformed = (self.chat_agent.chatbot.generate(prompt) or "").strip()
            if transformed:
                return self._finalize_result(
                    transformed,
                    True,
                    {
                        "mode": "builder",
                        "route_mode": route_mode,
                        "query": question,
                        "concepts": concepts,
                        "answer_path": "transform_only",
                    },
                )
            return self._finalize_result(
                "I couldn't transform the previous response from the available memory.",
                False,
                {
                    "mode": "builder",
                    "route_mode": route_mode,
                    "query": question,
                    "concepts": concepts,
                    "answer_path": "transform_only_failed",
                },
            )

        if route_mode == "retrieve_followup":
            question_for_search = standalone_query or question
            question_for_answer = f"{memory_context}\nUser: {question}".strip() if memory_context else question
        else:
            # retrieve_new: intentionally ignore memory for retrieval and answering.
            question_for_search = question
            question_for_answer = question

        initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial")
        if self.debug:
            self.logger.debug(
                f"[builder] Initial results ({len(initial_results)}): "
                f"{[r.get('id') for r in initial_results]}"
            )

        if retry_on_empty and not initial_results and self.recrawl_fn:
            try:
                self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            except AttributeError:
                pass
            self.recrawl_fn()
            initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial-after-recrawl")

        if not initial_results:
            answer, supported = self._fallback_payload([], question)
            return self._finalize_result(
                answer,
                supported,
                {
                    "mode": "builder",
                    "route_mode": route_mode,
                    "query": question,
                    "concepts": concepts,
                    "initial_result_count": 0,
                },
            )

        saved_results: List[Dict[str, Any]] = []
        saved_results.extend(initial_results)

        if not concepts:
            concepts = self.context_builder.extract_concepts(question_for_search)
        if self.debug:
            self.logger.debug(f"[builder] Concepts: {concepts}")

        # Minimal builder loop: request targeted searches only for missing concepts.
        coverage = self.context_builder.coverage_report(concepts, saved_results)
        for i in range(self.builder_max_rounds):
            coverage = self.context_builder.coverage_report(concepts, saved_results)
            missing = coverage.get("missing") or []
            if self.debug:
                self.logger.debug(
                    f"[builder] Round {i + 1} coverage: covered={coverage.get('covered')} missing={missing}"
                )
            if not missing:
                break
            decision = self.context_builder.decide_followups(question_for_search, missing, saved_results)
            drop_ids = set(decision.get("drop_chunk_ids") or [])
            if drop_ids:
                saved_results = [
                    r
                    for r in saved_results
                    if (r.get("id") or f"{r.get('url', '')}#chunk_{r.get('chunk_index', -1)}") not in drop_ids
                ]
            extra_queries = decision.get("queries") or []
            if self.debug:
                self.logger.debug(
                    f"[builder] Round {i + 1} decision: "
                    f"queries={extra_queries}, drop_chunk_ids={list(drop_ids)}"
                )
            if not extra_queries:
                break
            for q in extra_queries:
                saved_results.extend(self._search(q, self.top_k_second_pass, tag="builder-followup"))

        combined = self._combine_and_rerank(saved_results)[: self.max_results_to_consider]
        context = self._assemble_context(combined, max_chars=self._compute_budget_chars(question))
        coverage = self.context_builder.coverage_report(concepts, combined)
        if self.debug:
            self.logger.debug(f"[builder] Context length: {len(context)} chars")
            self.logger.debug(
                f"[builder] Final coverage: "
                f"covered={coverage.get('covered')} missing={coverage.get('missing')}"
            )

        if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
            return self._finalize_result(
                self.chat_agent.answer(question_for_answer, context),
                True,
                {
                    "mode": "builder",
                    "route_mode": route_mode,
                    "query": question,
                    "concepts": concepts,
                    "coverage": coverage,
                    "combined_result_count": len(combined),
                    "answer_path": "answerable",
                },
            )

        if self.allow_best_effort and combined:
            answer, supported = self._best_effort_payload(
                question_for_answer=question_for_answer,
                context=context,
                concepts=concepts,
                coverage=coverage,
                results=combined,
            )
            return self._finalize_result(
                answer,
                supported,
                {
                    "mode": "builder",
                    "route_mode": route_mode,
                    "query": question,
                    "concepts": concepts,
                    "coverage": coverage,
                    "combined_result_count": len(combined),
                    "answer_path": "best_effort",
                },
            )
        answer, supported = self._fallback_payload(combined, question_for_answer)
        return self._finalize_result(
            answer,
            supported,
            {
                "mode": "builder",
                "route_mode": route_mode,
                "query": question,
                "concepts": concepts,
                "coverage": coverage,
                "combined_result_count": len(combined),
                "answer_path": "fallback",
            },
        )

    # ---------------- Helpers ----------------
    def _finalize_result(self, answer: str, supported: bool, trace: Optional[Dict[str, Any]] = None) -> QueryResult:
        self._last_supported = bool(supported)
        self._last_trace = dict(trace or {})
        return QueryResult(
            answer=answer,
            supported=self._last_supported,
            sources=self._current_sources(),
            trace=dict(self._last_trace),
        )

    def _current_sources(self) -> List[SourceRef]:
        return self.context_tools.current_sources(self._last_used_sources)

    def _search(self, query: Optional[Union[str, List[str]]], k: int, tag: str) -> List[Dict[str, Any]]:
        return self.retriever.search(query, k, tag)

    def _collect_hints_for_rewrite(self, results: List[Dict[str, Any]]) -> List[str]:
        return self.retriever.collect_hints_for_rewrite(results)

    def _expand_via_graph(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.retriever.expand_via_graph(question, seeds)

    def _expand_via_section(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.retriever.expand_via_section(question, seeds)

    def _combine_and_rerank(self, *result_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.retriever.combine_and_rerank(*result_groups)

        groups: List[List[Dict[str, Any]]] = []
        if len(result_groups) == 1 and isinstance(result_groups[0], list):
            # single list possibly passed in
            groups = [result_groups[0]]
        else:
            groups = list(result_groups)

        by_id: Dict[str, Dict[str, Any]] = {}
        for group in groups:
            for r in group:
                rid = r.get("id") or f"{r.get('url','')}#chunk_{r.get('chunk_index',-1)}"
                if rid in by_id:
                    prev = by_id[rid]
                    if (r.get("score") or -math.inf) > (prev.get("score") or -math.inf):
                        by_id[rid] = r
                    else:
                        prev.setdefault("_boost_reason", r.get("_boost_reason"))
                        prev.setdefault("_origin", r.get("_origin"))
                        prev.setdefault("_meta_rank", r.get("_meta_rank"))
                else:
                    by_id[rid] = r

        combined = list(by_id.values())

        def rank_key(r: Dict[str, Any]) -> Tuple:
            vec = float(r.get("_score_vec") or r.get("score") or 0.0)
            bm25 = float(r.get("_score_bm25") or 0.0)
            # Hybrid score: weighted sum (vector dominates, BM25 helps recall)
            score = (0.75 * vec) + (0.25 * bm25)
            boost = 0.0
            if r.get("_boost_reason") == "anchor":
                boost += self.anchor_boost
            if r.get("_boost_reason") == "section":
                boost += self.section_boost

            origin_pri = {
                "initial": 3,
                "initial-after-recrawl": 3,
                "rewrite": 2,
                "graph-anchor": 1,
                "section": 1,
            }.get(r.get("_origin", ""), 0)
            meta_rank = r.get("_meta_rank", 9999)
            return (score + boost, origin_pri, -meta_rank)

        combined.sort(key=rank_key, reverse=True)
        max_per_parent = 2  # allow up to 2 segments from the same page; tune 1â€“3
        by_parent = {}
        parent_limited = []
        for r in combined:
            meta = r.get("metadata") or {}
            parent = meta.get("chunk_id") or meta.get("parent_id") or (r.get("url") or r.get("source") or "")
            cnt = by_parent.get(parent, 0)
            if cnt >= max_per_parent:
                continue
            by_parent[parent] = cnt + 1
            parent_limited.append(r)

        # --- Stage B: cap per canonical URL (collapse ?page=1/2, utm_* etc.)
        max_per_canon = 1  # usually 1 is ideal; set 2 if pagination genuinely differs
        seen_canon = {}
        canon_limited = []
        for r in parent_limited:
            canon = self._normalize_for_dedupe(r.get("url") or r.get("source") or "")
            cnt = seen_canon.get(canon, 0)
            if cnt >= max_per_canon:
                continue
            seen_canon[canon] = cnt + 1
            canon_limited.append(r)

        return canon_limited

    # ---------------- Hybrid retrieval (BM25) ----------------
    def _tokenize(self, text: str) -> List[str]:
        return self.retriever._tokenize(text)

    def _ensure_bm25(self):
        self.retriever._ensure_bm25()
        return

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        return self.retriever._bm25_search(query, top_k=top_k)

    def _normalize_for_dedupe(self, url: str) -> str:
        return self.retriever._normalize_for_dedupe(url)

    def _assemble_context(self, results: List[Dict[str, Any]], max_chars: int) -> str:
        context, used_sources = self.context_tools.assemble_context(results, max_chars=max_chars)
        self._last_used_sources = used_sources
        return context

    def _compute_budget_chars(self, question: str) -> int:
        _ = question
        return self.context_tools.compute_budget_chars(
            self.chat_agent,
            max_context_chars=self.max_context_chars,
        )

    def _fallback_payload(self, results: List[Dict[str, Any]], question: str) -> Tuple[str, bool]:
        answer, supported, used_sources = self.response_composer.fallback_payload(results, question)
        self._last_used_sources = used_sources
        return answer, supported

    def _fallback_message(self, results: List[Dict[str, Any]], question: str) -> str:
        return self._fallback_payload(results, question)[0]

    def _best_effort_payload(
        self,
        question_for_answer: str,
        context: str,
        concepts: List[str],
        coverage: Dict[str, List[str]],
        results: List[Dict[str, Any]],
    ) -> Tuple[str, bool]:
        _ = concepts, results
        return self.response_composer.best_effort_payload(
            question_for_answer=question_for_answer,
            context=context,
            coverage=coverage,
            used_sources=self._last_used_sources,
        )

    def _best_effort_with_links(
        self,
        question_for_answer: str,
        context: str,
        concepts: List[str],
        coverage: Dict[str, List[str]],
        results: List[Dict[str, Any]],
    ) -> str:
        return self._best_effort_payload(
            question_for_answer=question_for_answer,
            context=context,
            concepts=concepts,
            coverage=coverage,
            results=results,
        )[0]

    def _read_more_urls_from_used_sources(self, limit: int = 3) -> List[str]:
        return self.context_tools.read_more_urls_from_used_sources(self._last_used_sources, limit=limit)

    def _helpful_links_by_concept(
        self, concepts: List[str], results: List[Dict[str, Any]], max_links_per_concept: int = 2
    ) -> Dict[str, List[str]]:
        return self.context_tools.helpful_links_by_concept(
            concepts,
            results,
            max_links_per_concept=max_links_per_concept,
        )

    def _top_distinct_urls(self, results: List[Dict[str, Any]], limit: int = 3) -> List[str]:
        return self.context_tools.top_distinct_urls(results, limit=limit)

    def _extract_used_urls_from_context(self, context: str) -> List[str]:
        return self.context_tools.extract_used_urls_from_context(context)
