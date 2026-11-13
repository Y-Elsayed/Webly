import hashlib
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from webly.processors.table_extraction import table_blocks


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
        for tag in soup(["script", "style", "noscript", "input", "textarea", "button"]):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        # Display labels are published evidence, unlike option/control values.
        for option in soup.find_all("option", label=True):
            if option["label"]:
                option.string = option["label"]
        for group in soup.find_all("optgroup", label=True):
            if group["label"]:
                group.insert(0, NavigableString(group["label"]))
        return soup

    # ---------- Utilities ----------
    @staticmethod
    def _text(t: Tag) -> str:
        # Nested tables have their own evidence blocks, even inside a paragraph
        # or list item. Do not duplicate their values in the enclosing block.
        return " ".join(
            str(text).strip()
            for text in t.descendants
            if isinstance(text, NavigableString) and str(text).strip() and text.find_parent("table") is None
        )

    @staticmethod
    def _region(node) -> str:
        roles = {"main": "main", "navigation": "navigation", "contentinfo": "footer", "form": "form"}
        tags = {"main": "main", "nav": "navigation", "footer": "footer", "form": "form"}
        for parent in (node, *node.parents):
            if isinstance(parent, Tag):
                role = next((roles[r] for r in str(parent.get("role", "")).split() if r in roles), None)
                region = role or tags.get(parent.name)
                if region:
                    return region
        return "unknown"

    @staticmethod
    def _hash_id(url: str, hierarchy: List[str], local_idx: int) -> str:
        base = f"{url}|{' > '.join(hierarchy)}|{local_idx}"
        return hashlib.blake2b(base.encode("utf-8"), digest_size=10).hexdigest()

    def _block_text_and_anchors(self, node: Tag) -> Tuple[str, List[Dict]]:
        """
        Return plain text for the block and anchors inside it as [{'anchor_text','href'}...].
        Handles tables specially.
        """
        anchors = []
        for a in node.find_all("a", href=True):
            if a.find_parent("table") is not None:
                continue
            txt = a.get_text(" ", strip=True)
            if txt:
                anchors.append({"anchor_text": txt, "target": a["href"]})

        if node.name in {"pre", "code"}:
            txt = "```\n" + node.get_text().strip() + "\n```"
        else:
            txt = self._text(node)
        return txt, anchors

    # ---------- Sectioning by headings ----------
    def _iter_sections(self, soup: BeautifulSoup, url: str = "") -> List[Dict]:
        """
        Returns a list of sections:
        {
          'hierarchy': [h1, h2, ...],
          'blocks': [ {'text':..., 'anchors':[...]} , ...]
        }
        We walk headings in document order; a section spans until the next heading of same or higher level.
        """
        body = soup.body or soup
        sections: List[Dict] = []

        # Build sections delimited by headings
        def level_of(tag: Tag) -> int:
            m = self._heading_re.match(tag.name)
            return int(m.group(1)) if m else 6

        path: List[str] = []
        blocks: List[Dict] = []
        block_names = {"p", "li", "pre", "code", "blockquote", "td", "th", "table", "label", "legend", "option"}
        table_indices = {id(table): i for i, table in enumerate(body.find_all("table"))}
        for node in body.descendants:
            if isinstance(node, Tag) and node.name == "table":
                blocks.extend(
                    table_blocks(node, url=url, table_index=table_indices[id(node)], region=self._region(node))
                )
                continue
            if node.find_parent("table") is not None:
                continue
            if isinstance(node, NavigableString):
                if any(
                    parent.name in block_names or self._heading_re.match(parent.name or "")
                    for parent in node.parents
                    if isinstance(parent, Tag)
                ):
                    continue
                text = str(node).strip()
                if text:
                    anchor = node.find_parent("a", href=True)
                    anchors = [{"anchor_text": text, "target": anchor["href"]}] if anchor else []
                    blocks.append({"text": text, "anchors": anchors, "kind": "text", "region": self._region(node)})
                continue
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
                if txt:
                    blocks.append({"text": txt, "anchors": anchors, "kind": node.name, "region": self._region(node)})
        if blocks:
            sections.append({"hierarchy": path[:], "blocks": blocks})

        return sections

    # ---------- Chunking over blocks with sliding window ----------
    def _chunk_section_blocks(self, url: str, hierarchy: List[str], blocks: List[Dict]) -> List[Dict]:
        """
        Merge consecutive blocks into chunks up to max_words with overlap, carrying anchors that fall inside.
        """
        chunks: List[Dict] = []
        offset = 0
        word_offset = 0
        current = []
        current_words = 0

        def flush():
            nonlocal current, current_words
            if not current:
                return
            chunks.append(
                {
                    "id": self._hash_id(url, hierarchy, len(chunks)),
                    "url": url,
                    "text": "\n\n".join(block["text"] for block in current),
                    "tokens": current_words,
                    "start_word": current[0]["start_word"],
                    "end_word": current[-1]["end_word"],
                    "hierarchy": hierarchy[:],
                    "blocks": [dict(block) for block in current],
                    "outgoing_links": [anchor for block in current for anchor in block.get("anchors", [])],
                }
            )
            current, current_words = [], 0

        for index, block in enumerate(blocks):
            text = block["text"]
            spans = list(re.finditer(r"\S+", text))
            oversized = len(spans) > self.max_words
            prefix = ""
            metadata = block
            if block.get("kind") == "table" and oversized:
                prefix = " ".join(block.get("context_prefix", "")[:512].split()[: self.max_words // 3])
                if prefix:
                    prefix += "\n"
                # Source cell coordinates survive every slice. Full row values
                # already survive in the evidence slices and frozen source HTML;
                # copying them into every slice would amplify oversized rows.
                metadata = {
                    **block,
                    "original_text": "",
                    "context_prefix": prefix,
                    "caption": block.get("caption", "")[:512],
                    "cell_text_basis": "source_table",
                    "cells": [
                        {
                            **{k: v for k, v in cell.items() if k not in {"text", "header_cells"}},
                            "header_cells": [{**h, "text": h["text"][:512]} for h in cell["header_cells"]],
                        }
                        for cell in block.get("cells", [])
                    ],
                }
            size = max(1, self.max_words - len(prefix.split()))
            step = max(1, size - min(self.overlap, size - 1))
            starts = range(0, len(spans), step) if oversized else [0]
            for start in starts:
                if not spans:
                    continue
                end = min(start + size, len(spans))
                begin_char, end_char = spans[start].start(), spans[end - 1].end()
                piece = text[begin_char:end_char]
                if block.get("kind") in {"pre", "code"}:
                    if start:
                        piece = "```\n" + piece
                    if end < len(spans):
                        piece += "\n```"
                if block.get("kind") == "table" and start:
                    piece = prefix + piece
                if current_words + len(piece.split()) > self.max_words:
                    flush()
                piece_metadata = metadata
                if block.get("kind") == "table" and oversized:
                    piece_metadata = {
                        **metadata,
                        "cells": [
                            cell
                            for cell in metadata.get("cells", [])
                            if cell["render_end_char"] > begin_char and cell["render_start_char"] < end_char
                        ],
                    }
                current.append(
                    {
                        **piece_metadata,
                        "kind": block.get("kind", "text"),
                        "region": block.get("region", "unknown"),
                        "text": piece,
                        "block_id": self._hash_id(url, hierarchy, index),
                        "start_char": offset + begin_char,
                        "end_char": offset + end_char,
                        "offset_basis": "section_extracted_text",
                        "start_word": word_offset + start,
                        "end_word": word_offset + end,
                    }
                )
                current_words += len(piece.split())
                if end == len(spans):
                    break
                flush()
            offset += len(text) + 2
            word_offset += len(spans)
        flush()
        return chunks

    def chunk_html(self, html: str, url: str) -> List[Dict]:
        soup = self._clean_html(html)
        sections = self._iter_sections(soup, url)

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
