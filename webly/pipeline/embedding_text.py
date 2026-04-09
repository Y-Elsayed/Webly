from __future__ import annotations

import re
from typing import Any


def max_input_tokens(embedder: Any) -> int:
    for attr in ("max_input_tokens", "max_tokens", "context_size", "max_seq_len"):
        value = getattr(embedder, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    return 8192


def count_tokens(embedder: Any, text: str, logger=None) -> int:
    if hasattr(embedder, "count_tokens"):
        try:
            return int(embedder.count_tokens(text))
        except Exception as exc:
            if logger is not None:
                logger.debug(f"embedder.count_tokens failed, using char-count heuristic: {exc}")
    return max(1, len(text) // 4)


def hard_char_splits(text: str, max_tokens: int) -> list[str]:
    char_budget = max(800, max_tokens * 4)
    out: list[str] = []
    start = 0
    total = len(text)
    while start < total:
        out.append(text[start : min(total, start + char_budget)])
        start += char_budget
    return out


def chunk_text_for_embedding(embedder: Any, text: str, logger=None, safety_ratio: float = 0.9) -> list[str]:
    max_tok = int(max_input_tokens(embedder) * getattr(embedder, "safety_ratio", safety_ratio))
    if count_tokens(embedder, text, logger) <= max_tok:
        return [text]

    paras = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            joined = "\n\n".join(current).strip()
            if joined:
                chunks.append(joined)
        current = []
        current_tokens = 0

    for paragraph in paras:
        paragraph_tokens = count_tokens(embedder, paragraph, logger)
        if paragraph_tokens > max_tok:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            for sentence in sentences:
                sentence_tokens = count_tokens(embedder, sentence, logger)
                if sentence_tokens > max_tok:
                    for piece in hard_char_splits(sentence, max_tok):
                        piece_tokens = count_tokens(embedder, piece, logger)
                        if piece_tokens > max_tok:
                            chunks.append(piece)
                            continue
                        if current_tokens + piece_tokens > max_tok:
                            flush()
                        current.append(piece)
                        current_tokens += piece_tokens
                    continue
                if current_tokens + sentence_tokens > max_tok:
                    flush()
                current.append(sentence)
                current_tokens += sentence_tokens
            flush()
            continue

        if current_tokens + paragraph_tokens > max_tok:
            flush()
        current.append(paragraph)
        current_tokens += paragraph_tokens

    flush()
    return [chunk for chunk in chunks if chunk]
