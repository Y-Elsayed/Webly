from .vector_db import VectorDatabase
from typing import List, Dict
import faiss
import numpy as np
import pickle
import os

class FaissDatabase(VectorDatabase):

    
    def __init__(self, index_path: str = None):
        self.index_path = index_path
        self.index = None
        self.metadata = []
        self.dim = None
        self.id_map = {} # maps from key to idx, the key is the url or id of the record

        if index_path:
            self.load(index_path)

    
    def create(self, dim: int, index_type: str = "flat") -> None:
        """
        initialize the faiss index.
        """
        if index_type == "flat": # currently only supports flat index (still a poc)
            self.index = faiss.IndexFlatL2(dim)
        else:
            raise ValueError(f"Unsupported index type: {index_type}")

        self.metadata = []
        self.dim = dim


    
    def add(self, records: List[Dict]) -> None:
        """
        add records to the db
        record must have:
        - embedding : List[float]
        - metadata : anything other thing
        """
        if not self.index:
            raise RuntimeError("Index not created. Call create() first.")

        vectors = [rec["embedding"] for rec in records]
        arr = np.array(vectors).astype("float32")
        self.index.add(arr)
        
        for i, rec in enumerate(records):
            rec_copy = rec.copy()
            rec_copy.pop("embedding", None)

            next_idx = len(self.metadata)
            key = rec_copy.get("url") or rec_copy.get("id") or f"record_{next_idx}" 

            self.metadata.append(rec_copy)
            self.id_map[key] = next_idx


    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        if self.index is None:
            raise RuntimeError("Index not initialized.")
        
        query = np.array([query_embedding]).astype("float32")
        distances, indices = self.index.search(query, top_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            result = self.metadata[idx].copy()
            result["score"] = float(distances[0][i])
            result["id"] = idx
            results.append(result)
        
        return results

    def get_id_by_key(self, key: str) -> int:
        return self.id_map.get(key, -1)
    
    def _rebuild_id_map(self):
        self.id_map = {}
        for idx, rec in enumerate(self.metadata):
            key = rec.get("url") or rec.get("id") or f"record_{idx}"
            self.id_map[key] = idx


    def delete(self, ids: List[int]) -> None:
        if self.index is None:
            raise RuntimeError("Index not initialized.")

        keep = [i for i in range(len(self.metadata)) if i not in ids]
        
        new_metadata = [self.metadata[i] for i in keep]
        new_embeddings = [self.index.reconstruct(i) for i in keep]

        # (not sure if this is the best way, but it works for now)
        # I reconstruct the whole index, because I want to preserve the order of embeddings with metadata
        # the good part is that delete isn't expected to be called often
        self.index = faiss.IndexFlatL2(self.index.d)
        self.index.add(np.array(new_embeddings).astype("float32"))
        self.metadata = new_metadata

        self._rebuild_id_map()


    def delete_by_key(self, key: str):
        idx = self.get_id_by_key(key)
        if idx == -1:
            raise KeyError(f"No record found for key: {key}")
        self.delete([idx])
    
    def update(self, id: int, new_record: Dict) -> None:
        # update the record
        embedding = new_record["embedding"]
        self.delete([id])
        self.add([new_record])


    
    def save(self, path: str) -> None:
        if self.index is None:
            raise RuntimeError("Nothing to save — index is not initialized.")

        os.makedirs(path, exist_ok=True)

        faiss.write_index(self.index, os.path.join(path, "embeddings.index"))
        with open(os.path.join(path, "metadata.meta"), "wb") as f:
            pickle.dump(self.metadata, f)

    
    def load(self, path: str) -> None:
        self.index = faiss.read_index(os.path.join(path, "embeddings.index"))
        with open(os.path.join(path, "metadata.meta"), "rb") as f:
            self.metadata = pickle.load(f)

        # rebuilding the id_map
        # was thinking of saving it and loading it just like the embeddings and metadata
        # but for order & corruption safety, I think it's better to rebuild it, although any change in the order of the 
        # metadata is nearly impossible, but sanity checking is always good. (might optimize later)
        self._rebuild_id_map()



