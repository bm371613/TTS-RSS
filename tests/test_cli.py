import json
import os
from xml.etree import ElementTree as ET

import httpx
import pytest

from tts_rss import cli, tts


@pytest.fixture
def env(tmp_path, monkeypatch):
    # A fake `ssh` that runs the remote command locally, so the real Remote code is exercised.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text('#!/bin/sh\nshift\nexec sh -c "$1"\n')
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    server = tmp_path / "server"
    config = tmp_path / "config.toml"
    config.write_text(f"""
cache_dir = "{tmp_path / "cache"}"

[elevenlabs]
api_key = "secret"
voices = {{ en = "EN", pl = "PL" }}

[server]
host = "myserver"
path = "{server}"

[feed]
base_url = "https://example.org/tts"
title = "Test feed"
""")
    monkeypatch.setenv("TTS_RSS_CONFIG", str(config))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, content=b"\xff\xfb" * 8000)

    class FakeElevenLabs(tts.ElevenLabs):
        def __init__(self, config):
            super().__init__(config, client=httpx.Client(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(cli, "ElevenLabs", FakeElevenLabs)
    return server, calls


def test_add_text_publishes_episode(env, tmp_path):
    server, calls = env
    article = tmp_path / "article.txt"
    article.write_text("Wstęp\n\nTo jest tekst, który nie jest długi, ale się nada.")

    assert cli.main(["add", str(article), "--title", "Mój artykuł", "--yes"]) == 0

    episodes = json.loads((server / "episodes.json").read_text())["episodes"]
    first = episodes[0]
    assert first["title"] == "Mój artykuł"
    assert first["language"] == "pl"
    assert first["audio_file"].startswith(first["id"] + "-")
    assert first["id"].endswith("-moj-artykul")
    audio = server / "audio" / first["audio_file"]
    assert audio.stat().st_size == first["size_bytes"] == 16000
    assert calls[0]["text"].startswith("Mój artykuł\n\nWstęp")

    feed = ET.fromstring((server / "feed.xml").read_text())
    assert feed.findtext("channel/item/title") == "Mój artykuł"
    enclosure = feed.find("channel/item/enclosure")
    assert enclosure is not None
    url = enclosure.get("url")
    assert url == f"https://example.org/tts/audio/{first['audio_file']}"
    assert not list(server.rglob(".*.tmp"))


def test_second_episode_is_appended(env, tmp_path, monkeypatch):
    server, _ = env
    for i in range(2):
        f = tmp_path / f"a{i}.txt"
        f.write_text(f"Article {i}\n\nThis is the text of the article and it is in English.")
        assert cli.main(["add", str(f), "--yes"]) == 0
    episodes = json.loads((server / "episodes.json").read_text())["episodes"]
    assert [e["title"] for e in episodes] == ["Article 0", "Article 1"]
    assert all(e["language"] == "en" for e in episodes)
    assert cli.main(["rebuild"]) == 0
    assert len(ET.fromstring((server / "feed.xml").read_text()).findall("channel/item")) == 2


def test_dry_run_needs_no_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TTS_RSS_CONFIG", str(tmp_path / "missing.toml"))
    f = tmp_path / "a.txt"
    f.write_text("Hello\n\nThe body of the text.")
    assert cli.main(["add", str(f), "--dry-run"]) == 0
    out = capsys.readouterr()
    assert "The body of the text." in out.out
    assert "characters" in out.err


def test_declining_confirmation_spends_nothing(env, tmp_path, monkeypatch):
    server, calls = env
    monkeypatch.setattr("builtins.input", lambda _: "n")
    f = tmp_path / "a.txt"
    f.write_text("Hello\n\nThe body.")
    assert cli.main(["add", str(f)]) == 1
    assert calls == []
    assert not server.exists()


def test_slugify():
    assert cli.slugify("Zażółć gęślą jaźń — Łódź!") == "zazolc-gesla-jazn-lodz"
    assert cli.slugify("???") == "episode"
