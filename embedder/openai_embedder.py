# embedder/openai_embedder.py
import os
from typing import List
from embedder.base_embedder import Embedder
from openai import OpenAI


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

        # Dimension sizes (hardcoded since OpenAI doesn’t expose this directly)
        if model_name == "text-embedding-3-small":
            self.dim = 1536
        elif model_name == "text-embedding-3-large":
            self.dim = 3072
        else:
            # fallback
            self.dim = 1536  

    def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a single text string.
        """
        if not text.strip():
            return []
        resp = self.client.embeddings.create(
            model=self.model_name,
            input=text
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        """
        texts = [t for t in texts if t.strip()]
        if not texts:
            return []
        resp = self.client.embeddings.create(
            model=self.model_name,
            input=texts
        )
        return [item.embedding for item in resp.data]
