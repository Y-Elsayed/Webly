from __future__ import annotations

import os

from webly.query_result import QueryResult
from webly.runtime import build_runtime
from webly.storage.project_repository import FileProjectRepository


class RuntimeService:
    def __init__(self, projects: FileProjectRepository):
        self.projects = projects

    def build_project_runtime(self, project: str):
        safe_name = self.projects.sanitize_name(project, "project name")
        if not os.path.exists(self.projects.get_paths(safe_name).config):
            raise FileNotFoundError(f"Project not found: {safe_name}")
        config = self.projects.load(safe_name)
        return build_runtime(config)

    def query_project(self, project: str, *, question: str, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        runtime = self.build_project_runtime(project)
        return runtime.query_result(
            question,
            retry_on_empty=retry_on_empty,
            memory_context=memory_context,
        )

    def run_ingest(self, project: str, *, mode: str = "both", force_crawl: bool = False) -> dict:
        runtime = self.build_project_runtime(project)
        return runtime.run_ingest(mode=mode, force_crawl=force_crawl)

    def status(self, project: str) -> dict:
        safe_name = self.projects.sanitize_name(project, "project name")
        if not os.path.exists(self.projects.get_paths(safe_name).config):
            raise FileNotFoundError(f"Project not found: {safe_name}")
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
        query_pipeline_available = has_openai_api_key
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
                "query_pipeline_available": query_pipeline_available,
            },
        }
