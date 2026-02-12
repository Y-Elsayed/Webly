from abc import ABC, abstractmethod

import trafilatura
from bs4 import BeautifulSoup


class TextExtractor(ABC):
    """
    Abstract base class for HTML text extraction.
    Subclasses should implement __call__ method to extract text from the HTML,
    and return a dict with the url, extracted text (as 'text'), and any other relevant info.
    """

    @abstractmethod
    def __call__(self, url: str, html: str) -> dict:
        raise NotImplementedError("Subclasses must implement __call__")


# --- Cloudflare Email Decoding Helpers ---
def _decode_cf_email(encoded: str) -> str:
    """Decode Cloudflare's email obfuscation (data-cfemail)."""
    r = bytes.fromhex(encoded)
    key = r[0]
    return "".join(chr(b ^ key) for b in r[1:])


def _replace_cf_emails(html: str) -> str:
    """Replace Cloudflare-protected emails in raw HTML with decoded ones."""
    soup = BeautifulSoup(html, "html.parser")

    for span in soup.find_all("span", class_="__cf_email__"):
        data = span.get("data-cfemail")
        if data:
            try:
                decoded = _decode_cf_email(data)
                span.string = decoded  # replace placeholder with decoded email
                span.attrs.pop("data-cfemail", None)
            except Exception:
                continue

    return str(soup)


# --- Default Extractor (with CF fix) ---
class TrafilaturaTextExtractor(TextExtractor):
    def __call__(self, url: str, html: str) -> dict:
        # Preprocess HTML to replace Cloudflare obfuscated emails
        html = _replace_cf_emails(html)

        extracted = trafilatura.extract(html)
        if not extracted:
            return {}

        return {"url": url, "text": extracted, "length": len(extracted)}


# Default alias for convenience
DefaultTextExtractor = TrafilaturaTextExtractor
