import json
import string
from pathlib import Path
from typing import List, Optional, Tuple

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

        default_system_prompt = self._load_default_system_prompt()
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

    def _load_default_system_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent / "prompts" / "webly_chat_agent_system.txt"
        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            pass

        return (
            "You are a helpful assistant that answers questions based solely on the content of a specific website.\n"
            "Never use outside knowledge.\n"
            "If the answer is not in the provided context, respond only with: `N`."
        )

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

    def answer_with_support(self, question: str, context: str) -> Tuple[str, str]:
        """
        Return a tuple: (answer_text, support_flag), where support_flag is 'Y' or 'N'.
        'Y' means the answer is supported by provided context.
        """
        context = context.strip()
        if not context:
            return "I'm sorry, I couldn't find any relevant information to answer that question.", "N"

        prompt = self.prompt_template.format(context=context, question=question)
        full_prompt = (
            f"{self.system_prompt.strip()}\n\n{prompt.strip()}\n\n"
            "Return JSON only with this exact schema:\n"
            '{"answer":"<final answer text>", "supported":"Y|N"}\n'
            "- Set supported='Y' only if the answer is supported by the provided context.\n"
            "- Set supported='N' if the answer is not sufficiently supported.\n"
            "- Do not include markdown fences or extra keys."
        )

        raw = (self.chatbot.generate(full_prompt) or "").strip()
        try:
            parsed = json.loads(raw)
            answer = str(parsed.get("answer") or "").strip()
            supported = str(parsed.get("supported") or "").strip().upper()
            if supported not in {"Y", "N"}:
                supported = "N"
            if not answer:
                answer = "I'm sorry, I couldn't find any relevant information to answer that question."
            return answer, supported
        except Exception:
            # Safe fallback: use existing answer path + answerability probe.
            answer = self.answer(question, context)
            supported = "Y" if self._judge_answerability(question, context) else "N"
            return answer, supported

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
