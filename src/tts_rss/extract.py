"""Get readable article text out of a web page, like a browser's reader view."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx
import lxml.etree
import lxml.html
import trafilatura

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


# Pull quotes are often <aside> elements, which trafilatura drops as boilerplate. Some sites
# repeat a sentence from the body in them, others put text there that appears nowhere else.
_PULL_QUOTE_CLASS = re.compile(r"\bpull[-_]?quote\b", re.IGNORECASE)


class ExtractionError(Exception):
    pass


@dataclass
class Article:
    title: str
    text: str
    url: str | None = None
    author: str | None = None


def fetch_html(url: str) -> str:
    try:
        response = httpx.get(
            url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ExtractionError(f"could not fetch article: {e}") from e
    return response.text


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _keep_pull_quotes(tree: lxml.html.HtmlElement) -> list[str]:
    """Turn pull quotes into blockquotes, which trafilatura keeps; return their texts."""
    quotes = []
    for el in tree.iter():
        if not isinstance(el.tag, str) or not _PULL_QUOTE_CLASS.search(el.get("class", "")):
            continue
        if el.getparent() is not None and _PULL_QUOTE_CLASS.search(el.getparent().get("class", "")):
            continue  # Inside a pull quote already handled, e.g. <p class=pullquote__text>.
        el.tag = "blockquote"
        text = _normalize(el.text_content())
        if text:
            quotes.append(text)
    return quotes


def _drop_repeated(lines: list[str], quotes: list[str]) -> list[str]:
    """Drop pull quotes that only repeat text from the rest of the article."""
    kept = list(lines)
    for quote in quotes:
        rest = [line for line in kept if _normalize(line) != quote]
        if len(rest) < len(kept) and any(quote in _normalize(line) for line in rest):
            kept = rest
    return kept


def extract_article(html: str, url: str | None = None) -> Article:
    try:
        # The text is already decoded; parse it as UTF-8 whatever encoding the page declares.
        tree = lxml.html.fromstring(
            html.encode("utf-8"), parser=lxml.html.HTMLParser(encoding="utf-8")
        )
    except (ValueError, lxml.etree.ParserError) as e:
        raise ExtractionError(f"could not parse the page: {e}") from e
    quotes = _keep_pull_quotes(tree)
    result = trafilatura.extract(
        tree,
        url=url,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        include_images=False,
        favor_precision=True,
    )
    if not result:
        raise ExtractionError("could not find article text on the page")
    data = json.loads(result)
    # trafilatura puts one paragraph per line; make paragraph breaks explicit.
    lines = [line.strip() for line in data.get("text", "").splitlines()]
    lines = _drop_repeated([line for line in lines if line], quotes)
    title = (data.get("title") or url or "Untitled").strip()
    # The headline is often part of the text; the title is read out separately.
    if lines and lines[0].casefold() == title.casefold():
        lines = lines[1:]
    text = "\n\n".join(lines)
    if not text:
        raise ExtractionError("could not find article text on the page")
    return Article(
        title=title,
        text=text,
        url=url,
        author=data.get("author") or None,
    )


def article_from_url(url: str) -> Article:
    return extract_article(fetch_html(url), url=url)
