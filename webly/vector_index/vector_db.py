from abc import ABC, abstractmethod
from typing import Dict, List

# Base interface for vector DB backends, so additional implementations can
# be added without changing pipeline code.


class VectorDatabase(ABC):
    """
    Abstract base class for a vector database backend.
    Implementations must define how vectors are added, searched, saved, and loaded.
    """

    @abstractmethod
    def create(self, dim: int, index_type: str = "flat") -> None:
        """
        Initialize a new vector index with the given dimension and type.
        """
        pass

    @abstractmethod
    def add(self, records: List[Dict]) -> None:
        """
        Add a list of records to the vector database.
        Each record must include an 'embedding' and optionally metadata.
        """
        pass

    @abstractmethod
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """
        Search the database using a query embedding and return the top-k most similar records.
        """
        pass

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """
        Delete records from the vector database by their IDs.
        """
        pass

    @abstractmethod
    def update(self, id: str, new_record: Dict) -> None:
        """
        Update a specific record's embedding or metadata by its ID.
        """
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """
        Persist the vector index and metadata to disk.
        """
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """
        Load the vector index and metadata from disk.
        """
        pass
