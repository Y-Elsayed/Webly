from __future__ import annotations

import os

from webly.query_result import QueryResult
from webly.runtime import build_runtime
from webly.service.errors import BadRequestError, NotFoundError, ServiceUnavailableError
from webly.storage.project_repository import FileProjectRepository


class RuntimeService:
    def __init__(self, projects: FileProjectRepository):
        self.projects = projects

    @staticmethod
    def _require_query_ready(status: dict) -> None:
        if not status["capabilities"]["query_pipeline_available"]:
            raise ServiceUnavailableError("OPENAI_API_KEY is required for query and chat responses.")
        if not status["index_ready"]:
            raise ServiceUnavailableError("Index files are missing. Run ingest before querying.")

    @staticmethod
    def _require_ingest_ready(status: dict) -> None:
        if not status["capabilities"]["ingest_pipeline_available"]:
            raise ServiceUnavailableError(
                "OPENAI_API_KEY is required for ingest when using OpenAI embeddings or summarization."
            )

    def build_project_runtime(self, project: str):
        safe_name = self.projects.sanitize_name(project, "project name")
        if not os.path.exists(self.projects.get_paths(safe_name).config):
            raise NotFoundError(f"Project not found: {safe_name}")
        config = self.projects.load(safe_name)
        try:
            return build_runtime(config)
        except RuntimeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc

    def query_project(self, project: str, *, question: str, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        status = self.status(project)
        self._require_query_ready(status)
        runtime = self.build_project_runtime(project)
        try:
            return runtime.query_result(
                question,
                retry_on_empty=retry_on_empty,
                memory_context=memory_context,
            )
        except FileNotFoundError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        except RuntimeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc

    def run_ingest(self, project: str, *, mode: str = "both", force_crawl: bool = False) -> dict:
        status = self.status(project)
        self._require_ingest_ready(status)
        runtime = self.build_project_runtime(project)
        try:
            return runtime.run_ingest(mode=mode, force_crawl=force_crawl)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        except RuntimeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc

    def status(self, project: str) -> dict:
        safe_name = self.projects.sanitize_name(project, "project name")
        if not os.path.exists(self.projects.get_paths(safe_name).config):
            raise NotFoundError(f"Project not found: {safe_name}")
        config = self.projects.load(safe_name)
        results_path = os.path.join(config.output_dir, config.results_file)
        results_ready = os.path.exists(results_path) and os.path.getsize(results_path) > 0
        index_ready = (
            os.path.isdir(config.index_dir)
            and os.path.exists(os.path.join(config.index_dir, "embeddings.index"))
            and os.path.exists(os.path.join(config.index_dir, "metadata.json"))
        )
        uses_openai_embeddings = config.embedding_model.startswith("openai:")
        uses_summary_model = bool(config.summary_model)
        has_openai_api_key = bool(os.getenv("OPENAI_API_KEY"))
        requires_openai_for_ingest = uses_openai_embeddings or uses_summary_model
        requires_openai_for_query = True
        ingest_pipeline_available = has_openai_api_key or not requires_openai_for_ingest
        query_pipeline_available = has_openai_api_key and requires_openai_for_query
        blockers: list[str] = []
        if requires_openai_for_ingest and not has_openai_api_key:
            blockers.append("OPENAI_API_KEY is required for ingest when using OpenAI embeddings or summarization.")
        if requires_openai_for_query and not has_openai_api_key:
            blockers.append("OPENAI_API_KEY is required for query and chat responses.")
        if not index_ready:
            blockers.append("Index files are missing. Run ingest before querying.")
        return {
            "config": config,
            "paths": self.projects.get_paths(project),
            "results_ready": results_ready,
            "index_ready": index_ready,
            "query_ready": index_ready and query_pipeline_available,
            "chat_ready": query_pipeline_available,
            "capabilities": {
                "has_openai_api_key": has_openai_api_key,
                "uses_openai_embeddings": uses_openai_embeddings,
                "uses_summary_model": uses_summary_model,
                "requires_openai_for_ingest": requires_openai_for_ingest,
                "requires_openai_for_query": requires_openai_for_query,
                "ingest_pipeline_available": ingest_pipeline_available,
                "query_pipeline_available": query_pipeline_available,
                "blockers": blockers,
            },
        }
