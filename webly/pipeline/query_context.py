from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from webly.query_result import SourceRef


class QueryContextTools:
    def assemble_context(
        self,
        results: List[Dict[str, Any]],
        *,
        max_chars: int,
    ) -> Tuple[str, List[Dict[str, str]]]:
        section_groups: Dict[str, List[str]] = defaultdict(list)
        seen_ids = set()
        total = 0
        used_sources: List[Dict[str, str]] = []

        for record in results:
            uid = record.get("id") or f"{record.get('url', '')}#chunk_{record.get('chunk_index', -1)}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            text = (record.get("text") or "").strip()
            if not text:
                continue

            url = record.get("url") or record.get("source", "N/A")
            subheadings = " > ".join(record.get("hierarchy", [])) if record.get("hierarchy") else ""
            prefix = f"[{subheadings}]\n" if subheadings else ""
            chunk_text = f"{prefix}{text}\n\n(Source: {url})"

            if total + len(chunk_text) > max_chars:
                remaining = max(0, max_chars - total)
                preview = chunk_text[:remaining]
                if preview:
                    top = (record.get("hierarchy") or ["General"])[0]
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

            top_level = (record.get("hierarchy") or ["General"])[0]
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
        return "\n\n---\n\n".join(blocks).strip(), used_sources

    def compute_budget_chars(self, chat_agent, *, max_context_chars: int) -> int:
        base = max(max_context_chars, 8000)
        chatbot = getattr(chat_agent, "chatbot", None)
        context_window = getattr(chatbot, "context_window_tokens", None)

        if isinstance(context_window, int) and context_window > 0:
            reserve_tokens = max(2000, int(context_window * 0.15))
            usable_tokens = max(2000, context_window - reserve_tokens)
            return max(base, min(int(usable_tokens * 4), 180000))

        model_name = (getattr(chatbot, "model_name", None) or getattr(chatbot, "model", "")).lower()
        if "gpt-4o" in model_name or "4o" in model_name or "gpt-4.1" in model_name:
            return min(int(base * 5), 100000)
        return base

    def current_sources(self, used_sources: List[Dict[str, str]]) -> List[SourceRef]:
        sources: List[SourceRef] = []
        seen: set[tuple[str, str]] = set()
        for item in used_sources:
            url = str(item.get("url") or "").strip()
            chunk_id = str(item.get("chunk_id") or "").strip()
            if not url or not chunk_id:
                continue
            key = (chunk_id, url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                SourceRef(
                    chunk_id=chunk_id,
                    url=url,
                    section=str(item.get("section") or ""),
                )
            )
        return sources

    def read_more_urls_from_used_sources(self, used_sources: List[Dict[str, str]], *, limit: int = 3) -> List[str]:
        links = []
        seen = set()
        for src in used_sources:
            url = str(src.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            links.append(url)
            if len(links) >= limit:
                break
        return links

    def helpful_links_by_concept(
        self,
        concepts: List[str],
        results: List[Dict[str, Any]],
        *,
        max_links_per_concept: int = 2,
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
            for record in results[:20]:
                url = record.get("url") or record.get("source")
                if not url or url in seen:
                    continue
                text = (record.get("text") or "").lower()
                hierarchy = " ".join(record.get("hierarchy") or []).lower()
                if needle in text or needle in hierarchy or needle in url.lower():
                    seen.add(url)
                    links.append(url)
                if len(links) >= max_links_per_concept:
                    break
            if links:
                out[concept] = links
        return out

    def top_distinct_urls(self, results: List[Dict[str, Any]], *, limit: int = 3) -> List[str]:
        links = []
        seen = set()
        for record in results:
            url = record.get("url") or record.get("source")
            if not url or url in seen:
                continue
            seen.add(url)
            links.append(url)
            if len(links) >= limit:
                break
        return links

    def extract_used_urls_from_context(self, context: str) -> List[str]:
        links = []
        seen = set()
        for url in re.findall(r"\(Source:\s*(https?://[^\s\)]+)\)", context or ""):
            if url in seen:
                continue
            seen.add(url)
            links.append(url)
        return links
