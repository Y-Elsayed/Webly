import os
from typing import List, Optional

from dotenv import load_dotenv

from webly.runtime import build_runtime

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
        embedding_cache_dir: str

except ImportError:
    PipelineConfig = dict  # type: ignore[misc,assignment]


def build_pipelines(config: "PipelineConfig", api_key: Optional[str] = None):
    load_dotenv()
    runtime = build_runtime(config, api_key=api_key or os.getenv("OPENAI_API_KEY"))
    return runtime.ingest_pipeline, runtime.query_pipeline
