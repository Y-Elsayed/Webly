from typing import List


class PageProcessor:
    def __init__(self, extractor, chunker):
        self.extractor = extractor
        self.chunker = chunker

    def process(self, url: str, html: str) -> List[dict]:
        extracted = self.extractor(url, html)
        text = extracted.get("text")
        if not text:
            return []

        chunks = self.chunker.chunk_html(text)
        return [{"url": url, "chunk_index": i, "text": chunk, "length": len(chunk)} for i, chunk in enumerate(chunks)]


class SemanticPageProcessor:
    def __init__(self, extractor, chunker):
        self.extractor = extractor
        self.chunker = chunker

    def process(self, url: str, html: str) -> List[dict]:
        """
        IMPORTANT: pass the raw HTML to the chunker so we can keep structure (headings/anchors).
        The extractor can still be used for other signals if needed.
        """
        self.extractor(url, html)  # preserve compatibility if extractor has side effects
        # Use raw HTML here to preserve headings/anchors
        chunks = self.chunker.chunk_html(html, url)
        return [
            {
                "url": url,
                "chunk_index": i,
                "text": ch["text"],
                "length": ch.get("tokens", len(ch["text"].split())),
                # carry structural metadata forward
                "hierarchy": ch.get("hierarchy", []),
                "outgoing_links": ch.get("outgoing_links", []),
                "id": ch.get("id"),  # deterministic id for graph joins
            }
            for i, ch in enumerate(chunks)
        ]
