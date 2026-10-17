import hashlib
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup, Tag


class TextChunker(ABC):
    """
    Interface for HTML/text chunking strategies.

    Implement this to swap in your own chunking logic — recursive
    character splitting, semantic paragraph splitting, fixed-token
    windows, or anything else.

    ``SemanticPageProcessor`` accepts any ``TextChunker`` in its
    constructor, so no other code changes are needed.

    Example::

        class FixedTokenChunker(TextChunker):
            def __init__(self, max_tokens: int = 512):
                self.max_tokens = max_tokens

            def chunk_html(self, html: str, url: str = "") -> List[Dict]:
                # strip HTML, split by token count
                text = strip_tags(html)
                return [
                    {"text": chunk, "hierarchy": [], "outgoing_links": []}
                    for chunk in split_by_tokens(text, self.max_tokens)
                ]
    """

    @abstractmethod
    def chunk_html(self, html: str, url: str = "") -> List[Dict]:
        """Split raw HTML into structured chunks.

        Args:
            html: Raw HTML string of the page.
            url:  Canonical URL of the page (used for stable chunk IDs
                  and resolving relative links).

        Returns:
            List of chunk dicts.  Each dict must contain at least:

            - ``"text"`` (str): The plain-text content of the chunk.

            Optional but used by the pipeline when present:

            - ``"hierarchy"`` (List[str]): Heading breadcrumb, e.g.
              ``["Getting Started", "Installation"]``.
            - ``"outgoing_links"`` (List[Dict]): Links found in this
              chunk, each with ``"target"`` and ``"anchor_text"`` keys.
            - ``"id"`` (str): Stable deterministic ID for graph joins.
        """


class SlidingTextChunker(TextChunker):
    def __init__(self, max_words: int = 350, overlap: int = 50):
        if max_words < 1 or overlap < 0:
            raise ValueError("max_words must be positive and overlap nonnegative")
        self.max_words = max_words
        self.overlap = overlap
        self._heading_re = re.compile(r"^h([1-6])$", re.I)

    # ---------- Cleaning ----------
    def _clean_html(self, html: str) -> BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "form", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return soup

    # ---------- Utilities ----------
    @staticmethod
    def _text(t: Tag) -> str:
        return t.get_text(" ", strip=True)

    @staticmethod
    def _hash_id(url: str, hierarchy: List[str], local_idx: int) -> str:
        base = f"{url}|{' > '.join(hierarchy)}|{local_idx}"
        return hashlib.blake2b(base.encode("utf-8"), digest_size=10).hexdigest()

    def _table_to_md(self, table: Tag) -> str:
        # very lightweight markdown rendering for tables
        rows = []
        for tr in table.find_all("tr"):
            cells = [self._text(td) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            sep = "| " + " | ".join("---" for _ in rows[0].split("|")[1:-1]) + " |"
            if len(rows) >= 2:
                return "\n".join([rows[0], sep] + rows[1:])
        return "\n".join(rows)

    def _block_text_and_anchors(self, node: Tag) -> Tuple[str, List[Dict]]:
        """
        Return plain text for the block and anchors inside it as [{'anchor_text','href'}...].
        Handles tables specially.
        """
        anchors = []
        for a in node.find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            if txt:
                anchors.append({"anchor_text": txt, "target": a["href"]})

        # handle tables
        if node.name == "table":
            txt = self._table_to_md(node)
        else:
            txt = self._text(node)
        return txt, anchors

    # ---------- Sectioning by headings ----------
    def _iter_sections(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Returns a list of sections:
        {
          'hierarchy': [h1, h2, ...],
          'blocks': [ {'text':..., 'anchors':[...]} , ...]
        }
        We walk headings in document order; a section spans until the next heading of same or higher level.
        """
        body = soup.body or soup
        headings = body.find_all(self._heading_re)
        sections: List[Dict] = []

        # If no headings at all, treat entire body as one section
        if not headings:
            blocks = []
            # block-level nodes likely to contain meaningful text
            for node in body.find_all(["p", "li", "pre", "code", "blockquote", "td", "table"]):
                if any(
                    parent.name in {"p", "li", "pre", "code", "blockquote", "td", "table"}
                    for parent in node.parents if isinstance(parent, Tag)
                ):
                    continue
                txt, anchors = self._block_text_and_anchors(node)
                if txt and len(txt.split()) > 3:
                    blocks.append({"text": txt, "anchors": anchors})
            if blocks:
                sections.append({"hierarchy": [], "blocks": blocks})
            return sections

        # Build sections delimited by headings
        def level_of(tag: Tag) -> int:
            m = self._heading_re.match(tag.name)
            return int(m.group(1)) if m else 6

        path: List[str] = []
        blocks: List[Dict] = []
        block_names = {"p", "li", "pre", "code", "blockquote", "td", "table"}
        for node in body.descendants:
            if not isinstance(node, Tag):
                continue
            if self._heading_re.match(node.name or ""):
                if blocks:
                    sections.append({"hierarchy": path[:], "blocks": blocks})
                    blocks = []
                curr_lvl = level_of(node)
                path = path[: curr_lvl - 1]
                while len(path) < curr_lvl - 1:
                    path.append("")
                path.append(self._text(node))
            elif node.name in block_names:
                if any(parent.name in block_names for parent in node.parents if isinstance(parent, Tag)):
                    continue
                txt, anchors = self._block_text_and_anchors(node)
                if txt and len(txt.split()) > 3:
                    blocks.append({"text": txt, "anchors": anchors})
        if blocks:
            sections.append({"hierarchy": path[:], "blocks": blocks})

        return sections

    # ---------- Chunking over blocks with sliding window ----------
    def _chunk_section_blocks(self, url: str, hierarchy: List[str], blocks: List[Dict]) -> List[Dict]:
        """
        Merge consecutive blocks into chunks up to max_words with overlap, carrying anchors that fall inside.
        """
        words: List[str] = []
        anchors: List[Tuple[int, Dict]] = []
        for block in blocks:
            start = len(words)
            words.extend(block["text"].split())
            anchors.extend((start, anchor) for anchor in block.get("anchors", []))
        chunks: List[Dict] = []
        step = max(1, self.max_words - min(self.overlap, self.max_words - 1))
        for start in range(0, len(words), step):
            end = min(start + self.max_words, len(words))
            chunks.append({
                "id": self._hash_id(url, hierarchy, len(chunks)),
                "url": url,
                "text": " ".join(words[start:end]),
                "tokens": end - start,
                "start_word": start,
                "end_word": end,
                "hierarchy": hierarchy[:],
                "outgoing_links": [anchor for offset, anchor in anchors if start <= offset < end],
            })
            if end == len(words):
                break
        return chunks

    def chunk_html(self, html: str, url: str) -> List[Dict]:
        soup = self._clean_html(html)
        sections = self._iter_sections(soup)

        all_chunks: List[Dict] = []
        for sec in sections:
            hierarchy = [h for h in sec["hierarchy"] if h]  # drop empty placeholders
            blocks = sec["blocks"]
            sec_chunks = self._chunk_section_blocks(url, hierarchy, blocks)
            all_chunks.extend(sec_chunks)

        # If nothing at all, fallback to whole body text
        if not all_chunks:
            body = soup.body or soup
            full_text = body.get_text(separator=" ", strip=True)
            if full_text:
                all_chunks.extend(self._chunk_section_blocks(url, [], [{"text": full_text, "anchors": []}]))

        return all_chunks


DefaultChunker = SlidingTextChunker
