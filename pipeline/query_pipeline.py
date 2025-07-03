from chatbot.webly_chat_agent import WeblyChatAgent
from typing import Optional
from collections import defaultdict


class QueryPipeline:
    def __init__(self, chat_agent: WeblyChatAgent, recrawl_fn: Optional[callable] = None):
        self.chat_agent = chat_agent
        self.recrawl_fn = recrawl_fn
        # self.max_context_chars = 12000  # Plenty for GPT-4o mini

    def query(self, question: str, retry_on_empty: bool = True) -> str:
        query_embedding = self.chat_agent.embedder.embed(question)

        results = self.chat_agent.vector_db.search(
            query_embedding,
            top_k=self.chat_agent.top_k
        )

        if retry_on_empty and not results and self.recrawl_fn:
            self.chat_agent.logger.info("[QueryPipeline] No context found. Triggering re-crawl.")
            self.recrawl_fn()
            results = self.chat_agent.vector_db.search(query_embedding, top_k=self.chat_agent.top_k)

        if not results:
            return "Sorry, I couldn't find relevant information."

        # Step 1: Group by top-level heading (hierarchy[0])
        section_groups = defaultdict(list)
        for r in results:
            text = r.get("text", "").strip()
            if not text:
                continue
            section_title = r.get("hierarchy", ["General"])[0]
            section_groups[section_title].append(r)

        # Step 2: Assemble full sections into context
        context_chunks = []
        total_chars = 0
        seen_ids = set()

        for section, chunks in section_groups.items():
            section_chunks = []
            for r in chunks:
                uid = r.get("id")
                if uid and uid in seen_ids:
                    continue
                seen_ids.add(uid)

                text = r.get("text", "").strip()
                if not text:
                    continue

                url = r.get("url") or r.get("source", "N/A")
                subheadings = " > ".join(r.get("hierarchy", []))
                prefix = f"[{subheadings}]\n" if subheadings else ""
                chunk_text = f"{prefix}{text}\n\n(Source: {url})"
                section_chunks.append(chunk_text)

            full_section = "\n\n".join(section_chunks).strip()
            # if total_chars + len(full_section) > self.max_context_chars:
            #     break

            context_chunks.append(full_section)
            total_chars += len(full_section)

        context = "\n\n---\n\n".join(context_chunks).strip()
        # print("DEBUG Context:\n", context[:3000])  # Optional debug preview

        return self.chat_agent.answer(question, context)
