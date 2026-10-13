"""Configuration loaded from a TOML file, with the API key optionally from the environment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/.config/tts-rss/config.toml")


class ConfigError(Exception):
    pass


@dataclass
class ElevenLabsConfig:
    api_key: str
    voices: dict[str, str]
    model_id: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"
    max_chunk_chars: int = 4500
    send_language_code: bool = False
    stitching: bool = True


@dataclass
class ServerConfig:
    host: str
    path: str


@dataclass
class FeedConfig:
    base_url: str
    title: str = "TTS RSS"
    description: str = "Articles read aloud."
    author: str = "TTS RSS"
    image_url: str | None = None
    media_base_url: str | None = None

    @property
    def audio_base_url(self) -> str:
        return (self.media_base_url or self.base_url).rstrip("/") + "/audio"


@dataclass
class Config:
    elevenlabs: ElevenLabsConfig
    server: ServerConfig
    feed: FeedConfig
    cache_dir: Path = field(default_factory=lambda: Path("~/.cache/tts-rss").expanduser())


def config_path() -> Path:
    return Path(os.environ.get("TTS_RSS_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()


def _require(section: dict[str, Any], key: str, name: str) -> Any:
    try:
        return section[key]
    except KeyError:
        raise ConfigError(f"missing required setting [{name}] {key}") from None


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(f"config file not found: {path} (see config.example.toml)")
    with path.open("rb") as f:
        data = tomllib.load(f)

    el = data.get("elevenlabs", {})
    api_key = os.environ.get("ELEVENLABS_API_KEY") or el.get("api_key") or ""
    voices = _require(el, "voices", "elevenlabs")
    if "en" not in voices:
        raise ConfigError("[elevenlabs.voices] must define at least an 'en' voice")
    elevenlabs = ElevenLabsConfig(
        api_key=api_key,
        voices=dict(voices),
        **{
            k: el[k]
            for k in (
                "model_id",
                "output_format",
                "max_chunk_chars",
                "send_language_code",
                "stitching",
            )
            if k in el
        },
    )

    srv = data.get("server", {})
    server = ServerConfig(
        host=_require(srv, "host", "server"), path=_require(srv, "path", "server")
    )

    fd = data.get("feed", {})
    feed = FeedConfig(
        base_url=_require(fd, "base_url", "feed"),
        **{
            k: fd[k]
            for k in (
                "title",
                "description",
                "author",
                "image_url",
                "media_base_url",
            )
            if k in fd
        },
    )

    config = Config(elevenlabs=elevenlabs, server=server, feed=feed)
    if "cache_dir" in data:
        config.cache_dir = Path(data["cache_dir"]).expanduser()
    return config
