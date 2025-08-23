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
        # print(full_prompt)  # keep disabled in production

        response = self.chatbot.generate(full_prompt).strip()
        if response == "N":
            return "I'm sorry, I couldn't find any relevant information to answer that question."
        return response

    # === NEW: lightweight query rewriter ===
    def rewrite_query(self, question: str, hints: list[str], max_chars: int = 300) -> str | None:
        """
        Ask the LLM for a surgical rewrite of the query to improve retrieval.
        Returns None if no rewrite is needed.
        - hints: short strings like top headings, anchor texts, or page titles.
        """
        hints_text = "; ".join(hints[:8])[:1000]
        prompt = (
            "You help reformulate search queries to retrieve the most relevant website chunks.\n"
            "Original query:\n"
            f"{question.strip()}\n\n"
            "Context hints (headings/anchors):\n"
            f"{hints_text}\n\n"
            "Rewrite the query to be clearer and more specific for retrieval.\n"
            "If the original is already optimal, answer exactly: SAME\n"
            f"Limit to {max_chars} characters. Output only the query text or SAME."
        )
        rewritten = self.chatbot.generate(prompt).strip()
        if not rewritten or rewritten.upper() == "SAME":
            return None
        return rewritten
