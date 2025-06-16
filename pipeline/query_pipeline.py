from chatbot.webly_chat_agent import WeblyChatAgent
from typing import Optional

class QueryPipeline:
    def __init__(self, chat_agent: WeblyChatAgent, recrawl_fn: Optional[callable] = None, score_threshold: float = 0.6):
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn
        self.score_threshold = score_threshold

    def query(self, question: str, retry_on_weak: bool = True) -> str:
        query_embedding = self.chat_agent.embedder.embed(question)
        results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        top_score = max((r.get("score", 0) for r in results), default=0)

        if retry_on_weak and top_score < self.score_threshold and self.recrawl_fn:
            self.chat_agent.logger.info(
                f"Top similarity score ({top_score:.2f}) below threshold ({self.score_threshold}). Triggering re-crawl."
            )
            self.recrawl_fn()
            results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)
            top_score = max((r.get("score", 0) for r in results), default=0)

        if not results or top_score < self.score_threshold:
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        context = "\n\n".join([
            f"Source: {r.get('metadata', {}).get('url', 'N/A')}\n{r['text']}"
            for r in results if "text" in r
        ]).strip()

        if not context:
            return "I'm sorry, I couldn't find any relevant information to answer that question."

        return self.chat_agent.answer(question, context)
