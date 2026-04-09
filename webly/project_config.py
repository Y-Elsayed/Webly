from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from webly.config_validator import validate_pipeline_config

_LIST_FIELDS = (
    "allowed_domains",
    "allowed_paths",
    "blocked_paths",
    "allow_url_patterns",
    "block_url_patterns",
    "seed_urls",
)


@dataclass(slots=True)
class ProjectConfig:
    start_url: str
    output_dir: str
    index_dir: str
    allowed_domains: list[str] = field(default_factory=list)
    crawl_entire_site: bool = True
    max_depth: int = 3
    allow_subdomains: bool = False
    respect_robots: bool = True
    rate_limit_delay: float = 0.2
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    allow_url_patterns: list[str] = field(default_factory=list)
    block_url_patterns: list[str] = field(default_factory=list)
    seed_urls: list[str] = field(default_factory=list)
    results_file: str = "results.jsonl"
    embedding_model: str = "openai:text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    summary_model: str = ""
    answering_mode: str = "technical_grounded"
    system_prompt: str = ""
    system_prompt_custom_override: bool = False
    allow_generated_examples: bool = False
    retrieval_mode: str = "builder"
    builder_max_rounds: int = 1
    leave_last_k: int = 2
    score_threshold: float = 0.5
    debug: bool = False
    query_debug: bool = False
    embedding_cache_dir: str = ""

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        output_dir: str | None = None,
        index_dir: str | None = None,
    ) -> "ProjectConfig":
        raw = dict(data)

        emb = (raw.get("embedding_model") or "").strip()
        raw["embedding_model"] = "openai:text-embedding-3-small" if emb.lower() in {"", "default"} else emb

        chat = (raw.get("chat_model") or "").strip()
        raw["chat_model"] = "gpt-4o-mini" if chat.lower() in {"", "default"} else chat

        raw["output_dir"] = output_dir or raw.get("output_dir") or ""
        raw["index_dir"] = index_dir or raw.get("index_dir") or ""
        raw["results_file"] = str(raw.get("results_file") or "results.jsonl")

        for field_name in _LIST_FIELDS:
            value = raw.get(field_name) or []
            if isinstance(value, (tuple, set)):
                raw[field_name] = list(value)

        config = cls(
            start_url=raw.get("start_url", ""),
            output_dir=raw["output_dir"],
            index_dir=raw["index_dir"],
            allowed_domains=raw.get("allowed_domains", []),
            crawl_entire_site=raw.get("crawl_entire_site", True),
            max_depth=raw.get("max_depth", 3),
            allow_subdomains=raw.get("allow_subdomains", False),
            respect_robots=raw.get("respect_robots", True),
            rate_limit_delay=raw.get("rate_limit_delay", 0.2),
            allowed_paths=raw.get("allowed_paths", []),
            blocked_paths=raw.get("blocked_paths", []),
            allow_url_patterns=raw.get("allow_url_patterns", []),
            block_url_patterns=raw.get("block_url_patterns", []),
            seed_urls=raw.get("seed_urls", []),
            results_file=raw["results_file"],
            embedding_model=raw["embedding_model"],
            chat_model=raw["chat_model"],
            summary_model=raw.get("summary_model", ""),
            answering_mode=raw.get("answering_mode", "technical_grounded"),
            system_prompt=raw.get("system_prompt", ""),
            system_prompt_custom_override=raw.get("system_prompt_custom_override", False),
            allow_generated_examples=raw.get("allow_generated_examples", False),
            retrieval_mode=raw.get("retrieval_mode", "builder"),
            builder_max_rounds=raw.get("builder_max_rounds", 1),
            leave_last_k=raw.get("leave_last_k", 2),
            score_threshold=raw.get("score_threshold", 0.5),
            debug=raw.get("debug", False),
            query_debug=raw.get("query_debug", False),
            embedding_cache_dir=raw.get("embedding_cache_dir", ""),
        )
        config.validate()
        return config

    def validate(self) -> None:
        validate_pipeline_config(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_url": self.start_url,
            "output_dir": self.output_dir,
            "index_dir": self.index_dir,
            "allowed_domains": list(self.allowed_domains),
            "crawl_entire_site": self.crawl_entire_site,
            "max_depth": self.max_depth,
            "allow_subdomains": self.allow_subdomains,
            "respect_robots": self.respect_robots,
            "rate_limit_delay": self.rate_limit_delay,
            "allowed_paths": list(self.allowed_paths),
            "blocked_paths": list(self.blocked_paths),
            "allow_url_patterns": list(self.allow_url_patterns),
            "block_url_patterns": list(self.block_url_patterns),
            "seed_urls": list(self.seed_urls),
            "results_file": self.results_file,
            "embedding_model": self.embedding_model,
            "chat_model": self.chat_model,
            "summary_model": self.summary_model,
            "answering_mode": self.answering_mode,
            "system_prompt": self.system_prompt,
            "system_prompt_custom_override": self.system_prompt_custom_override,
            "allow_generated_examples": self.allow_generated_examples,
            "retrieval_mode": self.retrieval_mode,
            "builder_max_rounds": self.builder_max_rounds,
            "leave_last_k": self.leave_last_k,
            "score_threshold": self.score_threshold,
            "debug": self.debug,
            "query_debug": self.query_debug,
            "embedding_cache_dir": self.embedding_cache_dir,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("output_dir", None)
        data.pop("index_dir", None)
        return data
