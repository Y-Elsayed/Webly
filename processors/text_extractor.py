import trafilatura

class TextExtractor:
    def extract(self, html: str) -> str:
        return trafilatura.extract(html) or ""
