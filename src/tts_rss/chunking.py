"""Split long text into pieces that fit into a single TTS request."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks of at most max_chars, preferring paragraph, then sentence,
    then word boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # Each piece remembers how it joins the previous one: a paragraph break or a space.
    pieces: list[tuple[str, str]] = []
    for paragraph in paragraphs:
        paragraph = " ".join(paragraph.split())
        if len(paragraph) <= max_chars:
            pieces.append(("\n\n", paragraph))
            continue
        parts = [
            part
            for sentence in _SENTENCE_END.split(paragraph)
            for part in _split_words(sentence, max_chars)
        ]
        pieces.extend(("\n\n" if i == 0 else " ", part) for i, part in enumerate(parts))

    chunks: list[str] = []
    current = ""
    for joiner, piece in pieces:
        sep = joiner if current else ""
        if len(current) + len(sep) + len(piece) <= max_chars:
            current += sep + piece
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _split_words(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    out: list[str] = []
    current = ""
    for word in sentence.split():
        while len(word) > max_chars:
            if current:
                out.append(current)
                current = ""
            out.append(word[:max_chars])
            word = word[max_chars:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out
