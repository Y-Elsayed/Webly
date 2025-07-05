from bs4 import BeautifulSoup, Tag
from typing import List, Dict
import uuid
import re

class HeaderSlidingChunker:
    def __init__(self, max_words: int = 350, overlap: int = 50):
        """
        Args:
            max_words: Max number of words in a chunk before splitting.
            overlap: Number of words to include from previous chunk (sliding window).
        """
        self.max_words = max_words
        self.overlap = overlap

    def _split_by_heading(self, text: str) -> List[str]:
        """
        Splits text by level 1 headings (# Header).
        """
        sections = re.split(r"(?=^#\s)", text, flags=re.MULTILINE)
        return [section.strip() for section in sections if section.strip()]

    def _sliding_window_chunks(self, text: str) -> List[str]:
        """
        Splits long text into overlapping chunks using a sliding window.
        """
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk_words = words[i:i + self.max_words]
            chunks.append(" ".join(chunk_words))
            i += self.max_words - self.overlap  # Move window
        return chunks

    def chunk_text(self, text: str) -> List[str]:
        sections = self._split_by_heading(text)
        all_chunks = []
        for section in sections:
            section_chunks = self._sliding_window_chunks(section)
            all_chunks.extend(section_chunks)
        return all_chunks 
