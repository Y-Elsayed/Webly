from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
import math


class QueryPipeline:
    """
    Retrieval with:
    - Initial semantic search
    - Optional LLM query rewrite + second search
    - Graph-aware expansion (backlinks via anchor_text, optional section/sibling expansion)
    - Re-ranking + length trimming
    - Sectioned context assembly
    """
    def __init__(
        self,
        chat_agent,
        recrawl_fn: Optional[callable] = None,
        enable_rewrite: bool = True,
        enable_graph_expansion: bool = True,
        enable_section_expansion: bool = True,
        max_context_chars: int = 12000,
        max_results_to_consider: int = 30,  # across all passes
        top_k_first_pass: int | None = None,  # default to chat_agent.top_k if None
        top_k_second_pass: int | None = None, # for rewrite/expansion passes
        anchor_boost: float = 0.10,           # boost for results sourced via anchor/backlink expansion
        section_boost: float = 0.05,          # mild boost for same-section/sibling expansion
        debug: bool = False                   # NEW: toggle detailed logging
    ):
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn

        self.enable_rewrite = enable_rewrite
        self.enable_graph_expansion = enable_graph_expansion
        self.enable_section_expansion = enable_section_expansion

        self.max_context_chars = max_context_chars
        self.max_results_to_consider = max_results_to_consider

        self.top_k_first_pass = top_k_first_pass or chat_agent.top_k
        self.top_k_second_pass = top_k_second_pass or max(chat_agent.top_k, 5)

        self.anchor_boost = anchor_boost
        self.section_boost = section_boost
        self.debug = debug

    # ---------------- Core entrypoint ----------------
    def query(self, question: str, retry_on_empty: bool = False) -> str:
        if self.debug:
            print(f"\n[DEBUG] User query: {question}")

        # Pass 1: initial search
        initial_results = self._search(question, self.top_k_first_pass, tag="initial")
        if self.debug:
            print(f"[DEBUG] Initial results ({len(initial_results)}): {[r.get('id') for r in initial_results]}")

        if retry_on_empty and not initial_results and self.recrawl_fn:
            self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            self.recrawl_fn()
            initial_results = self._search(question, self.top_k_first_pass, tag="initial-after-recrawl")

        if not initial_results:
            return "Sorry, I couldn't find relevant information."

        # Optional: fast query rewrite using top hints
        rewritten_query = None
        if self.enable_rewrite:
            hints = self._collect_hints_for_rewrite(initial_results)
            rewritten_query = self.chat_agent.rewrite_query(question, hints)
            if self.debug:
                print(f"[DEBUG] Rewritten query: {rewritten_query}")

        rewritten_results = self._search(rewritten_query, self.top_k_second_pass, tag="rewrite") if rewritten_query else []
        if self.debug and rewritten_results:
            print(f"[DEBUG] Rewritten results ({len(rewritten_results)}): {[r.get('id') for r in rewritten_results]}")

        # Graph-aware expansion
        graph_expanded_results = self._expand_via_graph(question, initial_results + rewritten_results) \
                                 if self.enable_graph_expansion else []
        if self.debug and graph_expanded_results:
            print(f"[DEBUG] Graph expansion added {len(graph_expanded_results)} results")

        # Section/sibling expansion
        section_expanded_results = self._expand_via_section(question, initial_results + rewritten_results) \
                                   if self.enable_section_expansion else []
        if self.debug and section_expanded_results:
            print(f"[DEBUG] Section expansion added {len(section_expanded_results)} results")

        # Combine + rerank + trim
        combined = self._combine_and_rerank(initial_results, rewritten_results, graph_expanded_results, section_expanded_results)
        trimmed = combined[: self.max_results_to_consider]
        if self.debug:
            print(f"[DEBUG] Combined + reranked results ({len(trimmed)} kept): {[r.get('id') for r in trimmed]}")

        # Build sectioned context
        context = self._assemble_context(trimmed, max_chars=self.max_context_chars)
        if self.debug:
            print(f"[DEBUG] Final context length: {len(context)} chars")

        return self.chat_agent.answer(question, context)

    # ---------------- Helpers ----------------
    def _search(self, query: Optional[str], k: int, tag: str) -> List[Dict[str, Any]]:
        if not query:
            return []
        q_emb = self.chat_agent.embedder.embed(query)
        results = self.chat_agent.vector_db.search(q_emb, top_k=k) or []
        for i, r in enumerate(results):
            r.setdefault("_meta_rank", i)
            r.setdefault("_origin", tag)
        return results

    def _collect_hints_for_rewrite(self, results: List[Dict[str, Any]]) -> List[str]:
        hints = []
        for r in results[:8]:
            if r.get("hierarchy"):
                hints.append(" > ".join(r["hierarchy"]))
            for inc in (r.get("metadata", {}).get("incoming_links") or []):
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
                    x["_boost_reason"] = "anchor"
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
                x["_boost_reason"] = "section"
            expansions.extend(res)
        return expansions

    def _combine_and_rerank(self, *result_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        origin_priority = {"initial": 3, "initial-after-recrawl": 3, "rewrite": 2, "graph-anchor": 1, "section": 1}
        by_id: Dict[str, Dict[str, Any]] = {}

        for group in result_groups:
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
            score = float(r.get("score") or 0.0)
            boost = 0.0
            if r.get("_boost_reason") == "anchor":
                boost += self.anchor_boost
            if r.get("_boost_reason") == "section":
                boost += self.section_boost

            origin_pri = {"initial": 3, "initial-after-recrawl": 3, "rewrite": 2, "graph-anchor": 1, "section": 1}.get(r.get("_origin", ""), 0)
            meta_rank = r.get("_meta_rank", 9999)
            return (score + boost, origin_pri, -meta_rank)

        combined.sort(key=rank_key, reverse=True)
        return combined

    def _assemble_context(self, results: List[Dict[str, Any]], max_chars: int) -> str:
        section_groups: Dict[str, List[str]] = defaultdict(list)
        seen_ids = set()
        total = 0

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
                preview = chunk_text[: max(0, max_chars - total)]
                if preview:
                    top = (r.get("hierarchy") or ["General"])[0]
                    section_groups[top].append(preview)
                    total += len(preview)
                break

            top_level = (r.get("hierarchy") or ["General"])[0]
            section_groups[top_level].append(chunk_text)
            total += len(chunk_text)

            if total >= max_chars:
                break

        blocks = []
        for section, chunks in section_groups.items():
            full = "\n\n".join(chunks).strip()
            if full:
                blocks.append(full)

        return "\n\n---\n\n".join(blocks).strip()
