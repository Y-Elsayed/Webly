from bs4 import BeautifulSoup
import html2text
from abc import ABC, abstractmethod
import trafilatura

class TextExtractor(ABC):
    """
    Abstract base class for HTML text extraction.
    Subclasses should implement __call__ method to extract text from the HTML, and return
    a dict with the url, extracted text (as 'text'), and any other relevant info.
    """
    @abstractmethod
    def __call__(self, url: str, html: str) -> dict:
        raise NotImplementedError("Subclasses must implement __call__")


class TrafilaturaTextExtractor(TextExtractor):
    def __call__(self, url: str, html: str) -> dict:
        extracted = trafilatura.extract(html)
        if not extracted:
            return {}

        return {
            "url": url,
            "text": extracted,
            "length": len(extracted)
        }


class PlainTextExtractor(TextExtractor):
    """
    Extracts raw visible text from HTML using BeautifulSoup.
    Strips tags and outputs plain, unstructured text.
    """
    def __call__(self, url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        return {
            "url": url,
            "text": text,
            "length": len(text)
        }


class MarkdownTextExtractor(TextExtractor):
    """
    Converts HTML to Markdown using html2text.
    Markdown output is still stored as plain text in the 'text' field for consistency.
    """
    def __call__(self, url: str, html: str) -> dict:
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = False
        markdown = converter.handle(html)

        return {
            "url": url,
            "text": markdown,  # UNIFIED under 'text'
            "length": len(markdown)
        }
