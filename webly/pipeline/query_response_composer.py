from __future__ import annotations

from typing import Any, Dict, List, Tuple

from webly.pipeline.query_context import QueryContextTools


class QueryResponseComposer:
    def __init__(self, chat_agent, context_tools: QueryContextTools, *, max_context_chars: int):
        self.chat_agent = chat_agent
        self.context_tools = context_tools
        self.max_context_chars = max_context_chars

    def fallback_payload(self, results: List[Dict[str, Any]], question: str) -> Tuple[str, bool, List[Dict[str, str]]]:
        if not results:
            return "I couldn't find anything on this site related to your question.", False, []

        context, used_sources = self.context_tools.assemble_context(
            results[: min(8, len(results))],
            max_chars=min(self.max_context_chars, 8000),
        )
        _, supported = self.chat_agent.answer_with_support(question, context)
        if supported != "Y":
            return "I couldn't find enough information on this site to answer that directly.", False, used_sources

        links: List[str] = []
        seen = set()
        for record in results:
            url = record.get("url") or record.get("source")
            if not url or url in seen:
                continue
            seen.add(url)
            section = " > ".join(record.get("hierarchy", [])[:2]) if record.get("hierarchy") else None
            if section:
                links.append(f"- {section}: {url}")
            else:
                links.append(f"- {url}")
            if len(links) >= 3:
                break

        if not links:
            return "I couldn't find enough relevant information here to answer that.", False, used_sources

        return (
            "I couldn't find enough information on this site to answer that directly. "
            "These pages may help:\n" + "\n".join(links),
            False,
            used_sources,
        )

    def best_effort_payload(
        self,
        question_for_answer: str,
        context: str,
        coverage: Dict[str, List[str]],
        used_sources: List[Dict[str, str]],
    ) -> Tuple[str, bool]:
        missing = coverage.get("missing") or []
        used_urls = self.context_tools.read_more_urls_from_used_sources(used_sources, limit=3)

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
            return base_answer, str(supported).upper() == "Y"
        if str(supported).upper() != "Y":
            return base_answer, False

        lines = ["Read more:"]
        for url in used_urls:
            lines.append(f"- {url}")
        return f"{base_answer}\n\n" + "\n".join(lines), True
