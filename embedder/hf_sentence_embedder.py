from sentence_transformers import SentenceTransformer
from embedder.base_embedder import Embedder

class HFSentenceEmbedder(Embedder):
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text).tolist()
