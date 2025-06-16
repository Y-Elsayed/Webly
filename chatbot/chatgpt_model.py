from chatbot.base_chatbot import Chatbot
from openai import OpenAI

class ChatGPTModel(Chatbot):
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        """ChatGPT model wrapper using the new OpenAI client."""
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9
        )
        return response.choices[0].message.content.strip()
