import hashlib
import re
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup, Tag


class SlidingTextChunker:
    def __init__(self, max_words: int = 350, overlap: int = 50):
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

        # Maintain current heading path (H1..Hn)
        path: List[str] = []
        for i, h in enumerate(headings):
            curr_lvl = level_of(h)
            # update path to this level
            text = self._text(h)
            if curr_lvl - 1 <= len(path):
                path = path[: curr_lvl - 1]
            # ensure parents exist up to level-1
            while len(path) < curr_lvl - 1:
                path.append("")  # missing parent heading
            path = path + [text]

            # Collect blocks until next heading of <= curr_lvl
            blocks: List[Dict] = []
            for sib in h.next_siblings:
                if isinstance(sib, Tag):
                    m = self._heading_re.match(sib.name or "")
                    if m and int(m.group(1)) <= curr_lvl:
                        break  # next sibling heading closes this section
                    if sib.name in ["p", "li", "pre", "code", "blockquote", "td", "table"]:
                        txt, anchors = self._block_text_and_anchors(sib)
                        if txt and len(txt.split()) > 3:
                            blocks.append({"text": txt, "anchors": anchors})
            if blocks:
                # copy the path for immutability per section
                sections.append({"hierarchy": path[:], "blocks": blocks})

        return sections

    # ---------- Chunking over blocks with sliding window ----------
    def _chunk_section_blocks(self, url: str, hierarchy: List[str], blocks: List[Dict]) -> List[Dict]:
        """
        Merge consecutive blocks into chunks up to max_words with overlap, carrying anchors that fall inside.
        """
        chunks: List[Dict] = []
        window_words: List[str] = []
        window_anchors: List[Dict] = []
        section_chunks_idx = 0

        # To support overlap, keep a small trailing buffer of words and anchors
        trailing_words: List[str] = []
        trailing_anchors: List[Dict] = []

        def flush_chunk():
            nonlocal window_words, window_anchors, section_chunks_idx, trailing_words, trailing_anchors
            if not window_words:
                return
            text = " ".join(window_words).strip()
            tokens = len(window_words)
            chunk_id = self._hash_id(url, hierarchy, section_chunks_idx)
            chunks.append(
                {
                    "id": chunk_id,
                    "url": url,
                    "text": text,
                    "tokens": tokens,
                    "hierarchy": hierarchy[:],
                    "outgoing_links": window_anchors[:],  # anchors inside this chunk
                }
            )
            section_chunks_idx += 1
            # prepare overlap from end of window
            if self.overlap > 0 and len(window_words) > self.overlap:
                trailing_words = window_words[-self.overlap :]
                # we cannot precisely trim anchors by word offset here; keep last window anchors
                trailing_anchors = window_anchors[-max(1, min(len(window_anchors), 3)) :]
            else:
                trailing_words, trailing_anchors = [], []
            window_words, window_anchors = [], []

        for blk in blocks:
            bw = blk["text"].split()
            ba = blk.get("anchors", [])
            # if adding this block would exceed the window, flush first
            if window_words and len(window_words) + len(bw) > self.max_words:
                flush_chunk()
                # start next window with overlap seed
                window_words = trailing_words[:]
                window_anchors = trailing_anchors[:]

            window_words.extend(bw)
            window_anchors.extend(ba)

            # flush if we hit/exceeded max_words
            while len(window_words) >= self.max_words:
                flush_chunk()
                # seed with overlap for next chunk
                window_words = trailing_words[:]
                window_anchors = trailing_anchors[:]

        # leftover
        if window_words:
            flush_chunk()

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
                tokens = len(full_text.split())
                all_chunks.append(
                    {
                        "id": self._hash_id(url, [], 0),
                        "url": url,
                        "text": full_text,
                        "tokens": tokens,
                        "hierarchy": [],
                        "outgoing_links": [],
                    }
                )

        return all_chunks


DefaultChunker = SlidingTextChunker
