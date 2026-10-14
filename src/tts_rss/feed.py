"""Episode list and podcast RSS feed generation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from .config import FeedConfig

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)

# Characters XML 1.0 cannot represent, e.g. control characters scraped from a web page.
# One of them in a title would make the whole feed unreadable.
_INVALID_XML_CHARS = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


@dataclass
class Episode:
    id: str
    title: str
    audio_file: str
    size_bytes: int
    duration_seconds: int
    published: str  # ISO 8601 with timezone
    language: str
    source_url: str | None = None
    author: str | None = None
    characters: int = 0

    @property
    def published_at(self) -> datetime:
        return datetime.fromisoformat(self.published)


def load_episodes(data: str | None) -> list[Episode]:
    if not data or not data.strip():
        return []
    return [Episode(**item) for item in json.loads(data)["episodes"]]


def dump_episodes(episodes: list[Episode]) -> str:
    return json.dumps({"episodes": [asdict(e) for e in episodes]}, indent=2, ensure_ascii=False)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, {k: _xml_safe(v) for k, v in attrs.items()})
    if text is not None:
        el.text = _xml_safe(text)
    return el


def _xml_safe(text: str) -> str:
    return _INVALID_XML_CHARS.sub("", text)


def _duration(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}"


def render_feed(feed: FeedConfig, episodes: list[Episode]) -> str:
    episodes = sorted(episodes, key=lambda e: e.published_at, reverse=True)
    base_url = feed.base_url.rstrip("/")

    rss = ET.Element("rss", {"version": "2.0"})
    channel = _sub(rss, "channel")
    _sub(channel, "title", feed.title)
    _sub(channel, "link", base_url + "/")
    _sub(channel, "description", feed.description)
    _sub(
        channel,
        f"{{{ATOM}}}link",
        href=base_url + "/feed.xml",
        rel="self",
        type="application/rss+xml",
    )
    _sub(channel, f"{{{ITUNES}}}author", feed.author)
    _sub(channel, f"{{{ITUNES}}}explicit", "false")
    # Keep this private feed out of podcast directories.
    _sub(channel, f"{{{ITUNES}}}block", "Yes")
    if feed.image_url:
        _sub(channel, f"{{{ITUNES}}}image", href=feed.image_url)
        image = _sub(channel, "image")
        _sub(image, "url", feed.image_url)
        _sub(image, "title", feed.title)
        _sub(image, "link", base_url + "/")
    if episodes:
        _sub(channel, "lastBuildDate", format_datetime(episodes[0].published_at))

    for episode in episodes:
        item = _sub(channel, "item")
        _sub(item, "title", episode.title)
        description = episode.source_url or episode.title
        if episode.author:
            description = f"{episode.author} — {description}"
        _sub(item, "description", description)
        if episode.source_url:
            _sub(item, "link", episode.source_url)
        _sub(item, "guid", episode.id, isPermaLink="false")
        _sub(item, "pubDate", format_datetime(episode.published_at))
        _sub(
            item,
            "enclosure",
            url=f"{feed.audio_base_url}/{episode.audio_file}",
            length=str(episode.size_bytes),
            type="audio/mpeg",
        )
        _sub(item, f"{{{ITUNES}}}duration", _duration(episode.duration_seconds))
        _sub(item, f"{{{ITUNES}}}episodeType", "full")

    ET.indent(rss)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"
