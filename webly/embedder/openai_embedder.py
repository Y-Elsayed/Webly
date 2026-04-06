# embedder/openai_embedder.py
import logging
import os
import time
from typing import List

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from .base_embedder import Embedder

logger = logging.getLogger(__name__)


class OpenAIEmbedder(Embedder):
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str | None = None):
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

        # Dimension sizes (hardcoded since OpenAI doesnâ€™t expose this directly)
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
        except Exception:
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
        resp = self._call_with_retry(
            lambda: self.client.embeddings.create(model=self.model_name, input=text)
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        """
        texts = [t for t in texts if t.strip()]
        if not texts:
            return []
        resp = self._call_with_retry(
            lambda: self.client.embeddings.create(model=self.model_name, input=texts)
        )
        return [item.embedding for item in resp.data]
