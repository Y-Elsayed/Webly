from sentence_transformers import SentenceTransformer

from .base_embedder import Embedder


class HFSentenceEmbedder(Embedder):
    def __init__(self, model_name: str | None = "sentence-transformers/all-MiniLM-L6-v2"):
        name = (model_name or "").strip()
        if name.lower() in ("", "default"):
            name = "sentence-transformers/all-MiniLM-L6-v2"

        try:
            self.model = SentenceTransformer(name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load embedding model '{name}'. "
                "Set a valid Hugging Face model in your project config, e.g. "
                "'sentence-transformers/all-MiniLM-L6-v2' or 'sentence-transformers/all-mpnet-base-v2'. "
                f"Original error: {e}"
            )
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        vec = self.model.encode(text, normalize_embeddings=True).tolist()
        return vec
