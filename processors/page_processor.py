class PageProcessor:
    def __init__(self, extractor, chunker):
        self.extractor = extractor
        self.chunker = chunker

    def process(self, url: str, html: str) -> list[dict]:
        extracted = self.extractor(url, html)
        text = extracted.get("text")
        if not text:
            return []

        chunks = self.chunker.split(text)
        return [
            {
                "url": url,
                "chunk_index": i,
                "text": chunk,
                "length": len(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]
