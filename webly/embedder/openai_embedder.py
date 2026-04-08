# embedder/openai_embedder.py
import logging
import os
import time
from typing import List

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from .base_embedder import Embedder

logger = logging.getLogger(__name__)


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: str | None = None,
        cache_dir: str | None = None,
        cost_tracker=None,
    ):
        """
        Args:
            model_name (str): OpenAI embedding model (e.g. "text-embedding-3-small", "text-embedding-3-large").
            api_key (str): Optional API key. Defaults to OPENAI_API_KEY from env.
        """
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY environment variable or api_key argument")

        self.client = OpenAI(api_key=self.api_key)

        self._cost_tracker = cost_tracker

        # Optional embedding cache
        self._cache = None
        if cache_dir is not None:
            from .embedding_cache import EmbeddingCache
            self._cache = EmbeddingCache(os.path.join(cache_dir, ".embedding_cache.db"))

        # Dimension sizes (hardcoded since OpenAI doesn't expose this directly)
        if model_name == "text-embedding-3-small":
            self.dim = 1536
            self.max_input_tokens = 7000
            self.safety_ratio = 0.8
        elif model_name == "text-embedding-3-large":
            self.dim = 3072
            self.max_input_tokens = 7000
            self.safety_ratio = 0.8
        else:
            # fallback
            self.dim = 1536
            self.max_input_tokens = 7000
            self.safety_ratio = 0.8

    def count_tokens(self, text: str) -> int:
        """
        Best-effort token counter to help pre-chunking.
        Falls back to a rough char heuristic if tiktoken isn't available.
        """
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception as e:
            logger.debug(f"tiktoken unavailable or failed, using char-count heuristic: {e}")
            return max(1, len(text) // 4)

    def _call_with_retry(self, fn, max_retries: int = 3, backoff: float = 1.0):
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except RateLimitError as e:
                if attempt == max_retries:
                    raise
                wait = backoff * (2 ** attempt)
                logger.warning(f"OpenAI rate limit hit; retrying in {wait:.1f}s (attempt {attempt + 1}): {e}")
                time.sleep(wait)
            except (APIConnectionError, APIStatusError) as e:
                if attempt == max_retries:
                    raise
                wait = backoff * (2 ** attempt)
                logger.warning(f"OpenAI API error; retrying in {wait:.1f}s (attempt {attempt + 1}): {e}")
                time.sleep(wait)

    def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a single text string.
        """
        if not text.strip():
            return []

        if self._cache is not None:
            _key = self._cache.make_key(text, self.model_name)
            _cached = self._cache.get(_key)
            if _cached is not None:
                return _cached

        resp = self._call_with_retry(
            lambda: self.client.embeddings.create(model=self.model_name, input=text)
        )
        result = resp.data[0].embedding

        if self._cache is not None:
            self._cache.put(_key, result)

        if self._cost_tracker is not None and resp.usage is not None:
            self._cost_tracker.record_embedding(self.model_name, resp.usage.prompt_tokens, 1)

        return result

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.  Cache hits are returned
        directly; only cache misses are sent to the API.
        """
        texts = [t for t in texts if t.strip()]
        if not texts:
            return []

        if self._cache is None:
            resp = self._call_with_retry(
                lambda: self.client.embeddings.create(model=self.model_name, input=texts)
            )
            if self._cost_tracker is not None and resp.usage is not None:
                self._cost_tracker.record_embedding(self.model_name, resp.usage.prompt_tokens, len(texts))
            return [item.embedding for item in resp.data]

        # Separate cache hits from misses (preserve original order, deduplicate misses)
        result_map: dict[str, List[float] | None] = {}
        for t in texts:
            k = self._cache.make_key(t, self.model_name)
            result_map[t] = self._cache.get(k)

        # Unique misses in original order
        unique_misses: list[str] = list(dict.fromkeys(t for t in texts if result_map[t] is None))

        if unique_misses:
            resp = self._call_with_retry(
                lambda: self.client.embeddings.create(model=self.model_name, input=unique_misses)
            )
            if self._cost_tracker is not None and resp.usage is not None:
                self._cost_tracker.record_embedding(self.model_name, resp.usage.prompt_tokens, len(unique_misses))
            for miss_text, item in zip(unique_misses, resp.data):
                result_map[miss_text] = item.embedding
                self._cache.put(self._cache.make_key(miss_text, self.model_name), item.embedding)

        return [result_map[t] for t in texts]  # type: ignore[return-value]
