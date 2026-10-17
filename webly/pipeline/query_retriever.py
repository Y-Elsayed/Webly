from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from logging import Logger
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class QueryRetriever:
    def __init__(
        self,
        chat_agent,
        *,
        logger: Logger,
        enable_hybrid: bool = True,
        anchor_boost: float = 0.10,
        section_boost: float = 0.05,
        score_threshold: float = 0.0,
    ):
        self.chat_agent = chat_agent
        self.logger = logger
        self.enable_hybrid = enable_hybrid
        self.anchor_boost = anchor_boost
        self.section_boost = section_boost
        self.score_threshold = max(0.0, float(score_threshold or 0.0))

        self._bm25_ready = False
        self._bm25_docs: List[List[str]] = []
        self._bm25_doc_ids: List[Dict[str, Any]] = []
        self._bm25_avgdl = 0.0
        self._bm25_df = defaultdict(int)
        self._bm25_idf: Dict[str, float] = {}
        self._bm25_k1 = 1.5
        self._bm25_b = 0.75

    def search(self, query: Optional[Union[str, List[str]]], k: int, tag: str) -> List[Dict[str, Any]]:
        if not query:
            return []
        queries = [query] if isinstance(query, str) else list(query)
        all_results: List[Dict[str, Any]] = []
        for q in queries:
            q_emb = self.chat_agent.embedder.embed(q)
            results = self.chat_agent.vector_db.search(q_emb, top_k=k) or []
            if self.score_threshold > 0.0:
                results = [
                    record
                    for record in results
                    if float(record.get("score") or 0.0) >= self.score_threshold
                ]
            for i, record in enumerate(results):
                record = record.copy()
                record["_meta_rank"] = i + 1
                record["_origin"] = tag
                record["_channel"] = "semantic"
                record["_score_vec"] = float(record.get("score") or 0.0)
                results[i] = record
            all_results.extend(results)

            if self.enable_hybrid:
                bm25_hits = self._bm25_search(q, top_k=max(8, k))
                for i, record in enumerate(bm25_hits):
                    record["_meta_rank"] = i + 1
                    record["_origin"] = f"{tag}-bm25"
                    record["_channel"] = "lexical"
                all_results.extend(bm25_hits)
        return all_results

    def collect_hints_for_rewrite(self, results: List[Dict[str, Any]]) -> List[str]:
        hints: List[str] = []
        for record in results[:8]:
            if record.get("hierarchy"):
                hints.append(" > ".join(record["hierarchy"]))
            for incoming in record.get("metadata", {}).get("incoming_links") or []:
                if incoming.get("anchor_text"):
                    hints.append(incoming["anchor_text"])
        return [hint for hint in hints if hint]

    def expand_via_graph(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        expansions: List[Dict[str, Any]] = []
        seen_queries = set()

        for record in seeds[:12]:
            incoming_links = (record.get("metadata", {}) or {}).get("incoming_links") or []
            for incoming in incoming_links[:5]:
                anchor = (incoming.get("anchor_text") or "").strip()
                if not anchor:
                    continue
                query = f"{anchor} {question}".strip()
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                results = self.search(query, k=3, tag="graph-anchor")
                for expansion in results:
                    expansion.setdefault("_boost_reason", "anchor")
                expansions.extend(results)
        return expansions

    def expand_via_section(self, question: str, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        expansions: List[Dict[str, Any]] = []
        seen_queries = set()

        for record in seeds[:10]:
            top_heading = None
            if isinstance(record.get("hierarchy"), list) and record["hierarchy"]:
                top_heading = record["hierarchy"][0]
            if not top_heading:
                continue

            query = f"{question} {top_heading}"
            if query in seen_queries:
                continue
            seen_queries.add(query)

            results = self.search(query, k=3, tag="section")
            for expansion in results:
                expansion.setdefault("_boost_reason", "section")
            expansions.extend(results)
        return expansions

    def combine_and_rerank(self, *result_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: List[List[Dict[str, Any]]] = []
        if len(result_groups) == 1 and isinstance(result_groups[0], list):
            groups = [result_groups[0]]
        else:
            groups = list(result_groups)

        by_id: Dict[str, Dict[str, Any]] = {}
        for group in groups:
            for record in group:
                record_id = record.get("segment_id") or record.get("id")
                if not isinstance(record_id, str) or not record_id:
                    continue
                channel = record.get("_channel") or ("lexical" if record.get("_score_bm25") else "semantic")
                origin = str(record.get("_origin") or "initial")
                rank = max(1, int(record.get("_meta_rank", 1)))
                entry = by_id.setdefault(
                    record_id, {**record, "id": record_id, "segment_id": record_id, "channel_ranks": {}}
                )
                ranks = entry["channel_ranks"]
                key = f"{origin}:{channel}"
                ranks[key] = min(rank, ranks.get(key, rank))
                if channel == "lexical":
                    entry["_score_bm25"] = max(
                        float(record.get("_score_bm25") or 0), float(entry.get("_score_bm25") or 0)
                    )
                else:
                    entry["_score_vec"] = max(
                        float(record.get("_score_vec") or record.get("score") or 0),
                        float(entry.get("_score_vec") or 0),
                    )
        for entry in by_id.values():
            entry["fusion_score"] = sum(1.0 / (60 + rank) for rank in entry["channel_ranks"].values())
        return sorted(by_id.values(), key=lambda entry: (-entry["fusion_score"], entry["segment_id"]))

    def _tokenize(self, text: str) -> List[str]:
        normalized = unicodedata.normalize("NFKC", text or "").casefold()
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.findall(r"[^\W_]{2,}", normalized, flags=re.UNICODE)

    def _ensure_bm25(self) -> None:
        if self._bm25_ready:
            return
        docs = []
        doc_ids = []
        for record in self.chat_agent.vector_db.metadata or []:
            text = record.get("text") or record.get("summary") or ""
            if not text:
                continue
            tokens = self._tokenize(text)
            if not tokens:
                continue
            docs.append(tokens)
            doc_ids.append(record)

        self._bm25_docs = docs
        self._bm25_doc_ids = doc_ids
        if not docs:
            self._bm25_ready = True
            return

        df = defaultdict(int)
        total_len = 0
        for doc in docs:
            total_len += len(doc)
            for token in set(doc):
                df[token] += 1
        self._bm25_df = df
        self._bm25_avgdl = total_len / max(len(docs), 1)
        n_docs = len(docs)
        self._bm25_idf = {
            token: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
            for token, freq in df.items()
        }
        self._bm25_ready = True

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        self._ensure_bm25()
        if not self._bm25_docs:
            return []

        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        scores = []
        for index, doc in enumerate(self._bm25_docs):
            doc_len = len(doc)
            tf = defaultdict(int)
            for token in doc:
                tf[token] += 1
            score = 0.0
            for token in query_terms:
                if token not in tf:
                    continue
                idf = self._bm25_idf.get(token, 0.0)
                denom = tf[token] + self._bm25_k1 * (
                    1 - self._bm25_b + self._bm25_b * (doc_len / self._bm25_avgdl)
                )
                score += idf * (tf[token] * (self._bm25_k1 + 1) / denom)
            scores.append((score, index))

        scores.sort(key=lambda item: item[0], reverse=True)
        hits = []
        for score, index in scores[:top_k]:
            if score <= 0:
                continue
            record = self._bm25_doc_ids[index].copy()
            record["_score_bm25"] = float(score)
            hits.append(record)
        return hits

    def _normalize_for_dedupe(self, url: str) -> str:
        try:
            parsed = urlparse(url)
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
            kept = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in drop
            ]
            kept.sort()
            scheme = (parsed.scheme or "https").lower()
            netloc = (parsed.netloc or "").lower()
            path = (parsed.path or "/").rstrip("/") or "/"
            return urlunparse((scheme, netloc, path, "", urlencode(kept), ""))
        except Exception as exc:
            self.logger.debug(f"URL normalization failed, returning input unchanged: {exc}")
            return url or ""
