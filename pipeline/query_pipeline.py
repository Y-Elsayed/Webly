from chatbot.webly_chat_agent import WeblyChatAgent
from typing import Optional

class QueryPipeline:
    def __init__(self, chat_agent: WeblyChatAgent, recrawl_fn: Optional[callable] = None, score_threshold: float = 0.6):
        """
        init the query pipeline.

        Args:
            chat_agent (WeblyChatAgent): The main agent for embedding, retrieval, and answering.
            recrawl_fn (callable, optional): Function to trigger re-crawling when retrieval is weak.
            score_threshold (float): Minimum acceptable similarity score to consider the context strong.
        """
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn
        self.score_threshold = score_threshold

    def query(self, question: str, retry_on_weak: bool = True) -> str:
        query_embedding = self.chat_agent.embedder.embed(question)
        results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        top_score = max((r.get("score", 0) for r in results), default=0)

        if retry_on_weak and top_score < self.score_threshold and self.recrawl_fn:
            print(f"Top similarity score ({top_score:.2f}) below threshold ({self.score_threshold}). Triggering re-crawl.") # for debugging, will remove later and add logging
            self.recrawl_fn()
            results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        context = "\n\n".join([r.get("text") or r.get("markdown") or "" for r in results])
        prompt = self.chat_agent.prompt_template.format(context=context, question=question)
        answer = self.chat_agent.chatbot.generate(prompt)

        return answer
