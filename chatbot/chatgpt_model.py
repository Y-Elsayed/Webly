from chatbot.base_chatbot import Chatbot
import openai

class ChatGPTModel(Chatbot):
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        """chatbot wrapper for chatgpt"""
        openai.api_key = api_key
        self.model = model

    def generate(self, prompt: str) -> str:
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message["content"].strip()
