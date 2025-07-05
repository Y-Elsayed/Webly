from typing import List
from .text_chunkers import HeaderSlidingChunker


class PageProcessor:
    def __init__(self, extractor, chunker):
        self.extractor = extractor
        self.chunker = chunker

    def process(self, url: str, html: str) -> List[dict]:
        extracted = self.extractor(url, html)
        text = extracted.get("text")
        if not text:
            return []

        chunks = self.chunker.chunk_text(text)
        return [
            {
                "url": url,
                "chunk_index": i,
                "text": chunk,
                "length": len(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]


class SemanticPageProcessor:
    def __init__(self, extractor, chunker: HeaderSlidingChunker):
        self.extractor = extractor
        self.chunker = chunker

    def process(self, url: str, html: str) -> List[dict]:
        extracted = self.extractor(url, html)
        text = extracted.get("text")
        if not text:
            return []

        return [
            {
                "url": url,
                "chunk_index": i,
                "text": chunk,
                "length": len(chunk)
            }
            for i, chunk in enumerate(self.chunker.chunk_text(text))
        ]
