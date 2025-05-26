import os
import json
from embedder.base_embedder import Embedder
from storage.vector_db import VectorDatabase

# will use this in the future for updating existing indices after re-crawling or any other changes

class EmbedAndStorePipeline:
    def __init__(
        self,
        embedder: Embedder,
        db: VectorDatabase,
        results_path: str,
        index_path: str,
        embedding_field: str = "text"
    ):
        """
        Args:
            embedder (Embedder): Embedder instance to convert text to vectors.
            db (VectorDatabase): Vector database instance (e.g. FAISS).
            results_path (str): Path to the .jsonl file containing crawled data.
            index_path (str): Directory to save the index and metadata.
            embedding_field (str): Whether to embed 'text' or 'markdown' field.
        """
        self.embedder = embedder
        self.db = db
        self.results_path = results_path
        self.index_path = index_path
        self.embedding_field = embedding_field

    def run(self):
        """
        Reads the results file, generates embeddings, and stores them in the DB.
        """
        print(f"[EmbedAndStorePipeline] Reading: {self.results_path}")
        if not os.path.exists(self.results_path):
            raise FileNotFoundError(f"{self.results_path} does not exist.")

        self.db.create(dim=self.embedder.dim)

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                content = record.get(self.embedding_field)
                if not content:
                    continue

                embedding = self.embedder.embed(content)
                record["embedding"] = embedding
                self.db.add([record])

        self.db.save(self.index_path)
        print(f"[EmbedAndStorePipeline] Saved index to: {self.index_path}") # for debugging, will remove later and add logging
