from bs4 import BeautifulSoup, Tag
from typing import List, Dict
import uuid

class SlidingTextChunker:
    def __init__(self, max_words: int = 350, overlap: int = 50):
        self.max_words = max_words
        self.overlap = overlap

    def _clean_html(self, html: str) -> BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "footer", "nav", "form"]):
            tag.decompose()
        return soup

    def _sliding_window_chunks(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk_words = words[i:i + self.max_words]
            chunks.append(" ".join(chunk_words))
            i += self.max_words - self.overlap
        return chunks

    def _group_by_headings(self, soup: BeautifulSoup) -> List[str]:
        sections = []
        current_section = []

        heading_tags = ["h1", "h2", "h3", "h4", "h5", "h6"]
        body = soup.body or soup

        for el in body.descendants:
            if isinstance(el, Tag):
                if el.name in heading_tags:
                    if current_section:
                        sections.append(" ".join(current_section))
                        current_section = []
                    current_section.append(el.get_text(strip=True))
                elif el.name in ["p", "li", "span", "pre", "td", "code"]:
                    text = el.get_text(strip=True)
                    if text:
                        current_section.append(text)

        if current_section:
            sections.append(" ".join(current_section))
        return sections

    def _extract_div_blocks(self, soup: BeautifulSoup) -> List[str]:
        div_blocks = []
        for div in soup.find_all("div"):
            text = div.get_text(separator=" ", strip=True)
            if text and len(text.split()) > 10:
                div_blocks.append(text)
        return div_blocks

    def chunk_html(self, html: str, url: str) -> List[Dict]:
        soup = self._clean_html(html)

        # Try structured heading chunking first
        sections = self._group_by_headings(soup)

        # Fallback to divs if no heading sections
        if not sections:
            sections = self._extract_div_blocks(soup)

        # Last fallback: whole body
        if not sections:
            body = soup.body or soup
            full_text = body.get_text(separator=" ", strip=True)
            sections = [full_text] if full_text else []

        all_chunks = []
        for section in sections:
            for chunk in self._sliding_window_chunks(section):
                all_chunks.append({
                    "id": str(uuid.uuid4()),
                    "url": url,
                    "text": chunk,
                    "tokens": len(chunk.split())
                })

        return all_chunks

DefaultChunker = SlidingTextChunker
