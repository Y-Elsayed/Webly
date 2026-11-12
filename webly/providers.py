"""Caller-owned model clients with explicit capabilities and operation accounting."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from webly.contracts import ConfigurationError, CoreError, ProviderError, current_operation


@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    input_tokens: int
    output_tokens: int = 2048
    dimensions: int | None = None
    revision: str = "1"
    endpoint_id: str = "default"

    def __post_init__(self):
        if not self.model_id or self.input_tokens < 1 or self.output_tokens < 1:
            raise ConfigurationError("Model capabilities must be explicit positive limits")
        if self.dimensions is not None and self.dimensions < 1:
            raise ConfigurationError("Embedding dimensions must be positive")


@dataclass(frozen=True)
class ProviderResponse:
    value: object = field(repr=False)
    input_tokens: int
    output_tokens: int = 0


class AccountedProvider:
    def __init__(self, client, capabilities: ModelCapabilities, kind: str):
        self._client = client
        self.capabilities = capabilities
        self.kind = kind
        self.context_window_tokens = capabilities.input_tokens
        self.max_input_tokens = capabilities.input_tokens
        self.dim = capabilities.dimensions
        self.model_name = capabilities.model_id
        self.cache = None
        self.cache_namespace = ""

    def __repr__(self):
        return f"AccountedProvider(kind={self.kind!r}, model={self.model_name!r})"

    def count_tokens(self, text):
        counter = getattr(self._client, "count_tokens", None)
        if counter is None:
            raise ConfigurationError("Providers must supply a tokenizer")
        count = counter(text)
        if not isinstance(count, int) or count < 0:
            raise ConfigurationError("Invalid provider token count")
        return count

    def _attempt(self, method, text):
        context = current_operation()
        tokens = self.count_tokens(text) + (32 if method == "generate" else 0)
        reserve = self.capabilities.output_tokens if method == "generate" else 0
        if context:
            reserve = min(reserve, context.limits.output_tokens)
        if tokens + reserve > self.capabilities.input_tokens:
            raise ConfigurationError("Provider input exceeds declared model context")
        if context:
            context.before_provider(tokens + reserve, model=self.model_name, input_tokens=tokens, output_tokens=reserve)
        try:
            function = getattr(self._client, method)
            budgeted = getattr(self._client, f"{method}_with_limits", None)
            value = (
                budgeted(text, timeout=min(15.0, context.remaining), max_output_tokens=reserve)
                if context and budgeted
                else function(text)
            )
            usage = None
            if isinstance(value, ProviderResponse):
                usage = {"input_tokens": value.input_tokens, "output_tokens": value.output_tokens}
                value = value.value
        except CoreError:
            raise
        except Exception as exc:
            if context:
                context.emit(
                    "usage",
                    provider=self.kind,
                    model=self.model_name,
                    input_tokens=tokens,
                    output_tokens=reserve,
                    estimated=True,
                    outcome="failed_or_uncertain",
                )
            error = ProviderError(
                f"{self.kind} provider failed ({type(exc).__name__})",
                operation_id=context.operation_id if context else None,
            )
            status = getattr(exc, "status_code", None)
            error.retryable = (
                status in {408, 429, 500, 502, 503, 504}
                or type(exc).__name__
                in {"APIConnectionError", "APITimeoutError", "TimeoutError", "ConnectError", "ReadTimeout"}
            ) and "insufficient_quota" not in str(exc)
            raise error from None
        if context:
            context.emit(
                "usage",
                provider=self.kind,
                model=self.model_name,
                input_tokens=(usage or {}).get("input_tokens", tokens),
                output_tokens=(usage or {}).get("output_tokens", reserve),
                estimated=usage is None,
                outcome="completed",
            )
        return value

    def _call(self, method, text):
        context = current_operation()
        maximum = context.limits.retries if context else 0
        for attempt in range(maximum + 1):
            try:
                return self._attempt(method, text)
            except ProviderError as exc:
                if attempt == maximum or not exc.retryable:
                    raise
                context.check()
                time.sleep(min(0.2 * 2**attempt, context.remaining))

    def embed(self, text):
        context = current_operation()
        if context:
            context.check()
        key, result = None, None
        if self.cache:
            key = self.cache.make_key(
                text,
                self.model_name,
                provider=self.capabilities.endpoint_id,
                revision=self.capabilities.revision,
                dimensions=self.dim,
                namespace=self.cache_namespace,
            )
            result = self.cache.get(key)
        if result is None:
            result = self._call("embed", text)
        if result is None or len(result) != self.dim or any(not math.isfinite(float(value)) for value in result):
            raise ProviderError("Embedding vector dimensions do not match capabilities")
        if self.cache:
            self.cache.put(key, result)
        return result

    def generate(self, text):
        return self._call("generate", text)


@dataclass(repr=False)
class ProviderBundle:
    embedder: object = field(repr=False)
    embedding: ModelCapabilities
    chat: object | None = field(default=None, repr=False)
    generation: ModelCapabilities | None = None
    summary: object | None = field(default=None, repr=False)
    summarization: ModelCapabilities | None = None
    _closed: bool = False

    def __post_init__(self):
        if self.embedding.dimensions is None:
            raise ConfigurationError("Embedding dimensions are required")
        if (self.chat is None) != (self.generation is None) or (self.summary is None) != (self.summarization is None):
            raise ConfigurationError("Every model client requires matching capabilities")
        if any(
            client is not None and not callable(getattr(client, "count_tokens", None))
            for client in (self.embedder, self.chat, self.summary)
        ):
            raise ConfigurationError("Provider clients require token counters")

    def __repr__(self):
        return f"ProviderBundle(embedding={self.embedding.model_id!r}, closed={self._closed})"

    def close(self):
        if self._closed:
            return
        self._closed = True
        seen = set()
        for client in (self.embedder, self.chat, self.summary):
            if client is not None and id(client) not in seen:
                seen.add(id(client))
                close = getattr(client, "close", None)
                if close:
                    close()

    def __enter__(self):
        if self._closed:
            raise ConfigurationError("Provider bundle is closed")
        return self

    def __exit__(self, *_exc):
        self.close()
