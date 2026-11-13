"""Explicit, host-owned resources and operation contracts for Core 0.2."""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock


@dataclass(frozen=True)
class OperationOutcome:
    state: str = "not_committed"
    snapshot_id: str | None = None
    operation_id: str | None = None

    def __post_init__(self):
        if self.state not in {"not_committed", "committed", "uncertain"}:
            raise ValueError("Invalid publication outcome state")


class CoreError(RuntimeError):
    code = "core_error"
    retryable = False

    def __init__(self, message: str, *, operation_id=None, outcome=None):
        super().__init__(message)
        self.operation_id = operation_id
        self.outcome = outcome or OperationOutcome(operation_id=operation_id)


class ConfigurationError(CoreError):
    code = "configuration_error"


class PolicyError(CoreError):
    code = "policy_rejected"


class RunPolicyMismatch(PolicyError):
    code = "run_policy_mismatch"

    def __init__(self, changed_fields):
        super().__init__("Saved capture is incompatible with the current source policy; run a fresh crawl")
        self.changed_fields = sorted(set(changed_fields))


class BudgetExceeded(CoreError):
    code = "budget_exhausted"


class OperationCancelled(CoreError):
    code = "cancelled"


class ArtifactError(CoreError):
    code = "artifact_error"


class PublicationConflict(CoreError):
    code = "publication_conflict"


class PublicationUncertain(CoreError):
    code = "publication_uncertain"


class UsageDeliveryError(CoreError):
    code = "usage_delivery_failed"


class ApprovalRequired(CoreError):
    code = "approval_required"

    def __init__(self, proposal):
        super().__init__("Source removals require approval of this exact candidate")
        self.proposal = proposal


class ProviderError(CoreError):
    code = "provider_error"


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _is_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


@dataclass(frozen=True)
class ResourceScope:
    resource_id: str
    root: Path

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.resource_id):
            raise ConfigurationError("resource_id must be an opaque identifier of 1–128 safe characters")
        given = Path(self.root).absolute()
        if any(_is_link(part) for part in (given, *given.parents)):
            raise PolicyError("Resource roots cannot contain symlinks or junctions")
        root = given.resolve()
        root.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "root", root)
        with FileLock(str(root / ".resource.lock")):
            manifest = root / "resource.json"
            if manifest.exists():
                try:
                    stored = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ArtifactError("Corrupt resource manifest") from exc
                if stored != {"format": 1, "resource_id": self.resource_id}:
                    raise PublicationConflict("Resource root belongs to a different resource")
            else:
                atomic_json(manifest, {"format": 1, "resource_id": self.resource_id})

    def path(self, *names: str) -> Path:
        if not names or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", n) or n.startswith(".") for n in names):
            raise PolicyError("Artifact names must be contained safe path components")
        candidate = self.root.joinpath(*names)
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if any(name.split(".")[0].upper() in reserved or name.endswith(".") for name in names):
            raise PolicyError("Reserved artifact name")
        if any(_is_link(part) for part in (candidate, *candidate.parents)):
            raise PolicyError("Artifact paths cannot contain symlinks or junctions")
        if not candidate.resolve().is_relative_to(self.root):
            raise PolicyError("Artifact path escapes resource root")
        return candidate


@dataclass(frozen=True)
class OperationLimits:
    timeout_s: float = 30.0
    searches: int = 4
    provider_attempts: int = 16
    network_attempts: int = 10000
    tokens: int = 32000
    output_tokens: int = 2048
    pages: int = 2000
    response_bytes: int = 5 * 1024 * 1024
    total_bytes: int = 500 * 1024 * 1024
    redirects: int = 5
    concurrency: int = 4
    per_host_concurrency: int = 2
    host_interval_s: float = 0.2
    retries: int = 2
    final_reserve_tokens: int = 8192

    def __post_init__(self):
        for name, value in asdict(self).items():
            minimum = 0 if name in {"retries", "host_interval_s", "redirects", "final_reserve_tokens"} else 1
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < minimum
            ):
                raise ConfigurationError(f"Invalid operation limit: {name}")
            if name not in {"timeout_s", "host_interval_s"} and not isinstance(value, int):
                raise ConfigurationError(f"Limit must be an integer: {name}")

    @classmethod
    def ingest(cls, **overrides):
        return cls(
            **{
                "timeout_s": 1800,
                "provider_attempts": 10000,
                "tokens": 5_000_000,
                "final_reserve_tokens": 0,
                **overrides,
            }
        )


@dataclass
class OperationContext:
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    limits: OperationLimits = field(default_factory=OperationLimits)
    sink: Callable[[dict], None] | None = field(default=None, repr=False)
    cancelled: threading.Event = field(default_factory=threading.Event, repr=False)
    events: list[dict] = field(default_factory=list, repr=False)
    pending_events: list[dict] = field(default_factory=list, repr=False)
    outcome: OperationOutcome = field(default_factory=OperationOutcome)
    phase: str = "work"
    _started: float = field(default_factory=time.monotonic, repr=False)
    _counts: dict = field(default_factory=dict, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.operation_id):
            raise ConfigurationError("Invalid operation ID")
        self.outcome = OperationOutcome(operation_id=self.operation_id)

    @property
    def remaining(self) -> float:
        return max(0.0, self.limits.timeout_s - (time.monotonic() - self._started))

    def check(self):
        if self.cancelled.is_set():
            raise OperationCancelled("Operation cancelled", operation_id=self.operation_id, outcome=self.outcome)
        if not self.remaining:
            raise BudgetExceeded("Operation deadline exhausted", operation_id=self.operation_id, outcome=self.outcome)

    def consume(self, name: str, amount: int = 1):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ConfigurationError("Budget consumption must be a nonnegative integer")
        with self._lock:
            self.check()
            maximum = getattr(self.limits, name)
            value = self._counts.get(name, 0) + amount
            if value > maximum:
                raise BudgetExceeded(
                    f"Operation {name} budget exhausted", operation_id=self.operation_id, outcome=self.outcome
                )
            self._counts[name] = value

    def emit(self, kind: str, **payload):
        with self._lock:
            event = {"operation_id": self.operation_id, "sequence": len(self.events), "kind": kind, **payload}
            self.events.append(event)
            if self.sink:
                try:
                    self.sink(event)
                except Exception:
                    self.pending_events.append(event)

    def consume_bytes(self, kind: str, amount: int):
        with self._lock:
            self.check()
            key = f"{kind}_bytes"
            value = self._counts.get(key, 0) + amount
            if value > self.limits.total_bytes:
                raise BudgetExceeded(f"Crawl {kind} byte budget exhausted", operation_id=self.operation_id)
            self._counts[key] = value

    def before_provider(self, tokens: int, *, model="unknown", input_tokens=0, output_tokens=0):
        if self.pending_events:
            raise UsageDeliveryError(
                "Usage events await delivery", operation_id=self.operation_id, outcome=self.outcome
            )
        self.consume("provider_attempts")
        reserve = self.limits.final_reserve_tokens if self.phase != "final" else 0
        if self._counts.get("tokens", 0) + tokens + reserve > self.limits.tokens:
            raise BudgetExceeded("Provider call would consume final-answer reserve", operation_id=self.operation_id)
        self.consume("tokens", tokens)
        self.emit(
            "provider_started",
            attempt=self._counts["provider_attempts"],
            reserved_tokens=tokens,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if self.pending_events:
            raise UsageDeliveryError("Usage reservation could not be delivered", operation_id=self.operation_id)

    def summary(self):
        return {
            **self._counts,
            "pending_event_count": len(self.pending_events),
            "elapsed_s": round(time.monotonic() - self._started, 4),
        }


_operation: contextvars.ContextVar[OperationContext | None] = contextvars.ContextVar("webly_operation", default=None)


def current_operation() -> OperationContext | None:
    return _operation.get()


@contextmanager
def operation_scope(context: OperationContext):
    context.check()
    token = _operation.set(context)
    try:
        yield context
    finally:
        _operation.reset(token)


class IngestResult(dict):
    """JSON-compatible operation result, retaining 0.1 mapping access."""

    @property
    def outcome(self) -> OperationOutcome:
        return OperationOutcome(**self.get("outcome", {}))

    def to_dict(self):
        return dict(self)
