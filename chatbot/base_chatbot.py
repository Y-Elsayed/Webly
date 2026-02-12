from abc import ABC, abstractmethod


class Chatbot(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        this is the chatbot wrapper interface to make it easy to use any LLM backend.
        generate a response based on the given prompt.

        """
        pass
