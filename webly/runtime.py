from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from dotenv import load_dotenv

from webly.chatbot.chatgpt_model import ChatGPTModel
from webly.chatbot.prompts.system_prompts import apply_mode_flags, get_system_prompt
from webly.chatbot.webly_chat_agent import WeblyChatAgent
from webly.crawl.crawler import Crawler
from webly.observability.cost_tracker import CostTracker
from webly.pipeline.ingest_pipeline import IngestPipeline
from webly.pipeline.query_pipeline import QueryPipeline
from webly.project_config import ProjectConfig
from webly.query_result import QueryResult
from webly.vector_index.faiss_db import FaissDatabase
from webly.webcreeper.creeper_core.utils import configure_logging


@dataclass(slots=True)
class ProjectRuntime:
    config: ProjectConfig
    ingest_pipeline: IngestPipeline
    query_pipeline: QueryPipeline | None
    cost_tracker: CostTracker
    api_key: str | None = None

    @property
    def db(self):
        return self.ingest_pipeline.db

    def index_exists(self) -> bool:
        return (
            os.path.isdir(self.config.index_dir)
            and os.path.exists(os.path.join(self.config.index_dir, "embeddings.index"))
            and os.path.exists(os.path.join(self.config.index_dir, "metadata.json"))
        )

    def ensure_index_loaded(self) -> bool:
        if getattr(self.db, "index", None) is not None:
            return True
        if not self.index_exists():
            return False
        self.db.load(self.config.index_dir)
        return True

    def run_ingest(self, **kwargs):
        try:
            return self.ingest_pipeline.run(**kwargs)
        finally:
            self.cost_tracker.flush()

    def query(self, question: str, *, retry_on_empty: bool = False, memory_context: str = "") -> str:
        return self.query_result(
            question,
            retry_on_empty=retry_on_empty,
            memory_context=memory_context,
        ).answer

    def query_result(self, question: str, *, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        if self.query_pipeline is None:
            raise RuntimeError("Query pipeline is unavailable for this runtime.")
        if not self.ensure_index_loaded():
            raise FileNotFoundError(f"No index found at {self.config.index_dir}")
        try:
            return self.query_pipeline.query_result(
                question,
                retry_on_empty=retry_on_empty,
                memory_context=memory_context,
            )
        finally:
            self.cost_tracker.flush()


def build_runtime(config: Mapping[str, Any] | ProjectConfig, api_key: Optional[str] = None) -> ProjectRuntime:
    configure_logging("webly")
    load_dotenv()

    project_config = config if isinstance(config, ProjectConfig) else ProjectConfig.from_dict(config)
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    tracker = CostTracker(output_dir=project_config.output_dir)

    emb = project_config.embedding_model
    uses_openai_embedder = emb.startswith("openai:")
    uses_summary = bool(project_config.summary_model)

    if uses_openai_embedder:
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (required for OpenAI embeddings).")
        from webly.embedder.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder(
            model_name=emb.split(":", 1)[1],
            api_key=api_key,
            cache_dir=project_config.embedding_cache_dir or None,
            cost_tracker=tracker,
        )
    else:
        from webly.embedder.hf_sentence_embedder import HFSentenceEmbedder

        embedder = HFSentenceEmbedder(emb)

    db = FaissDatabase()
    chatbot = None
    if api_key:
        chatbot = ChatGPTModel(api_key=api_key, model=project_config.chat_model, cost_tracker=tracker)

    summarizer = None
    if uses_summary:
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (required for summarization).")
        from webly.processors.text_summarizer import TextSummarizer

        summary_llm = ChatGPTModel(
            api_key=api_key,
            model=project_config.summary_model,
            cost_tracker=tracker,
        )
        summarizer = TextSummarizer(
            llm=summary_llm,
            prompt_template="Summarize the following webpage clearly:\n\n{text}",
        )

    crawler = Crawler(
        start_url=project_config.start_url,
        allowed_domains=project_config.allowed_domains,
        output_dir=project_config.output_dir,
        results_filename=project_config.results_file,
        default_settings={
            "crawl_entire_website": project_config.crawl_entire_site,
            "max_depth": int(project_config.max_depth),
            "allowed_paths": project_config.allowed_paths,
            "blocked_paths": project_config.blocked_paths,
            "allow_url_patterns": project_config.allow_url_patterns,
            "block_url_patterns": project_config.block_url_patterns,
            "allow_subdomains": bool(project_config.allow_subdomains),
            "respect_robots": bool(project_config.respect_robots),
            "rate_limit_delay": float(project_config.rate_limit_delay),
            "seed_urls": project_config.seed_urls,
        },
    )

    ingest_pipeline = IngestPipeline(
        crawler=crawler,
        index_path=project_config.index_dir,
        embedder=embedder,
        db=db,
        summarizer=summarizer,
        use_summary=bool(summarizer),
        debug=bool(project_config.debug),
    )
    ingest_pipeline.cost_tracker = tracker

    query_pipeline = None
    if chatbot is not None:
        configured_system_prompt = get_system_prompt(
            project_config.answering_mode,
            project_config.system_prompt,
            bool(project_config.system_prompt_custom_override),
        )
        configured_system_prompt = apply_mode_flags(
            project_config.answering_mode,
            configured_system_prompt,
            bool(project_config.allow_generated_examples),
        )
        agent = WeblyChatAgent(embedder, db, chatbot, system_prompt=configured_system_prompt)
        query_pipeline = QueryPipeline(
            chat_agent=agent,
            debug=bool(project_config.query_debug),
            allow_best_effort=True,
            retrieval_mode=str(project_config.retrieval_mode),
            builder_max_rounds=int(project_config.builder_max_rounds),
            score_threshold=float(project_config.score_threshold),
        )

    return ProjectRuntime(
        config=project_config,
        ingest_pipeline=ingest_pipeline,
        query_pipeline=query_pipeline,
        cost_tracker=tracker,
        api_key=api_key,
    )
