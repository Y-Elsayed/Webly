import string
from chatbot.base_chatbot import Chatbot

class WeblyChatAgent:
    def __init__(self, embedder, vector_db, chatbot: Chatbot, top_k=5, prompt_template=None):
        self.embedder = embedder
        self.vector_db = vector_db
        self.chatbot = chatbot
        self.top_k = top_k
        
        default_prompt = (
            "Answer the following question based on the context:\n\n{context}\n\nQuestion: {question}"
        )

        self.prompt_template = prompt_template or default_prompt

        # validating the prompt template, should contain {context} and {question}
        # it might be a bit inconvenient, but for poc sake, I will keep it this way for now
        required_fields = {"context", "question"}
        found_fields = {field_name for _, field_name, _, _ in string.Formatter().parse(self.prompt_template) if field_name}
        missing = required_fields - found_fields

        if missing:
            raise ValueError(f"Prompt template is missing required placeholders: {', '.join(missing)}")

    def answer(self, question: str, context: str) -> str:
        context = context.strip()

        if not context:
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        # build the prompt
        prompt = self.prompt_template.format(context=context, question=question)
        print(f"Prompt: {prompt}")

        # generate the answer
        return self.chatbot.generate(prompt)



