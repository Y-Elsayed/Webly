import string
from chatbot.base_chatbot import Chatbot

class WeblyChatAgent:
    def __init__(self, embedder, vector_db, chatbot: Chatbot, top_k=5, prompt_template=None):
        self.embedder = embedder
        self.vector_db = vector_db
        self.chatbot = chatbot
        self.top_k = top_k

        self.system_prompt = (
            "You are an intelligent assistant helping users understand a specific website.\n\n"
            "You will be given:\n"
            "- A user question.\n"
            "- A set of documents retrieved from the website.\n\n"
            "Your task is to answer the question only if the documents contain enough relevant information "
            "to produce an accurate, helpful, and website-specific answer.\n\n"
            "Rules:\n"
            "1. If the documents include enough relevant information, answer confidently.\n"
            "2. If the question is clearly about the website (e.g., 'What is this website about?'), try your best "
            "to infer from what's available.\n"
            "3. If the question is unrelated (e.g., 'How do I swim?'), and no related info is present, do NOT answer.\n"
            "4. If you cannot confidently answer, respond only with the letter: \"N\"\n\n"
            "Never make up answers. Only use the content and purpose of the website."
        )

        default_prompt = (
            "User Question:\n{question}\n\nRetrieved Documents:\n{context}"
        )
        self.prompt_template = prompt_template or default_prompt

        required_fields = {"context", "question"}
        found_fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(self.prompt_template)
            if field_name
        }

        missing = required_fields - found_fields
        if missing:
            raise ValueError(f"Prompt template is missing required placeholders: {', '.join(missing)}")

    def answer(self, question: str, context: str) -> str:
        context = context.strip()
        if not context:
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        prompt = self.prompt_template.format(context=context, question=question)
        full_prompt = f"{self.system_prompt}\n\n{prompt}"

        response = self.chatbot.generate(full_prompt).strip()

        if response == "N":
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        return response
