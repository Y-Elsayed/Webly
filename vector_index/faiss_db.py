import hashlib
import os
import pickle
from typing import Dict, List, Optional

import faiss
import numpy as np

from .vector_db import VectorDatabase


class FaissDatabase(VectorDatabase):
    """
    Drop-in improved FAISS wrapper:
      - Stable 64-bit IDs via IndexIDMap2 (hash of a stable 'key')
      - True remove_ids / add_with_ids for delete/update
      - Optional index types: flat|hnsw|ivf_flat|ivf_pq
      - Auto-train IVF on first add (without using .base_index; compatible with Windows wheels)
      - Cosine similarity via inner product + L2 normalization
    External usage/API unchanged.
    """

    def __init__(self, index_path: str = None):
        self.index_path = index_path
        self.index: Optional[faiss.Index] = None
        self.dim: Optional[int] = None

        # Metadata storage (kept as a list for save/load compatibility)
        self.metadata: List[Dict] = []

        # Maps
        # key -> external id (we use the FAISS 64-bit id as the external id)
        self.id_map: Dict[str, int] = {}

        # faiss_id -> position in self.metadata
        self._faiss_to_pos: Dict[int, int] = {}
        # position -> faiss_id (helpful during maintenance)
        self._pos_to_faiss: Dict[int, int] = {}

        # Config
        self._index_type: str = "flat"
        self._ivf_nlist: int = 1024
        self._pq_m: int = 8
        self._pq_nbits: int = 8
        self._hnsw_M: int = 32
        self._hnsw_efSearch: int = 64
        self._hnsw_efConstruction: int = 120

        if index_path:
            self.load(index_path)

    # ---------------- Utilities ----------------

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    @staticmethod
    def _id64_from_key(key: str) -> np.int64:
        """
        Deterministic 64-bit id from a stable key (url/id/fallback).
        Use raw bytes -> uint64 to avoid Python int size issues on Windows.
        """
        h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        return np.frombuffer(h, dtype=np.uint64)[0].astype("int64")

    @staticmethod
    def _key_for_idx(rec: Dict, idx: int) -> str:
        """
        Stable key used for id hashing.
        Priority: explicit stored _key -> url -> id -> fallback 'record_{idx}'.
        We store _key in metadata during add() so rebuilds remain stable even if positions shift.
        """
        return rec.get("_key") or rec.get("url") or rec.get("id") or f"record_{idx}"

    def _maybe_train_ivf(self, arr: np.ndarray) -> None:
        """
        Train IVF-style indexes if needed. We do not rely on .base_index (not present on some builds).
        Many FAISS index types expose 'is_trained' on the wrapper; train() will forward.
        """
        try:
            if hasattr(self.index, "is_trained") and hasattr(self.index, "train"):
                if not self.index.is_trained:
                    self.index.train(arr)
        except Exception:
            # Non-trainable index types or already-trained: just ignore
            pass

    # ---------------- Core API ----------------

    def create(self, dim: int, index_type: str = "flat") -> None:
        """
        Initialize the FAISS index.
        index_type: "flat" | "hnsw" | "ivf_flat" | "ivf_pq"
        """
        self.dim = dim
        self._index_type = (index_type or "flat").lower()

        if self._index_type == "flat":
            base = faiss.IndexFlatIP(dim)

        elif self._index_type == "hnsw":
            # HNSW with Inner Product
            base = faiss.IndexHNSWFlat(dim, self._hnsw_M, faiss.METRIC_INNER_PRODUCT)
            base.hnsw.efConstruction = self._hnsw_efConstruction
            base.hnsw.efSearch = self._hnsw_efSearch

        elif self._index_type == "ivf_flat":
            # IVF with Flat lists (coarse quantizer = IP)
            quantizer = faiss.IndexFlatIP(dim)
            base = faiss.IndexIVFFlat(quantizer, dim, self._ivf_nlist, faiss.METRIC_INNER_PRODUCT)

        elif self._index_type == "ivf_pq":
            # IVF + PQ
            quantizer = faiss.IndexFlatIP(dim)
            base = faiss.IndexIVFPQ(
                quantizer, dim, self._ivf_nlist, self._pq_m, self._pq_nbits, faiss.METRIC_INNER_PRODUCT
            )

        else:
            raise ValueError(f"Unsupported index type: {index_type}")

        # Always wrap with IDMap2 to manage stable ids (no reliance on .base_index)
        self.index = faiss.IndexIDMap2(base)

        # Reset in-memory stores
        self.metadata = []
        self.id_map = {}
        self._faiss_to_pos = {}
        self._pos_to_faiss = {}

    def add(self, records: List[Dict]) -> None:
        """
        Add records to the DB.
        Each record must have:
          - "embedding": List[float]
          - other fields (url/id/text/metadata/...) are preserved in self.metadata
        """
        if not self.index:
            raise RuntimeError("Index not created. Call create() first.")
        if not records:
            return

        vectors = [rec["embedding"] for rec in records]
        arr = np.asarray(vectors, dtype="float32")
        arr = self._normalize(arr)

        # Determine stable keys and faiss ids
        start_pos = len(self.metadata)
        keys: List[str] = [self._key_for_idx(rec, start_pos + i) for i, rec in enumerate(records)]
        ids = np.asarray([self._id64_from_key(k) for k in keys], dtype="int64")

        # Train IVF if needed (safe no-op for non-trainable indexes)
        self._maybe_train_ivf(arr)

        # Add with stable ids
        self.index.add_with_ids(arr, ids)

        # Store metadata (without embeddings); persist the computed key for stability across rebuilds
        for i, rec in enumerate(records):
            rec_copy = rec.copy()
            rec_copy.pop("embedding", None)
            # store key so future map rebuilds don't depend on position
            rec_copy["_key"] = keys[i]

            pos = len(self.metadata)
            fid = int(ids[i])

            self.metadata.append(rec_copy)
            self._faiss_to_pos[fid] = pos
            self._pos_to_faiss[pos] = fid

            self.id_map[keys[i]] = fid

    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        if self.index is None:
            raise RuntimeError("Index not initialized.")
        if self.index.ntotal == 0 or top_k <= 0:
            return []

        k = min(int(top_k), self.index.ntotal)

        query = np.asarray([query_embedding], dtype="float32")
        query = self._normalize(query)

        distances, ids = self.index.search(query, k)

        results: List[Dict] = []
        id_row = ids[0]
        dist_row = distances[0]
        for i in range(len(id_row)):
            fid = int(id_row[i])
            if fid == -1:
                continue
            pos = self._faiss_to_pos.get(fid)
            if pos is None or pos < 0 or pos >= len(self.metadata):
                continue

            rec = self.metadata[pos].copy()
            rec["score"] = float(dist_row[i])  # cosine similarity ∈ [-1, 1]
            rec["id"] = fid  # stable external id = faiss id
            results.append(rec)

        return results

    def get_id_by_key(self, key: str) -> int:
        # Returns the stable FAISS id for a given key (url/id/fallback)
        return self.id_map.get(key, -1)

    def _rebuild_maps_from_metadata(self) -> None:
        """Rebuild id_map and faiss<->pos mappings deterministically from stored _key in metadata."""
        self.id_map.clear()
        self._faiss_to_pos.clear()
        self._pos_to_faiss.clear()
        for pos, rec in enumerate(self.metadata):
            key = self._key_for_idx(rec, pos)  # prefers stored _key if present
            fid = int(self._id64_from_key(key))
            self.id_map[key] = fid
            self._faiss_to_pos[fid] = pos
            self._pos_to_faiss[pos] = fid

    def delete(self, ids: List[int]) -> None:
        """
        Delete by external ids (FAISS ids returned from search()).
        """
        if self.index is None:
            raise RuntimeError("Index not initialized.")
        if not ids:
            return

        # Remove from FAISS
        faiss_ids = np.asarray(ids, dtype="int64")
        self.index.remove_ids(faiss_ids)

        # Remove from metadata (by positions), then rebuild maps
        to_remove_positions = set()
        for fid in ids:
            pos = self._faiss_to_pos.get(int(fid))
            if pos is not None:
                to_remove_positions.add(pos)

        if not to_remove_positions:
            return

        new_metadata = [rec for pos, rec in enumerate(self.metadata) if pos not in to_remove_positions]
        self.metadata = new_metadata

        # After positions shift, rebuild maps from stored _key so IDs stay consistent
        self._rebuild_maps_from_metadata()

    def delete_by_key(self, key: str):
        fid = self.get_id_by_key(key)
        if fid == -1:
            raise KeyError(f"No record found for key: {key}")
        self.delete([fid])

    def update(self, id: int, new_record: Dict) -> None:
        """
        Update a record identified by its external id (FAISS id).
        Replaces vector + metadata in place.
        """
        if self.index is None:
            raise RuntimeError("Index not initialized.")

        fid = int(id)
        pos = self._faiss_to_pos.get(fid)
        if pos is None:
            raise KeyError(f"No record found for id: {id}")

        # Remove old vector
        self.index.remove_ids(np.asarray([fid], dtype="int64"))

        # Add new vector with the SAME id
        embedding = np.asarray([new_record["embedding"]], dtype="float32")
        embedding = self._normalize(embedding)

        # Train if needed (safe no-op for non-trainable)
        self._maybe_train_ivf(embedding)

        self.index.add_with_ids(embedding, np.asarray([fid], dtype="int64"))

        # Update metadata (preserve stored _key if not provided)
        rec_copy = new_record.copy()
        rec_copy.pop("embedding", None)
        if "_key" not in rec_copy:
            # keep the previous key to maintain mapping stability
            prev_key = self.metadata[pos].get("_key")
            if prev_key:
                rec_copy["_key"] = prev_key
        self.metadata[pos] = rec_copy
        # maps remain valid (same fid, same pos)

    def save(self, path: str) -> None:
        if self.index is None:
            raise RuntimeError("Nothing to save — index is not initialized.")

        os.makedirs(path, exist_ok=True)
        faiss.write_index(self.index, os.path.join(path, "embeddings.index"))

        # Persist metadata and minimal config
        payload = {
            "metadata": self.metadata,
            "config": {
                "index_type": self._index_type,
                "ivf_nlist": self._ivf_nlist,
                "pq_m": self._pq_m,
                "pq_nbits": self._pq_nbits,
                "hnsw_M": self._hnsw_M,
                "hnsw_efSearch": self._hnsw_efSearch,
                "hnsw_efConstruction": self._hnsw_efConstruction,
            },
        }
        with open(os.path.join(path, "metadata.meta"), "wb") as f:
            pickle.dump(payload, f)

    def load(self, path: str) -> None:
        self.index = faiss.read_index(os.path.join(path, "embeddings.index"))

        with open(os.path.join(path, "metadata.meta"), "rb") as f:
            payload = pickle.load(f)

        # Backward compatibility: handle old format (list only)
        if isinstance(payload, dict) and "metadata" in payload:
            self.metadata = payload["metadata"]
            cfg = payload.get("config", {})
            self._index_type = cfg.get("index_type", "flat")
            self._ivf_nlist = cfg.get("ivf_nlist", self._ivf_nlist)
            self._pq_m = cfg.get("pq_m", self._pq_m)
            self._pq_nbits = cfg.get("pq_nbits", self._pq_nbits)
            self._hnsw_M = cfg.get("hnsw_M", self._hnsw_M)
            self._hnsw_efSearch = cfg.get("hnsw_efSearch", self._hnsw_efSearch)
            self._hnsw_efConstruction = cfg.get("hnsw_efConstruction", self._hnsw_efConstruction)
        else:
            # Older versions stored only the list
            self.metadata = payload

        # Rebuild maps deterministically from metadata (uses stored _key if present)
        self._rebuild_maps_from_metadata()

        # Dim is embedded in the FAISS index already
        try:
            self.dim = self.index.d
        except Exception:
            pass
