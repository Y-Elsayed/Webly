import json
import logging
import os
from typing import Any, Dict, List

from webly.embedder.base_embedder import Embedder
from webly.pipeline.embedding_text import chunk_text_for_embedding, count_tokens, hard_char_splits, max_input_tokens
from webly.vector_index.vector_db import VectorDatabase


class EmbedAndStorePipeline:
    def __init__(
        self,
        embedder: Embedder,
        db: VectorDatabase,
        results_path: str,
        index_path: str,
        embedding_field: str = "text",
        batch_size: int = 100,
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
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self):
        """
        Reads the results file, generates embeddings, and stores them in the DB.
        """
        self.logger.info(f"Reading: {self.results_path}")
        if not os.path.exists(self.results_path):
            raise FileNotFoundError(f"{self.results_path} does not exist.")

        self.db.create(dim=self.embedder.dim)
        buffer: List[Dict[str, Any]] = []

        with open(self.results_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Skipping line {line_num}: JSON decode error ({e})")
                    continue

                content = record.get(self.embedding_field)
                if not content or not isinstance(content, str) or not content.strip():
                    continue

                parts = self._chunk_for_embedding(content)
                parent_id = record.get("id") or f"{record.get('url', 'unknown')}#chunk_{record.get('chunk_index', -1)}"

                for seg_idx, part in enumerate(parts):
                    embedding = self.embedder.embed(part)
                    if embedding is None:
                        self.logger.warning(
                            f"Skipping record at line {line_num} seg {seg_idx} - embedding failed."
                        )
                        continue

                    record_to_store = {
                        "id": f"{parent_id}__seg_{seg_idx}",
                        "url": record.get("url"),
                        "chunk_index": record.get("chunk_index"),
                        "embedding": embedding,
                        "text": part,
                        "metadata": {
                            **(record.get("metadata", {}) or {}),
                            "parent_id": parent_id,
                            "seg_index": seg_idx,
                            "seg_count": len(parts),
                            "crawled_at": record.get("crawled_at", ""),
                        },
                    }
                    buffer.append(record_to_store)

                    if len(buffer) >= self.batch_size:
                        self.db.add(buffer)
                        buffer.clear()

                # Flush in batches
                if len(buffer) >= self.batch_size:
                    self.db.add(buffer)
                    buffer.clear()

            # Flush remainder
            if buffer:
                self.db.add(buffer)

        self.db.save(self.index_path)
        self.logger.info(f"Saved index to: {self.index_path}")

    # --- token-safe embedding helpers ---
    def _max_input_tokens(self) -> int:
        return max_input_tokens(self.embedder)

    def _count_tokens(self, text: str) -> int:
        return count_tokens(self.embedder, text, self.logger)

    def _hard_char_splits(self, text: str, max_tokens: int) -> list[str]:
        return hard_char_splits(text, max_tokens)

    def _chunk_for_embedding(self, text: str, safety_ratio: float = 0.9) -> list[str]:
        return chunk_text_for_embedding(self.embedder, text, self.logger, safety_ratio=safety_ratio)
