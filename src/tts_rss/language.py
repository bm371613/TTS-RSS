"""Tell Polish from English. Those are the only two languages we expect."""

from __future__ import annotations

import re

POLISH_STOPWORDS = frozenset(
    "i w z na nie się że to jest do jak o co ale po od za tak jego już przez dla czy też"
    " są być może ten tylko jej lub oraz który która które także tym przy bardzo".split()
)
ENGLISH_STOPWORDS = frozenset(
    "the and of to a in is that it for on with as was are be this by at from or an not"
    " but have has which you they their we were been can will would".split()
)
POLISH_LETTERS = frozenset("ąćęłńóśźż")

_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str) -> str:
    """Return "pl" if the text is (almost) all Polish, otherwise "en"."""
    words = [w.lower() for w in _WORD.findall(text)]
    pl_hits = sum(w in POLISH_STOPWORDS for w in words)
    en_hits = sum(w in ENGLISH_STOPWORDS for w in words)
    if pl_hits + en_hits >= 5:
        return "pl" if pl_hits > en_hits else "en"
    # Too few function words to judge; fall back to Polish diacritics.
    letters = [c for c in text.lower() if c.isalpha()]
    if letters and sum(c in POLISH_LETTERS for c in letters) / len(letters) > 0.02:
        return "pl"
    return "en"
