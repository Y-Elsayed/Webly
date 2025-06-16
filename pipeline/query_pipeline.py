from chatbot.webly_chat_agent import WeblyChatAgent
from typing import Optional

class QueryPipeline:
    def __init__(self, chat_agent: WeblyChatAgent, recrawl_fn: Optional[callable] = None):
        """
        Pipeline to handle embedding, vector search, and generating a response.

        Args:
            chat_agent (WeblyChatAgent): Handles embedding, search, and answering.
            recrawl_fn (callable, optional): Function to re-crawl the website if no relevant context is found.
        """
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn

    def query(self, question: str, retry_on_empty: bool = True) -> str:
        # Step 1: Embed the question
        query_embedding = self.chat_agent.embedder.embed(question)

        # Step 2: Search in vector DB
        results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        # Step 3: Optional recrawl if nothing found
        if retry_on_empty and not results and self.recrawl_fn:
            self.chat_agent.logger.info("No context found. Triggering re-crawl.")
            self.recrawl_fn()
            results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        # Step 4: Build context string
        context = "\n\n".join([
            f"Source: {r.get('url', 'N/A')}\n{r.get('text', '')}"
            for r in results if "text" in r
        ]).strip()

        # Step 5: Let the LLM decide if it can answer
        return self.chat_agent.answer(question, context)
