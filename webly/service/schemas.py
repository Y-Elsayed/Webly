from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectConfigCreate(BaseModel):
    start_url: str
    allowed_domains: list[str] = Field(default_factory=list)
    crawl_entire_site: bool = True
    max_depth: int = 3
    allow_subdomains: bool = False
    respect_robots: bool = True
    rate_limit_delay: float = 0.2
    allowed_paths: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)
    allow_url_patterns: list[str] = Field(default_factory=list)
    block_url_patterns: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
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


class ProjectConfigPatch(BaseModel):
    start_url: str | None = None
    allowed_domains: list[str] | None = None
    crawl_entire_site: bool | None = None
    max_depth: int | None = None
    allow_subdomains: bool | None = None
    respect_robots: bool | None = None
    rate_limit_delay: float | None = None
    allowed_paths: list[str] | None = None
    blocked_paths: list[str] | None = None
    allow_url_patterns: list[str] | None = None
    block_url_patterns: list[str] | None = None
    seed_urls: list[str] | None = None
    results_file: str | None = None
    embedding_model: str | None = None
    chat_model: str | None = None
    summary_model: str | None = None
    answering_mode: str | None = None
    system_prompt: str | None = None
    system_prompt_custom_override: bool | None = None
    allow_generated_examples: bool | None = None
    retrieval_mode: str | None = None
    builder_max_rounds: int | None = None
    leave_last_k: int | None = None
    score_threshold: float | None = None
    debug: bool | None = None
    query_debug: bool | None = None
    embedding_cache_dir: str | None = None


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Docs",
                "config": {
                    "start_url": "https://example.com/docs",
                    "allowed_domains": ["example.com"],
                    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                },
            }
        }
    )

    name: str
    config: ProjectConfigCreate


class ProjectUpdateRequest(BaseModel):
    config: ProjectConfigPatch


class ProjectPathsResponse(BaseModel):
    root: str
    config: str
    index: str
    chats: str


class ProjectResponse(BaseModel):
    name: str
    config: dict[str, Any]
    paths: ProjectPathsResponse


class ProjectListResponse(BaseModel):
    items: list[str]


class RuntimeCapabilitiesResponse(BaseModel):
    has_openai_api_key: bool
    uses_openai_embeddings: bool
    uses_summary_model: bool
    requires_openai_for_ingest: bool
    requires_openai_for_query: bool
    ingest_pipeline_available: bool
    query_pipeline_available: bool
    blockers: list[str] = Field(default_factory=list)


class ProjectStatusResponse(BaseModel):
    name: str
    config: dict[str, Any]
    paths: ProjectPathsResponse
    results_ready: bool
    index_ready: bool
    query_ready: bool
    chat_ready: bool
    capabilities: RuntimeCapabilitiesResponse


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "How does authentication work?",
                "memory_context": "",
                "retry_on_empty": False,
            }
        }
    )

    question: str
    memory_context: str = ""
    retry_on_empty: bool = False


class SourceRefResponse(BaseModel):
    chunk_id: str
    url: str
    section: str = ""


class QueryResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Authentication uses API tokens.",
                "supported": True,
                "sources": [
                    {
                        "chunk_id": "chunk-1",
                        "url": "https://example.com/docs/auth",
                        "section": "Authentication",
                    }
                ],
                "trace": {},
            }
        }
    )

    answer: str
    supported: bool
    sources: list[SourceRefResponse] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    mode: str = "both"
    force_crawl: bool = False


class IngestResponse(BaseModel):
    status: str
    result: dict[str, Any]


class ChatSettingsPayload(BaseModel):
    score_threshold: float = 0.5
    memory_reset_at: int = 0


class ChatMessagePayload(BaseModel):
    role: str
    content: str


class ChatUpdateRequest(BaseModel):
    title: str | None = None
    settings: ChatSettingsPayload | None = None
    messages: list[ChatMessagePayload] = Field(default_factory=list)


class ChatResponse(BaseModel):
    title: str
    settings: ChatSettingsPayload
    messages: list[ChatMessagePayload] = Field(default_factory=list)


class ChatListResponse(BaseModel):
    items: list[str]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "Project not found: Docs"}}
    )

    detail: str
