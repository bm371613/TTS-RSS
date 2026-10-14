"""Command-line interface."""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from . import chunking, extract, feed, language
from .config import Config, ConfigError, ElevenLabsConfig, config_path, load_config
from .remote import Remote, RemoteError
from .tts import ElevenLabs, TTSError, mp3_duration_seconds

EPISODES_FILE = "episodes.json"
FEED_FILE = "feed.xml"


def slugify(text: str, max_len: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    text = text.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "episode"


def confirm(question: str) -> bool:
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def get_article(args: argparse.Namespace) -> extract.Article:
    if args.source == "-":
        text = sys.stdin.read()
    elif re.match(r"https?://", args.source):
        article = extract.article_from_url(args.source)
        if args.title:
            article.title = args.title
        return article
    else:
        text = Path(args.source).read_text()
    text = text.strip()
    if not text:
        raise extract.ExtractionError("no text given")
    title = args.title or text.splitlines()[0][:80]
    return extract.Article(title=title, text=text, url=args.link)


def spoken_text(article: extract.Article) -> str:
    """Read the title first, so the episode announces what it is, unless the text already
    starts with it, as text taken from a file or stdin does."""
    if article.text.startswith(article.title):
        return article.text
    return f"{article.title}\n\n{article.text}"


def publish(config: Config, remote: Remote, episodes: list[feed.Episode]) -> None:
    remote.write_text(EPISODES_FILE, feed.dump_episodes(episodes))
    remote.write_text(FEED_FILE, feed.render_feed(config.feed, episodes))


def cmd_add(args: argparse.Namespace) -> int:
    article = get_article(args)
    lang = args.lang or language.detect_language(article.text)
    spoken = spoken_text(article)

    if args.dry_run:
        # Use the configured chunk size if there is a config, but do not require one.
        max_chars = (
            load_config().elevenlabs.max_chunk_chars
            if config_path().exists()
            else ElevenLabsConfig.max_chunk_chars
        )
        chunks = chunking.split_text(spoken, max_chars)
        characters = sum(len(c) for c in chunks)
        print(spoken)
        print(
            f"\n--- {characters} characters, {len(chunks)} request(s), language: {lang}",
            file=sys.stderr,
        )
        return 0

    config = load_config()
    chunks = chunking.split_text(spoken, config.elevenlabs.max_chunk_chars)
    characters = sum(len(c) for c in chunks)
    print(f"Title:      {article.title}")
    print(f"Language:   {lang}")
    print(f"Characters: {characters} in {len(chunks)} request(s)")
    if not (args.yes or args.audio or confirm("Generate audio?")):
        print("Aborted.")
        return 1

    # Check the API key and the server before spending credits.
    client = None if args.audio else ElevenLabs(config.elevenlabs)
    remote = Remote(config.server)
    episodes = feed.load_episodes(remote.read_text(EPISODES_FILE))

    now = datetime.now(UTC).replace(microsecond=0)
    episode_id = f"{now:%Y%m%d-%H%M%S}-{slugify(article.title)}"
    # A random suffix keeps audio URLs unguessable even if audio is served without auth.
    audio_file = f"{episode_id}-{secrets.token_hex(8)}.mp3"
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    local_audio = config.cache_dir / audio_file

    if client is None:
        shutil.copyfile(args.audio, local_audio)
    else:
        client.synthesize(
            chunks,
            lang,
            local_audio,
            on_chunk=lambda i: print(f"  synthesized {i + 1}/{len(chunks)}", file=sys.stderr),
        )
        print(f"Audio saved to {local_audio}")

    size = local_audio.stat().st_size
    episodes.append(
        feed.Episode(
            id=episode_id,
            title=article.title,
            audio_file=audio_file,
            size_bytes=size,
            duration_seconds=mp3_duration_seconds(size, config.elevenlabs.output_format),
            published=now.isoformat(),
            language=lang,
            source_url=article.url,
            author=article.author,
            characters=characters,
        )
    )
    remote.upload_file(local_audio, f"audio/{audio_file}")
    publish(config, remote, episodes)
    print(f"Published: {article.title}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    config = load_config()
    remote = Remote(config.server)
    episodes = feed.load_episodes(remote.read_text(EPISODES_FILE))
    publish(config, remote, episodes)
    print(f"Feed rebuilt with {len(episodes)} episode(s).")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config()
    episodes = feed.load_episodes(Remote(config.server).read_text(EPISODES_FILE))
    for e in sorted(episodes, key=lambda e: e.published_at):
        minutes = e.duration_seconds // 60
        print(f"{e.published_at:%Y-%m-%d}  {e.language}  {minutes:3d} min  {e.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts-rss", description="Turn articles into a private podcast feed."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="convert an article and publish it as an episode")
    add.add_argument("source", help="article URL, path to a text file, or - for stdin")
    add.add_argument("--title", help="episode title (default: article title or first line)")
    add.add_argument("--link", help="source URL to show with the episode, for text input")
    add.add_argument("--lang", choices=["en", "pl"], help="override language detection")
    add.add_argument(
        "--dry-run",
        action="store_true",
        help="print the text that would be read and its cost, then stop",
    )
    add.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    add.add_argument(
        "--audio", type=Path, help="publish this existing MP3 instead of calling ElevenLabs"
    )
    add.set_defaults(func=cmd_add)

    rebuild = sub.add_parser("rebuild", help="regenerate feed.xml from the episode list")
    rebuild.set_defaults(func=cmd_rebuild)

    lst = sub.add_parser("list", help="list published episodes")
    lst.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except (ConfigError, extract.ExtractionError, TTSError, RemoteError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
