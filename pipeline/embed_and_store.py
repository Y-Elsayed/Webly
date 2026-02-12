import json
import os
import re
from typing import Any, Dict, List

from embedder.base_embedder import Embedder
from vector_index.vector_db import VectorDatabase


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

                parts = self._chunk_for_embedding(content)
                parent_id = record.get("id") or f"{record.get('url', 'unknown')}#chunk_{record.get('chunk_index', -1)}"

                for seg_idx, part in enumerate(parts):
                    embedding = self.embedder.embed(part)
                    if embedding is None:
                        print(
                            "[EmbedAndStorePipeline] Skipping record at "
                            f"line {line_num} seg {seg_idx} - embedding failed."
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
        print(f"[EmbedAndStorePipeline] Saved index to: {self.index_path}")

    # --- token-safe embedding helpers ---
    def _max_input_tokens(self) -> int:
        # Try to read from embedder if available; otherwise default 8192
        for attr in ("max_input_tokens", "max_tokens", "context_size", "max_seq_len"):
            v = getattr(self.embedder, attr, None)
            if isinstance(v, int) and v > 0:
                return v
        return 8192

    def _count_tokens(self, text: str) -> int:
        # Prefer an embedder-provided counter if present
        if hasattr(self.embedder, "count_tokens"):
            try:
                return int(self.embedder.count_tokens(text))
            except Exception:
                pass
        # Heuristic: ~4 chars per token
        return max(1, len(text) // 4)

    def _hard_char_splits(self, text: str, max_tokens: int) -> list[str]:
        # Fall back to char-based slicing if a single sentence/para still too big
        # Convert token budget to rough char budget (x4), keep a minimum step
        char_budget = max(800, max_tokens * 4)
        out, i, n = [], 0, len(text)
        while i < n:
            out.append(text[i : min(n, i + char_budget)])
            i += char_budget
        return out

    def _chunk_for_embedding(self, text: str, safety_ratio: float = 0.9) -> list[str]:
        """Split text into <= max_tokens chunks, preferring paragraph/sentence boundaries."""
        max_tok = int(self._max_input_tokens() * safety_ratio)
        if self._count_tokens(text) <= max_tok:
            return [text]

        # 1) by blank lines (paragraphs)
        paras = re.split(r"\n{2,}", text)
        chunks, cur, cur_toks = [], [], 0

        def flush():
            nonlocal chunks, cur, cur_toks
            if cur:
                joined = "\n\n".join(cur).strip()
                if joined:
                    chunks.append(joined)
            cur, cur_toks = [], 0

        for p in paras:
            ptok = self._count_tokens(p)
            if ptok > max_tok:
                # 2) split paragraph by sentences
                sents = re.split(r"(?<=[.!?])\s+", p)
                for s in sents:
                    stok = self._count_tokens(s)
                    if stok > max_tok:
                        # 3) last resort: hard splits by chars
                        for piece in self._hard_char_splits(s, max_tok):
                            if self._count_tokens(piece) > max_tok:
                                # extremely rare; but we still push as-is to avoid loops
                                chunks.append(piece)
                            else:
                                if cur_toks + self._count_tokens(piece) > max_tok:
                                    flush()
                                cur.append(piece)
                                cur_toks += self._count_tokens(piece)
                        continue
                    if cur_toks + stok > max_tok:
                        flush()
                    cur.append(s)
                    cur_toks += stok
                flush()
            else:
                if cur_toks + ptok > max_tok:
                    flush()
                cur.append(p)
                cur_toks += ptok
        flush()
        return [c for c in chunks if c]
