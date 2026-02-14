from openai import OpenAI

from chatbot.base_chatbot import Chatbot


class ChatGPTModel(Chatbot):
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        """ChatGPT model wrapper using the new OpenAI client."""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        # Keep explicit attributes used by retrieval budget logic.
        self.model_name = model
        self.context_window_tokens = self._infer_context_window_tokens(model)

    @staticmethod
    def _infer_context_window_tokens(model: str) -> int:
        """
        Hard coded it for now, but later we can use the openai client to fetch the model details.
        """
        m = (model or "").lower()
        if "gpt-4.1" in m:
            return 1_000_000
        if "gpt-4o" in m or "o4" in m:
            return 128_000
        if "gpt-4" in m:
            return 128_000
        if "gpt-3.5" in m:
            return 16_000
        return 16_000

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
