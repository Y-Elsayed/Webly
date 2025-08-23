import os
import json
from typing import List, Dict, Any
from embedder.base_embedder import Embedder
from storage.vector_db import VectorDatabase


class EmbedAndStorePipeline:
    def __init__(
        self,
        embedder: Embedder,
        db: VectorDatabase,
        results_path: str,
        index_path: str,
        embedding_field: str = "text",
        batch_size: int = 100
    ):
        """
        A lightweight pipeline to embed existing processed results and store them in a vector DB.
        Useful for updating indices after re-crawling or processing changes.

        Args:
            embedder (Embedder): Embedder instance to convert text to vectors.
            db (VectorDatabase): Vector database instance (e.g., FAISS).
            results_path (str): Path to the .jsonl file containing crawled data.
            index_path (str): Directory to save the index and metadata.
            embedding_field (str): Which field to embed ('text', 'markdown', 'summary', etc.).
            batch_size (int): Number of records to add in a single DB batch.
        """
        self.embedder = embedder
        self.db = db
        self.results_path = results_path
        self.index_path = index_path
        self.embedding_field = embedding_field
        self.batch_size = batch_size

    def run(self):
        """
        Reads the results file, generates embeddings, and stores them in the DB.
        """
        print(f"[EmbedAndStorePipeline] Reading: {self.results_path}")
        if not os.path.exists(self.results_path):
            raise FileNotFoundError(f"{self.results_path} does not exist.")

        self.db.create(dim=self.embedder.dim)
        buffer: List[Dict[str, Any]] = []

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[EmbedAndStorePipeline] Skipping line {line_num}: JSON decode error ({e})")
                    continue

                content = record.get(self.embedding_field)
                if not content or not isinstance(content, str) or not content.strip():
                    continue

                embedding = self.embedder.embed(content)
                if embedding is None:
                    print(f"[EmbedAndStorePipeline] Skipping record at line {line_num} - embedding failed.")
                    continue

                # Build a clean record for storage
                record_to_store = {
                    "id": record.get("id") or f"{record.get('url', 'unknown')}#chunk_{record.get('chunk_index', -1)}",
                    "url": record.get("url"),
                    "chunk_index": record.get("chunk_index"),
                    "embedding": embedding,
                    "text": content,
                    # Carry over metadata if already exists (graph info, etc.)
                    "metadata": record.get("metadata", {})
                }

                buffer.append(record_to_store)

                # Flush in batches
                if len(buffer) >= self.batch_size:
                    self.db.add(buffer)
                    buffer.clear()

            # Flush remainder
            if buffer:
                self.db.add(buffer)

        self.db.save(self.index_path)
        print(f"[EmbedAndStorePipeline] Saved index to: {self.index_path}")
