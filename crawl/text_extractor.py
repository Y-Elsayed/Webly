from bs4 import BeautifulSoup

class TextExtractor:
    def __call__(self, url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return {
            "url": url,
            "text": text,
            "length": len(text)
        }
