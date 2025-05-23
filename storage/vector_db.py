from abc import ABC, abstractmethod
from typing import List, Dict

# I created this file in case I (or hopefully someone else, since it's open source) need to implement different vector databases in the future.

class VectorDatabase(ABC):
    """
    Abstract base class for a vector database backend.
    Implementations must define how vectors are added, searched, saved, and loaded.
    """

    @abstractmethod
    def add(self, records: List[Dict]) -> None:
        """
        Add a  list of records to the vector database.
        """
        pass

    @abstractmethod
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """
        Search the database using a query embedding and return top-k matching records and return a list of records
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
