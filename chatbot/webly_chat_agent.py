import string
from chatbot.base_chatbot import Chatbot

class WeblyChatAgent:
    def __init__(
        self,
        embedder,
        vector_db,
        chatbot: Chatbot,
        top_k=5,
        prompt_template=None,
        system_prompt: str = None 
    ):
        self.embedder = embedder
        self.vector_db = vector_db
        self.chatbot = chatbot
        self.top_k = top_k

        default_system_prompt = """
        You are a helpful, intelligent assistant designed to answer questions about the content and purpose of a specific website.

        You are conversational but do not overdo greetings — respond naturally to user tone. Only greet if the user greets you first and it fits the flow.

        You never make up information. You only use the retrieved website content provided to you.

        Your behavior should follow these rules:

        1. If the user's question is clearly related to the website and you have enough relevant information, respond confidently and naturally.
        2. If the user asks about the general purpose of the website, summarize it based on the available content.
        3. If the question is unrelated to the website, or if the content is insufficient to provide a helpful answer, respond only with the letter: "N".
        4. If the answer is based on a specific section of the website, include the link to that section if it was provided in the content.
        5. Never say “according to the documents” unless it adds real clarity — write as if you're naturally knowledgeable but strictly based on the provided content.

        You are not a generic chatbot — your only knowledge comes from the retrieved website content.
        """


        self.system_prompt = system_prompt or default_system_prompt

        default_prompt = (
            "User: {question}\n\n"
            "Website Content:\n{context}"
        )
        self.prompt_template = prompt_template or default_prompt

        # Ensure required placeholders exist in the prompt template
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
        full_prompt = f"{self.system_prompt.strip()}\n\n{prompt.strip()}"

        response = self.chatbot.generate(full_prompt).strip()

        if response == "N":
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        return response
