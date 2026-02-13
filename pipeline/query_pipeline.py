import math
import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from chatbot.context_builder_agent import ContextBuilderAgent


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
        self.context_builder = ContextBuilderAgent(planner_llm=getattr(self.chat_agent, "chatbot", None))

        # Hybrid retrieval (BM25) cache
        self._bm25_ready = False
        self._bm25_docs = []
        self._bm25_doc_ids = []
        self._bm25 = None
        self._bm25_avgdl = 0.0
        self._bm25_df = defaultdict(int)
        self._bm25_idf = {}
        self._bm25_k1 = 1.5
        self._bm25_b = 0.75
        self._last_used_sources: List[Dict[str, str]] = []

    # ---------------- Core entrypoint ----------------
    def query(self, question: str, retry_on_empty: bool = False, memory_context: str = "") -> str:
        if (self.retrieval_mode or "classic").lower() == "builder":
            return self._query_builder(question, retry_on_empty=retry_on_empty, memory_context=memory_context)

        if self.debug:
            print(f"\n[DEBUG] User query: {question}")
            if memory_context:
                print(f"[DEBUG] Memory context length: {len(memory_context)} chars")

        question_for_search = f"{memory_context}\n{question}".strip() if memory_context else question
        question_for_answer = f"{memory_context}\nUser: {question}".strip() if memory_context else question

        # === Pass 1: initial search ===
        initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial")
        if self.debug:
            print(f"[DEBUG] Initial results ({len(initial_results)}): {[r.get('id') for r in initial_results]}")

        if retry_on_empty and not initial_results and self.recrawl_fn:
            try:
                self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            except Exception:
                pass
            self.recrawl_fn()
            initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial-after-recrawl")

        if not initial_results:
            return self._fallback_message([], question)

        saved_results: List[Dict[str, Any]] = []
        saved_results.extend(initial_results)

        # Optional expansions for the initial seeds
        seeds = list(initial_results)
        if self.enable_graph_expansion:
            graph_expanded = self._expand_via_graph(question, seeds)
            if self.debug and graph_expanded:
                print(f"[DEBUG] Graph expansion added {len(graph_expanded)} results")
            saved_results.extend(graph_expanded)
        if self.enable_section_expansion:
            section_expanded = self._expand_via_section(question, seeds)
            if self.debug and section_expanded:
                print(f"[DEBUG] Section expansion added {len(section_expanded)} results")
            saved_results.extend(section_expanded)

        # Combine, dedupe, and prepare first context
        combined = self._combine_and_rerank(saved_results)
        combined = combined[: self.max_results_to_consider]

        context = self._assemble_context(combined, max_chars=self._compute_budget_chars(question))
        if self.debug:
            print(f"[DEBUG] Context v1 length: {len(context)} chars")

        # If we can already answer, do it
        if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
            return self.chat_agent.answer(question_for_answer, context)

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
                print(f"[DEBUG] Hop {hop} rewrites: {rewrites}")

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
                print(f"[DEBUG] Hop {hop} rewritten results: {[r.get('id') for r in hop_results]}")

            # Optional expansions on hop results
            if self.enable_graph_expansion and hop_results:
                hop_graph = self._expand_via_graph(question, hop_results)
                if self.debug and hop_graph:
                    print(f"[DEBUG] Hop {hop} graph expansion added {len(hop_graph)} results")
                hop_results.extend(hop_graph)
            if self.enable_section_expansion and hop_results:
                hop_section = self._expand_via_section(question, hop_results)
                if self.debug and hop_section:
                    print(f"[DEBUG] Hop {hop} section expansion added {len(hop_section)} results")
                hop_results.extend(hop_section)

            # Merge with what we already have and re-assemble context
            saved_results.extend(hop_results)
            combined = self._combine_and_rerank(saved_results)[: self.max_results_to_consider]
            context = self._assemble_context(combined, max_chars=self._compute_budget_chars(question))
            if self.debug:
                print(f"[DEBUG] Context after hop {hop}: {len(context)} chars")

            if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
                return self.chat_agent.answer(question_for_answer, context)

            tried_queries.extend(subqueries)

        # If we still can't answer confidently, return a natural fallback with helpful links
        if self.allow_best_effort and combined:
            return self.chat_agent.answer(question_for_answer, context)
        return self._fallback_message(combined, question_for_answer)

    def _query_builder(self, question: str, retry_on_empty: bool = False, memory_context: str = "") -> str:
        if self.debug:
            print(f"\n[DEBUG] [builder] User query: {question}")
            if memory_context:
                print(f"[DEBUG] [builder] Memory context length: {len(memory_context)} chars")

        route = self.context_builder.plan_initial_route(question=question, memory_context=memory_context)
        route_mode = str(route.get("mode") or "retrieve_new")
        standalone_query = str(route.get("standalone_query") or "").strip()
        concepts = route.get("concepts") if isinstance(route.get("concepts"), list) else []

        if self.debug:
            print(
                f"[DEBUG] [builder] Route mode={route_mode}, "
                f"standalone_query={standalone_query}, concepts={concepts}"
            )

        if route_mode == "transform_only":
            prior = (memory_context or "").strip()
            if not prior:
                return "I don't have enough prior conversation context to transform yet."
            prompt = (
                "You are transforming a prior answer. Follow the user's instruction exactly.\n"
                "Do not add new facts that are not present in prior context.\n\n"
                f"Instruction: {question}\n\n"
                f"Prior context:\n{prior}"
            )
            transformed = (self.chat_agent.chatbot.generate(prompt) or "").strip()
            if transformed:
                return transformed
            return "I couldn't transform the previous response from the available memory."

        if route_mode == "retrieve_followup":
            question_for_search = standalone_query or question
            question_for_answer = f"{memory_context}\nUser: {question}".strip() if memory_context else question
        else:
            # retrieve_new: intentionally ignore memory for retrieval and answering.
            question_for_search = question
            question_for_answer = question

        initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial")
        if self.debug:
            print(
                f"[DEBUG] [builder] Initial results ({len(initial_results)}): "
                f"{[r.get('id') for r in initial_results]}"
            )

        if retry_on_empty and not initial_results and self.recrawl_fn:
            try:
                self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            except Exception:
                pass
            self.recrawl_fn()
            initial_results = self._search(question_for_search, self.top_k_first_pass, tag="initial-after-recrawl")

        if not initial_results:
            return self._fallback_message([], question)

        saved_results: List[Dict[str, Any]] = []
        saved_results.extend(initial_results)

        if not concepts:
            concepts = self.context_builder.extract_concepts(question_for_search)
        if self.debug:
            print(f"[DEBUG] [builder] Concepts: {concepts}")

        # Minimal builder loop: request targeted searches only for missing concepts.
        coverage = self.context_builder.coverage_report(concepts, saved_results)
        for i in range(self.builder_max_rounds):
            coverage = self.context_builder.coverage_report(concepts, saved_results)
            missing = coverage.get("missing") or []
            if self.debug:
                print(f"[DEBUG] [builder] Round {i + 1} coverage: covered={coverage.get('covered')} missing={missing}")
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
                print(
                    f"[DEBUG] [builder] Round {i + 1} decision: "
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
            print(f"[DEBUG] [builder] Context length: {len(context)} chars")
            print(
                f"[DEBUG] [builder] Final coverage: "
                f"covered={coverage.get('covered')} missing={coverage.get('missing')}"
            )

        if self.enable_answerability_check and self.chat_agent._judge_answerability(question_for_answer, context):
            return self.chat_agent.answer(question_for_answer, context)

        if self.allow_best_effort and combined:
            return self._best_effort_with_links(
                question_for_answer=question_for_answer,
                context=context,
                concepts=concepts,
                coverage=coverage,
                results=combined,
            )
        return self._fallback_message(combined, question_for_answer)

    # ---------------- Helpers ----------------
    def _search(self, query: Optional[Union[str, List[str]]], k: int, tag: str) -> List[Dict[str, Any]]:
        if not query:
            return []
        queries = [query] if isinstance(query, str) else list(query)
        all_results: List[Dict[str, Any]] = []
        for q in queries:
            # Vector search
            q_emb = self.chat_agent.embedder.embed(q)
            results = self.chat_agent.vector_db.search(q_emb, top_k=k) or []
            for i, r in enumerate(results):
                r.setdefault("_meta_rank", i)
                r.setdefault("_origin", tag)
                r.setdefault("_score_vec", float(r.get("score") or 0.0))
            all_results.extend(results)

            # Hybrid BM25 search (optional)
            if self.enable_hybrid:
                bm25_hits = self._bm25_search(q, top_k=max(8, k))
                for i, r in enumerate(bm25_hits):
                    r.setdefault("_meta_rank", i)
                    r.setdefault("_origin", f"{tag}-bm25")
                    r.setdefault("_score_bm25", float(r.get("_score_bm25") or 0.0))
                all_results.extend(bm25_hits)
        return all_results

    def _collect_hints_for_rewrite(self, results: List[Dict[str, Any]]) -> List[str]:
        hints: List[str] = []
        for r in results[:8]:
            if r.get("hierarchy"):
                hints.append(" > ".join(r["hierarchy"]))
            for inc in r.get("metadata", {}).get("incoming_links") or []:
                if inc.get("anchor_text"):
                    hints.append(inc["anchor_text"])
        return [h for h in hints if h]

    def _expand_via_graph(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        expansions: List[Dict[str, Any]] = []
        seen_queries = set()

        for r in seeds[:12]:
            inc_links = (r.get("metadata", {}) or {}).get("incoming_links") or []
            for inc in inc_links[:5]:
                anchor = (inc.get("anchor_text") or "").strip()
                if not anchor:
                    continue
                q = f"{anchor} {question}".strip()
                if q in seen_queries:
                    continue
                seen_queries.add(q)
                res = self._search(q, k=3, tag="graph-anchor")
                for x in res:
                    x.setdefault("_boost_reason", "anchor")
                expansions.extend(res)
        return expansions

    def _expand_via_section(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        expansions: List[Dict[str, Any]] = []
        seen_queries = set()

        for r in seeds[:10]:
            top_heading = None
            if isinstance(r.get("hierarchy"), list) and r["hierarchy"]:
                top_heading = r["hierarchy"][0]
            if not top_heading:
                continue

            q = f"{question} {top_heading}"
            if q in seen_queries:
                continue
            seen_queries.add(q)

            res = self._search(q, k=3, tag="section")
            for x in res:
                x.setdefault("_boost_reason", "section")
            expansions.extend(res)
        return expansions

    def _combine_and_rerank(self, *result_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Allow both call styles: _combine_and_rerank(list) or _combine_and_rerank(list1, list2, ...)
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
        return re.findall(r"[A-Za-z0-9_]{2,}", (text or "").lower())

    def _ensure_bm25(self):
        if self._bm25_ready:
            return
        docs = []
        doc_ids = []
        for rec in self.chat_agent.vector_db.metadata or []:
            text = rec.get("text") or rec.get("summary") or ""
            if not text:
                continue
            tokens = self._tokenize(text)
            if not tokens:
                continue
            docs.append(tokens)
            doc_ids.append(rec)

        self._bm25_docs = docs
        self._bm25_doc_ids = doc_ids
        if not docs:
            self._bm25_ready = True
            return

        df = defaultdict(int)
        total_len = 0
        for doc in docs:
            total_len += len(doc)
            for t in set(doc):
                df[t] += 1
        self._bm25_df = df
        self._bm25_avgdl = total_len / max(len(docs), 1)
        n_docs = len(docs)
        self._bm25_idf = {t: math.log(1 + (n_docs - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._bm25_ready = True

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        self._ensure_bm25()
        if not self._bm25_docs:
            return []

        q_terms = self._tokenize(query)
        if not q_terms:
            return []

        scores = []
        for i, doc in enumerate(self._bm25_docs):
            doc_len = len(doc)
            tf = defaultdict(int)
            for t in doc:
                tf[t] += 1
            score = 0.0
            for t in q_terms:
                if t not in tf:
                    continue
                idf = self._bm25_idf.get(t, 0.0)
                denom = tf[t] + self._bm25_k1 * (1 - self._bm25_b + self._bm25_b * (doc_len / self._bm25_avgdl))
                score += idf * (tf[t] * (self._bm25_k1 + 1) / denom)
            scores.append((score, i))

        scores.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for score, idx in scores[:top_k]:
            if score <= 0:
                continue
            rec = self._bm25_doc_ids[idx].copy()
            rec["_score_bm25"] = float(score)
            hits.append(rec)
        return hits

    def _normalize_for_dedupe(self, url: str) -> str:
        try:
            u = urlparse(url)
            drop = {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "fbclid",
                "gclid",
                "ref",
                "ref_src",
                "ref_url",
                "page",
            }
            kept = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k.lower() not in drop]
            kept.sort()
            scheme = (u.scheme or "https").lower()
            netloc = (u.netloc or "").lower()
            path = (u.path or "/").rstrip("/") or "/"
            return urlunparse((scheme, netloc, path, "", urlencode(kept), ""))  # no fragment
        except Exception:
            return url or ""

    def _assemble_context(self, results: List[Dict[str, Any]], max_chars: int) -> str:
        section_groups: Dict[str, List[str]] = defaultdict(list)
        seen_ids = set()
        total = 0
        used_sources: List[Dict[str, str]] = []

        for r in results:
            uid = r.get("id") or f"{r.get('url','')}#chunk_{r.get('chunk_index',-1)}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            text = (r.get("text") or "").strip()
            if not text:
                continue

            url = r.get("url") or r.get("source", "N/A")
            subheadings = " > ".join(r.get("hierarchy", [])) if r.get("hierarchy") else ""
            prefix = f"[{subheadings}]\n" if subheadings else ""
            chunk_text = f"{prefix}{text}\n\n(Source: {url})"

            if total + len(chunk_text) > max_chars:
                remaining = max(0, max_chars - total)
                preview = chunk_text[:remaining]
                if preview:
                    top = (r.get("hierarchy") or ["General"])[0]
                    section_groups[top].append(preview)
                    total += len(preview)
                    used_sources.append(
                        {
                            "chunk_id": str(uid),
                            "url": str(url),
                            "section": str(top),
                        }
                    )
                break

            top_level = (r.get("hierarchy") or ["General"])[0]
            section_groups[top_level].append(chunk_text)
            total += len(chunk_text)
            used_sources.append(
                {
                    "chunk_id": str(uid),
                    "url": str(url),
                    "section": str(top_level),
                }
            )

            if total >= max_chars:
                break

        blocks = []
        for section, chunks in section_groups.items():
            full = "\n\n".join(chunks).strip()
            if full:
                blocks.append(full)

        self._last_used_sources = used_sources
        return "\n\n---\n\n".join(blocks).strip()

    def _compute_budget_chars(self, question: str) -> int:
        """
        Adaptive context size based on model context window when available.
        We reserve room for instructions, user question, and model output.
        """
        base = max(self.max_context_chars, 8000)  # never go below 8k chars
        chatbot = getattr(self.chat_agent, "chatbot", None)
        context_window = getattr(chatbot, "context_window_tokens", None)

        # Preferred path: explicit model context window from the chatbot wrapper.
        if isinstance(context_window, int) and context_window > 0:
            # Reserve at least 2k tokens, or 15% of window, for system/user/answer overhead.
            reserve_tokens = max(2000, int(context_window * 0.15))
            usable_tokens = max(2000, context_window - reserve_tokens)
            # Rough conversion: 1 token ~ 4 chars. Cap to avoid extreme prompt sizes.
            return max(base, min(int(usable_tokens * 4), 180000))

        model_name = (getattr(chatbot, "model_name", None) or getattr(chatbot, "model", "")).lower()
        # Fallback heuristic for wrappers without explicit context metadata.
        if "gpt-4o" in model_name or "4o" in model_name or "gpt-4.1" in model_name:
            return min(int(base * 5), 100000)
        return base

    def _fallback_message(self, results: List[Dict[str, Any]], question: str) -> str:
        """
        Natural fallback when we can't find enough info. Provide a few helpful links if any
        retrieved items exist; otherwise a concise apology.
        """
        if not results:
            return "I couldn't find anything on this site related to your question."

        context = self._assemble_context(results[: min(8, len(results))], max_chars=min(self.max_context_chars, 8000))
        _, supported = self.chat_agent.answer_with_support(question, context)
        if supported != "Y":
            return "I couldn't find enough information on this site to answer that directly."

        # Pick up to 3 distinct useful URLs with optional section labels
        links: List[str] = []
        seen = set()
        for r in results:
            url = r.get("url") or r.get("source")
            if not url or url in seen:
                continue
            seen.add(url)
            section = " > ".join(r.get("hierarchy", [])[:2]) if r.get("hierarchy") else None
            if section:
                links.append(f"- {section}: {url}")
            else:
                links.append(f"- {url}")
            if len(links) >= 3:
                break

        if not links:
            return "I couldn't find enough relevant information here to answer that."

        return (
            "I couldn't find enough information on this site to answer that directly. "
            "These pages may help:\n" + "\n".join(links)
        )

    def _best_effort_with_links(
        self,
        question_for_answer: str,
        context: str,
        concepts: List[str],
        coverage: Dict[str, List[str]],
        results: List[Dict[str, Any]],
    ) -> str:
        """
        Best-effort response when context is partially relevant but not fully answerable.
        Includes explicit uncertainty + concept-oriented links for follow-up reading.
        """
        missing = coverage.get("missing") or []
        used_urls = self._read_more_urls_from_used_sources(limit=3)

        if missing:
            guided_question = (
                f"{question_for_answer}\n\n"
                "Instruction: Use only the provided website context.\n"
                "Never add external knowledge.\n"
                "If information is missing, explicitly say it is not covered in the documentation.\n"
                f"Missing concepts detected: {', '.join(missing)}"
            )
            base_answer, supported = self.chat_agent.answer_with_support(guided_question, context)
            base_answer = (base_answer or "").strip()
        else:
            base_answer, supported = self.chat_agent.answer_with_support(question_for_answer, context)
            base_answer = (base_answer or "").strip()

        if not used_urls:
            return base_answer
        if str(supported).upper() != "Y":
            return base_answer

        lines = ["Read more:"]
        for u in used_urls:
            lines.append(f"- {u}")
        return f"{base_answer}\n\n" + "\n".join(lines)

    def _read_more_urls_from_used_sources(self, limit: int = 3) -> List[str]:
        links = []
        seen = set()
        for src in self._last_used_sources:
            url = str(src.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            links.append(url)
            if len(links) >= limit:
                break
        return links

    def _helpful_links_by_concept(
        self, concepts: List[str], results: List[Dict[str, Any]], max_links_per_concept: int = 2
    ) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        if not concepts:
            return out

        for concept in concepts[:4]:
            needle = (concept or "").strip().lower()
            if not needle:
                continue

            links = []
            seen = set()
            for r in results[:20]:
                url = r.get("url") or r.get("source")
                if not url or url in seen:
                    continue
                text = (r.get("text") or "").lower()
                hierarchy = " ".join(r.get("hierarchy") or []).lower()
                if needle in text or needle in hierarchy or needle in url.lower():
                    seen.add(url)
                    links.append(url)
                if len(links) >= max_links_per_concept:
                    break
            if links:
                out[concept] = links
        return out

    def _top_distinct_urls(self, results: List[Dict[str, Any]], limit: int = 3) -> List[str]:
        links = []
        seen = set()
        for r in results:
            url = r.get("url") or r.get("source")
            if not url or url in seen:
                continue
            seen.add(url)
            links.append(url)
            if len(links) >= limit:
                break
        return links

    def _extract_used_urls_from_context(self, context: str) -> List[str]:
        links = []
        seen = set()
        for url in re.findall(r"\(Source:\s*(https?://[^\s\)]+)\)", context or ""):
            if url in seen:
                continue
            seen.add(url)
            links.append(url)
        return links

