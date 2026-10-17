from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceRef:
    chunk_id: str
    url: str
    section: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "chunk_id": self.chunk_id,
            "url": self.url,
            "section": self.section,
        }


@dataclass(slots=True)
class QueryResult:
    answer: str
    supported: bool
    sources: list[SourceRef] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    citations: list[dict[str, str]] = field(default_factory=list)
    status: str | None = None
    missing_information: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = "answered" if self.supported else "unsupported"

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "supported": self.supported,
            "sources": [source.to_dict() for source in self.sources],
            "trace": dict(self.trace),
            "citations": list(self.citations),
            "status": self.status,
            "missing_information": list(self.missing_information),
        }
