from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from webly.pipeline.query_pipeline import QueryPipeline
from webly.query_result import QueryResult


def _default_answer(_question: str, _context: str) -> str:
    return "Default answer"


def _default_answer_with_support(question: str, context: str) -> tuple[str, str]:
    return _default_answer(question, context), "Y"


def _default_rewrite(_question: str, _hints) -> str | None:
    return None


def _default_judge(_question: str, context: str) -> bool:
    return bool((context or "").strip())


@dataclass(slots=True)
class ScriptedPlanner:
    route_payload: dict[str, object] = field(default_factory=lambda: {"mode": "retrieve_new", "standalone_query": "", "concepts": []})
    extracted_concepts: list[str] = field(default_factory=list)
    followup_payload: dict[str, list[str]] = field(default_factory=lambda: {"queries": [], "drop_chunk_ids": []})
    transform_response: str = "Transformed answer"

    def generate(self, prompt: str) -> str:
        if "Task: route the request and extract concepts." in prompt:
            return json.dumps(
                {
                    "mode": self.route_payload.get("mode", "retrieve_new"),
                    "standalone_query": self.route_payload.get("standalone_query", ""),
                    "concepts": list(self.route_payload.get("concepts", [])),
                }
            )
        if "Task: extract core concepts from user query." in prompt:
            return json.dumps({"concepts": list(self.extracted_concepts)})
        if "Task: propose minimal follow-up retrieval actions." in prompt:
            return json.dumps(
                {
                    "queries": list(self.followup_payload.get("queries", [])),
                    "drop_chunk_ids": list(self.followup_payload.get("drop_chunk_ids", [])),
                }
            )
        if "You are transforming a prior answer." in prompt:
            return self.transform_response
        return "OK"


class ScriptedEmbedder:
    def embed(self, text: str):
        return text


class ScriptedVectorDb:
    def __init__(self, results_by_query: dict[str, list[dict]], metadata: list[dict] | None = None):
        self.results_by_query = {key: deepcopy(value) for key, value in results_by_query.items()}
        self.metadata = list(metadata or [])

    def search(self, query_embedding, top_k: int = 5):
        return deepcopy(self.results_by_query.get(query_embedding, []))[:top_k]


class ScriptedChatAgent:
    def __init__(
        self,
        *,
        results_by_query: dict[str, list[dict]],
        planner: ScriptedPlanner | None = None,
        answer_fn: Callable[[str, str], str] | None = None,
        answer_with_support_fn: Callable[[str, str], tuple[str, str]] | None = None,
        rewrite_fn: Callable[[str, list[str]], str | None] | None = None,
        judge_fn: Callable[[str, str], bool] | None = None,
        metadata: list[dict] | None = None,
    ):
        self.top_k = 5
        self.chatbot = planner or ScriptedPlanner()
        self.embedder = ScriptedEmbedder()
        self.vector_db = ScriptedVectorDb(results_by_query, metadata=metadata)
        self._answer_fn = answer_fn or _default_answer
        self._answer_with_support_fn = answer_with_support_fn or _default_answer_with_support
        self._rewrite_fn = rewrite_fn or _default_rewrite
        self._judge_fn = judge_fn or _default_judge

    def answer(self, question: str, context: str) -> str:
        return self._answer_fn(question, context)

    def answer_with_support(self, question: str, context: str) -> tuple[str, str]:
        return self._answer_with_support_fn(question, context)

    def rewrite_query(self, question: str, hints):
        return self._rewrite_fn(question, hints)

    def _judge_answerability(self, question: str, context: str) -> bool:
        return self._judge_fn(question, context)


def run_query_case(
    *,
    results_by_query: dict[str, list[dict]],
    question: str,
    retrieval_mode: str,
    memory_context: str = "",
    planner: ScriptedPlanner | None = None,
    answer_fn: Callable[[str, str], str] | None = None,
    answer_with_support_fn: Callable[[str, str], tuple[str, str]] | None = None,
    rewrite_fn: Callable[[str, list[str]], str | None] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    **pipeline_kwargs,
) -> QueryResult:
    agent = ScriptedChatAgent(
        results_by_query=results_by_query,
        planner=planner,
        answer_fn=answer_fn,
        answer_with_support_fn=answer_with_support_fn,
        rewrite_fn=rewrite_fn,
        judge_fn=judge_fn,
    )
    pipeline = QueryPipeline(
        chat_agent=agent,
        retrieval_mode=retrieval_mode,
        **pipeline_kwargs,
    )
    return pipeline.query_result(question, memory_context=memory_context)
