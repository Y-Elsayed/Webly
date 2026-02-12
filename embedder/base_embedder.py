from abc import ABC, abstractmethod
from typing import List


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        returns the embedding vector for the input text
        """
        pass
