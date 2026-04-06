from abc import ABC, abstractmethod


class Chatbot(ABC):
    """
    Minimal interface for any LLM backend used by Webly.

    Implement this to plug in any chat model — OpenAI, Anthropic, local
    Ollama, or otherwise.  The only hard requirement is ``generate()``.
    Override ``context_window_tokens`` if your model's context window
    differs from the conservative 16 000-token default so that the
    retrieval budget is sized correctly.

    Example::

        class MyChatbot(Chatbot):
            context_window_tokens = 200_000  # Claude 3 Opus

            def generate(self, prompt: str) -> str:
                return my_llm_client.complete(prompt)
    """

    #: Advertise the model's context window so the query pipeline can
    #: size the retrieval context budget correctly.  Override this class
    #: attribute (or the property) in subclasses.
    context_window_tokens: int = 16_000

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return a text completion for *prompt*.

        Args:
            prompt: The full prompt string, including any system instructions
                    and retrieved context already formatted by the caller.

        Returns:
            The model's response as a plain string (no markdown fences or
            role prefixes — just the content).
        """
