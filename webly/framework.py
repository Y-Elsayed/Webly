import os
from typing import List, Optional

from dotenv import load_dotenv

from webly.chatbot.chatgpt_model import ChatGPTModel
from webly.chatbot.prompts.system_prompts import apply_mode_flags, get_system_prompt
from webly.chatbot.webly_chat_agent import WeblyChatAgent
from webly.crawl.crawler import Crawler
from webly.pipeline.ingest_pipeline import IngestPipeline
from webly.pipeline.query_pipeline import QueryPipeline
from webly.vector_index.faiss_db import FaissDatabase

try:
    from typing import Required, TypedDict

    class PipelineConfig(TypedDict, total=False):
        """Typed configuration dict for :func:`build_pipelines`.

        Required keys
        -------------
        start_url : str
            The URL the crawler starts from.
        output_dir : str
            Directory where ``results.jsonl``, ``graph.json``, and debug
            files are written.
        index_dir : str
            Directory where FAISS index files are saved and loaded from.

        Crawl settings
        --------------
        allowed_domains : List[str]
            Domains the crawler may visit. Auto-derived from *start_url*
            if omitted.
        crawl_entire_site : bool
            When ``True`` (default), follow all links within allowed domains.
        max_depth : int
            Maximum link-following depth. ``-1`` means unlimited.
        allow_subdomains : bool
            Allow crawling subdomains of the allowed domains.
        respect_robots : bool
            Honour ``robots.txt`` directives (default ``True``).
        rate_limit_delay : float
            Seconds to wait between requests to the same host.
        allowed_paths : List[str]
            URL path prefixes to include (e.g. ``["/docs"]``).
        blocked_paths : List[str]
            URL path prefixes to exclude.
        allow_url_patterns : List[str]
            Regex patterns. Only matching URLs are crawled.
        block_url_patterns : List[str]
            Regex patterns. Matching URLs are skipped.
        seed_urls : List[str]
            Explicit list of URLs to crawl (used instead of link-following).
        results_file : str
            Filename for the raw crawl output (default ``"results.jsonl"``).

        Embedding settings
        ------------------
        embedding_model : str
            Model identifier. Use ``"sentence-transformers/<name>"`` for
            local HuggingFace models or ``"openai:<model>"`` for OpenAI.
            Default: ``"openai:text-embedding-3-small"``.

        Chat / LLM settings
        -------------------
        chat_model : str
            OpenAI model name for the chat agent (default ``"gpt-4o-mini"``).
        summary_model : str
            Optional OpenAI model for page summarisation. Leave blank to
            embed raw chunked text instead.
        answering_mode : str
            One of ``"strict_grounded"``, ``"technical_grounded"``
            (default), or ``"assisted_examples"``.
        system_prompt : str
            Custom system prompt. Only used when
            *system_prompt_custom_override* is ``True``.
        system_prompt_custom_override : bool
            When ``True``, *system_prompt* replaces the mode default.
        allow_generated_examples : bool
            Allow the LLM to add generated examples (only in
            ``"assisted_examples"`` mode).

        Retrieval settings
        ------------------
        retrieval_mode : str
            ``"builder"`` (default) or ``"classic"``.
        builder_max_rounds : int
            Follow-up retrieval rounds in builder mode (default ``1``).
        leave_last_k : int
            Number of recent Q/A pairs to include as memory context.
        score_threshold : float
            Minimum cosine similarity score for retrieved chunks.

        Debug
        -----
        debug : bool
            Enable verbose debug logging for the ingest pipeline.
        query_debug : bool
            Enable verbose debug logging for the query pipeline.
        """

        start_url: Required[str]
        output_dir: Required[str]
        index_dir: Required[str]
        allowed_domains: List[str]
        crawl_entire_site: bool
        max_depth: int
        allow_subdomains: bool
        respect_robots: bool
        rate_limit_delay: float
        allowed_paths: List[str]
        blocked_paths: List[str]
        allow_url_patterns: List[str]
        block_url_patterns: List[str]
        seed_urls: List[str]
        results_file: str
        embedding_model: str
        chat_model: str
        summary_model: str
        answering_mode: str
        system_prompt: str
        system_prompt_custom_override: bool
        allow_generated_examples: bool
        retrieval_mode: str
        builder_max_rounds: int
        leave_last_k: int
        score_threshold: float
        debug: bool
        query_debug: bool

except ImportError:
    PipelineConfig = dict  # type: ignore[misc,assignment]


def build_pipelines(config: "PipelineConfig", api_key: Optional[str] = None):
    load_dotenv()
    api_key = api_key or os.getenv("OPENAI_API_KEY")

    emb = (config.get("embedding_model") or "").strip()
    if emb.lower() in ("", "default"):
        emb = "openai:text-embedding-3-small"
        config["embedding_model"] = emb

    chat = (config.get("chat_model") or "").strip()
    if chat.lower() in ("", "default"):
        chat = "gpt-4o-mini"
        config["chat_model"] = chat

    uses_openai_embedder = emb.startswith("openai:")
    uses_summary = bool(config.get("summary_model"))

    if uses_openai_embedder:
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (required for OpenAI embeddings).")
        from webly.embedder.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder(model_name=emb.split(":", 1)[1], api_key=api_key)
    else:
        from webly.embedder.hf_sentence_embedder import HFSentenceEmbedder

        embedder = HFSentenceEmbedder(emb)

    db = FaissDatabase()
    chatbot = None
    if api_key:
        chatbot = ChatGPTModel(api_key=api_key, model=config.get("chat_model", "gpt-4o-mini"))

    summarizer = None
    if uses_summary:
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (required for summarization).")
        from webly.processors.text_summarizer import TextSummarizer

        summary_llm = ChatGPTModel(api_key=api_key, model=config["summary_model"])
        summarizer = TextSummarizer(
            llm=summary_llm,
            prompt_template="Summarize the following webpage clearly:\n\n{text}",
        )

    crawler = Crawler(
        start_url=config["start_url"],
        allowed_domains=config.get("allowed_domains", []),
        output_dir=config["output_dir"],
        results_filename=config.get("results_file", "results.jsonl"),
        default_settings={
            "crawl_entire_website": config.get("crawl_entire_site", True),
            "max_depth": int(config.get("max_depth", 3)),
            "allowed_paths": config.get("allowed_paths", []),
            "blocked_paths": config.get("blocked_paths", []),
            "allow_url_patterns": config.get("allow_url_patterns", []),
            "block_url_patterns": config.get("block_url_patterns", []),
            "allow_subdomains": bool(config.get("allow_subdomains", False)),
            "respect_robots": bool(config.get("respect_robots", True)),
            "rate_limit_delay": float(config.get("rate_limit_delay", 0.2)),
            "seed_urls": config.get("seed_urls", []),
        },
    )

    ingest_pipeline = IngestPipeline(
        crawler=crawler,
        index_path=config["index_dir"],
        embedder=embedder,
        db=db,
        summarizer=summarizer,
        use_summary=bool(summarizer),
        debug=bool(config.get("debug", False)),
    )

    query_pipeline = None
    if chatbot is not None:
        mode = str(config.get("answering_mode", "technical_grounded"))
        custom_text = config.get("system_prompt") or ""
        custom_override = bool(config.get("system_prompt_custom_override", False))
        allow_generated_examples = bool(config.get("allow_generated_examples", False))
        configured_system_prompt = get_system_prompt(mode, custom_text, custom_override)
        configured_system_prompt = apply_mode_flags(mode, configured_system_prompt, allow_generated_examples)
        agent = WeblyChatAgent(embedder, db, chatbot, system_prompt=configured_system_prompt)
        query_pipeline = QueryPipeline(
            chat_agent=agent,
            debug=bool(config.get("query_debug", False)),
            allow_best_effort=True,
            retrieval_mode=str(config.get("retrieval_mode", "builder")),
            builder_max_rounds=int(config.get("builder_max_rounds", 1)),
        )

    return ingest_pipeline, query_pipeline
