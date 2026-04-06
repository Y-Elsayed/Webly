from abc import ABC, abstractmethod
from typing import List


class Embedder(ABC):
    """
    Interface for text embedding backends.

    Implement this to use any embedding model — OpenAI, HuggingFace
    sentence-transformers, Cohere, or a custom model.

    The only hard requirement is ``embed()``.  Expose ``dim`` and
    ``max_input_tokens`` as instance attributes so the pipeline can
    allocate the correct FAISS index size and chunk text safely.

    Example::

        class MyEmbedder(Embedder):
            dim = 768
            max_input_tokens = 512

            def embed(self, text: str) -> List[float]:
                return my_model.encode(text).tolist()
    """

    #: Output dimensionality of the embedding vectors.
    #: Must be set before ``IngestPipeline`` calls ``FaissDatabase.create(dim=…)``.
    dim: int

    #: Maximum number of tokens the model accepts in a single call.
    #: Used by the pipeline to split long chunks before embedding.
    max_input_tokens: int = 8192

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return a single embedding vector for *text*.

        Args:
            text: The input string to embed.

        Returns:
            A list of floats of length ``self.dim``.
            Return an empty list ``[]`` if the text is empty or un-embeddable.
        """

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings for a list of texts.

        The default implementation calls ``embed()`` for each item.
        Override for efficiency when the backend supports batch requests.

        Args:
            texts: List of input strings.

        Returns:
            List of embedding vectors in the same order as *texts*.
        """
        return [self.embed(t) for t in texts if t.strip()]
