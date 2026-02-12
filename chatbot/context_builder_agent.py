import json
import re
from pathlib import Path
from typing import Dict, List, Optional


class ContextBuilderAgent:
    """
    LLM-driven context builder helper.

    It parses core concepts from a query, checks concept coverage in retrieved
    chunks, and asks the LLM for follow-up retrieval actions.
    """

    def __init__(self, planner_llm=None, prompt_path: str | None = None):
        default_path = Path(__file__).resolve().parent / "prompts" / "context_builder_agent.txt"
        self.prompt_path = Path(prompt_path) if prompt_path else default_path
        self.prompt_text = self._load_prompt()
        self.planner_llm = planner_llm

    def _load_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8")
        except Exception:
            return "Context builder prompt unavailable."

    def _extract_json_payload(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return None
            try:
                return json.loads(m.group(0))
            except Exception:
                return None

    def plan_initial_route(self, question: str, memory_context: str = "") -> Dict[str, object]:
        """
        Decide how to handle the query at the first planner touchpoint.

        Returns:
        - mode: one of {"transform_only", "retrieve_followup", "retrieve_new"}
        - standalone_query: optional retrieval-ready rewrite
        - concepts: optional concept list
        """
        if self.planner_llm is None:
            return {"mode": "retrieve_new", "standalone_query": "", "concepts": []}

        mem = (memory_context or "").strip()
        prompt = (
            f"{self.prompt_text}\n\n"
            "Task: route the request and extract concepts.\n"
            "Return JSON only in this shape:\n"
            '{"mode":"retrieve_new","standalone_query":"","concepts":["..."]}\n'
            "- mode must be one of: transform_only, retrieve_followup, retrieve_new\n"
            "- transform_only: user asks to reformat/rewrite previous answer without new facts\n"
            "- retrieve_followup: user refers to previous context but needs retrieval\n"
            "- retrieve_new: unrelated new question\n"
            "- standalone_query: non-empty only when mode=retrieve_followup\n\n"
            f"User query: {question}\n"
            f"Memory context:\n{mem[:1800]}"
        )
        raw = self.planner_llm.generate(prompt)
        data = self._extract_json_payload(raw or "")
        if not isinstance(data, dict):
            return {"mode": "retrieve_new", "standalone_query": "", "concepts": []}

        mode = str(data.get("mode") or "retrieve_new").strip().lower()
        if mode not in {"transform_only", "retrieve_followup", "retrieve_new"}:
            mode = "retrieve_new"
        standalone_query = str(data.get("standalone_query") or "").strip()
        concepts = data.get("concepts") if isinstance(data.get("concepts"), list) else []

        cleaned_concepts = []
        seen = set()
        for c in concepts:
            if not isinstance(c, str):
                continue
            x = c.strip().lower()
            if len(x) < 3 or x in seen:
                continue
            seen.add(x)
            cleaned_concepts.append(x)
        return {"mode": mode, "standalone_query": standalone_query, "concepts": cleaned_concepts[:6]}

    def extract_concepts(self, question: str) -> List[str]:
        if self.planner_llm is None:
            return []
        prompt = (
            f"{self.prompt_text}\n\n"
            "Task: extract core concepts from user query.\n"
            "Return JSON only in this shape:\n"
            '{"concepts": ["..."]}\n\n'
            f"User query: {question}"
        )
        raw = self.planner_llm.generate(prompt)
        data = self._extract_json_payload(raw or "")
        if not isinstance(data, dict):
            return []
        concepts = data.get("concepts")
        if not isinstance(concepts, list):
            return []

        cleaned = []
        seen = set()
        for c in concepts:
            if not isinstance(c, str):
                continue
            x = c.strip().lower()
            if len(x) < 3 or x in seen:
                continue
            seen.add(x)
            cleaned.append(x)
        return cleaned[:6]

    def coverage_report(self, concepts: List[str], results: List[Dict], max_chunks: int = 10) -> Dict[str, List[str]]:
        text = "\n".join((r.get("text") or "") for r in results[:max_chunks]).lower()
        covered = [c for c in concepts if c in text]
        missing = [c for c in concepts if c not in text]
        return {"covered": covered, "missing": missing}

    def decide_followups(self, question: str, missing_concepts: List[str], results: List[Dict]) -> Dict[str, List[str]]:
        if self.planner_llm is None:
            return {"queries": [], "drop_chunk_ids": []}

        snippet_lines = []
        for r in results[:8]:
            rid = r.get("id") or f"{r.get('url', '')}#chunk_{r.get('chunk_index', -1)}"
            txt = (r.get("text") or "").strip().replace("\n", " ")
            snippet_lines.append(f"- id={rid} url={r.get('url', '')} text={txt[:220]}")
        snippets = "\n".join(snippet_lines)

        prompt = (
            f"{self.prompt_text}\n\n"
            "Task: propose minimal follow-up retrieval actions.\n"
            "Return JSON only in this shape:\n"
            '{"queries": ["..."], "drop_chunk_ids": ["..."]}\n'
            "- queries: up to 4 focused follow-up searches\n"
            "- drop_chunk_ids: optional low-signal chunk ids to remove\n\n"
            f"User query: {question}\n"
            f"Missing concepts: {missing_concepts}\n"
            f"Current chunks:\n{snippets}"
        )
        raw = self.planner_llm.generate(prompt)
        data = self._extract_json_payload(raw or "")
        if not isinstance(data, dict):
            return {"queries": [], "drop_chunk_ids": []}

        queries = data.get("queries") if isinstance(data.get("queries"), list) else []
        drop_ids = data.get("drop_chunk_ids") if isinstance(data.get("drop_chunk_ids"), list) else []
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()][:4]
        drop_ids = [d.strip() for d in drop_ids if isinstance(d, str) and d.strip()][:8]
        return {"queries": queries, "drop_chunk_ids": drop_ids}
