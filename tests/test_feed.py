from xml.etree import ElementTree as ET

from tts_rss.config import FeedConfig
from tts_rss.feed import ITUNES, Episode, dump_episodes, load_episodes, render_feed


def make_episode(n: int, **kwargs) -> Episode:
    defaults = dict(
        id=f"ep{n}",
        title=f"Episode {n} & <friends>",
        audio_file=f"ep{n}.mp3",
        size_bytes=1_920_000,
        duration_seconds=120,
        published=f"2026-10-1{n}T10:00:00+00:00",
        language="en",
        source_url=f"https://example.com/{n}",
    )
    return Episode(**{**defaults, **kwargs})


def test_episodes_round_trip():
    episodes = [make_episode(1), make_episode(2, language="pl", author="Ktoś")]
    assert load_episodes(dump_episodes(episodes)) == episodes
    assert load_episodes(None) == []


def test_render_feed():
    config = FeedConfig(base_url="https://example.org/tts/", title="My feed")
    xml = render_feed(config, [make_episode(1), make_episode(2)])
    root = ET.fromstring(xml)
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "My feed"
    items = channel.findall("item")
    # Newest first.
    assert [i.findtext("guid") for i in items] == ["ep2", "ep1"]
    assert items[0].findtext("title") == "Episode 2 & <friends>"
    enclosure = items[0].find("enclosure")
    assert enclosure is not None
    assert enclosure.get("url") == "https://example.org/tts/audio/ep2.mp3"
    assert enclosure.get("length") == "1920000"
    assert enclosure.get("type") == "audio/mpeg"
    assert items[0].findtext(f"{{{ITUNES}}}duration") == "0:02:00"
    assert items[0].findtext("pubDate") == "Mon, 12 Oct 2026 10:00:00 +0000"


def test_media_base_url_overrides_audio_location():
    config = FeedConfig(
        base_url="https://example.org/tts", media_base_url="https://u:p@example.org/tts"
    )
    root = ET.fromstring(render_feed(config, [make_episode(1)]))
    enclosure = root.find("channel/item/enclosure")
    assert enclosure is not None
    url = enclosure.get("url")
    assert url == "https://u:p@example.org/tts/audio/ep1.mp3"
