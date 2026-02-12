import string
from typing import List, Optional

from chatbot.base_chatbot import Chatbot


class WeblyChatAgent:
    def __init__(
        self,
        embedder,
        vector_db,
        chatbot: Chatbot,
        top_k: int = 5,
        prompt_template: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        self.embedder = embedder
        self.vector_db = vector_db
        self.chatbot = chatbot
        self.top_k = top_k

        default_system_prompt = """
        You are a helpful assistant that answers questions based solely on the content
        of a specific website.

        You speak as if you are the website: natural, direct, and informative.
        Do not over-greet or over-explain. Only greet if the user does first and it
        fits the flow.

        Your answers follow these principles:

        1. If the question is clearly about something covered on the site, answer
           confidently and concisely, using only the provided content.
        2. If the user asks about the overall purpose of the site, summarize it
           naturally and clearly.
        3. If the question is not related to the website, or there is not enough
           information to answer meaningfully, respond only with: `N`.
        4. If an answer is based on a specific section, include the link (if
           available) at the end of the response.
        5. If the user asks about something the site does not fully cover, briefly
           share what is known and direct them to the most relevant section.

        Avoid saying "the website says" or "according to the site" unless needed
        for clarity. Speak as the website itself.
        """
        self.system_prompt = system_prompt or default_system_prompt

        default_prompt = "User: {question}\n\n" "Website Content:\n{context}"
        self.prompt_template = prompt_template or default_prompt

        required_fields = {"context", "question"}
        found_fields = {
            field_name for _, field_name, _, _ in string.Formatter().parse(self.prompt_template) if field_name
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

    def rewrite_query(self, question: str, hints: List[str], max_chars: int = 500) -> Optional[str]:
        """
        Ask the LLM for a surgical rewrite (or small set of sub-queries) to improve retrieval.
        Returns None if no rewrite is needed.

        - hints: short strings like top headings, anchor texts, or page titles.
        - Output contract preserved: str | None. If multiple queries are needed, they are returned
          joined by " || " so the caller can split.
        """
        hints_text = "; ".join([h for h in hints[:8] if h])[:1000]
        prompt = (
            "You reformulate search queries to retrieve the most relevant website chunks.\n"
            "Original query:\n"
            f"{question.strip()}\n\n"
            "Context hints (headings/anchors):\n"
            f"{hints_text}\n\n"
            "If the original is already optimal, output exactly: SAME\n"
            "Otherwise, return either: a single improved query, OR a short list of 2-4 focused sub-queries.\n"
            "- If returning a list, use one bullet per line starting with '-' or a number.\n"
            f"Limit the whole output to {max_chars} characters or less. Output only the query text(s) or SAME."
        )
        raw = (self.chatbot.generate(prompt) or "").strip()
        if not raw or raw.upper() == "SAME":
            return None
        return self._normalize_rewrites(raw)

    def _normalize_rewrites(self, text: str) -> Optional[str]:
        """Normalize LLM output to one string. Multiple queries are joined by " || "."""
        lines = [ln.strip(" -*\t").strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 2:
            merged = " || ".join(lines)
            return merged[:3000] if merged else None
        return text[:3000] if text else None

    def _judge_answerability(self, question: str, context: str) -> bool:
        """
        Quick LLM probe to check if the provided context is sufficient to answer the question.
        Returns True if the model is confident the question can be fully answered from context.
        """
        ctx_preview = context[:6000]
        probe = (
            "You are checking whether the following website context contains enough information "
            "to fully answer the question.\n"
            "Answer ONLY 'YES' or 'NO'.\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{ctx_preview}\n\n"
            "Sufficient?"
        )
        try:
            verdict = (self.chatbot.generate(probe) or "").strip().upper()
        except Exception:
            return False
        return verdict.startswith("Y")
