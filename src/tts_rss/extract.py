"""Get readable article text out of a web page, like a browser's reader view."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import trafilatura

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


class ExtractionError(Exception):
    pass


@dataclass
class Article:
    title: str
    text: str
    url: str | None = None
    author: str | None = None


def fetch_html(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    response.raise_for_status()
    return response.text


def extract_article(html: str, url: str | None = None) -> Article:
    result = trafilatura.extract(
        html,
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
    lines = [line for line in lines if line]
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
