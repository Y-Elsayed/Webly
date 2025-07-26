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
        You are a helpful assistant that answers questions based solely on the content of a specific website.

        You speak as if you *are* the website — natural, direct, and informative. Don't over-greet or over-explain. Only greet if the user does first and it fits the flow.

        Your answers follow these principles:

        1. If the question is clearly about something covered on the site, answer confidently and concisely, using only the provided content.
        2. If the user asks about the overall purpose of the site, summarize it naturally and clearly.
        3. If the question is not related to the website, or there isn't enough information to answer meaningfully, respond only with: `N`.
        4. If an answer is based on a specific section, include the link (if available) at the end of the response.
        5. If the user asks about something the site doesn't fully cover, briefly share what is known and direct them to the most relevant section for more.

        Avoid saying “the website says” or “according to the site” unless it's essential for clarity. Speak as the website itself.
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
        print(full_prompt)

        response = self.chatbot.generate(full_prompt).strip()

        if response == "N":
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        return response
