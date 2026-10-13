"""ElevenLabs text-to-speech client."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx

from .config import ElevenLabsConfig

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class TTSError(Exception):
    pass


class ElevenLabs:
    def __init__(self, config: ElevenLabsConfig, client: httpx.Client | None = None):
        self.config = config
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, read=600))

    def synthesize_chunk(
        self, text: str, voice_id: str, language: str, previous_request_ids: list[str]
    ) -> tuple[bytes, str | None]:
        body: dict = {"text": text, "model_id": self.config.model_id}
        if self.config.send_language_code:
            body["language_code"] = language
        if self.config.stitching and previous_request_ids:
            # ElevenLabs accepts at most three previous requests for continuity.
            body["previous_request_ids"] = previous_request_ids[-3:]

        for attempt in range(5):
            response = self.client.post(
                API_URL.format(voice_id=voice_id),
                params={"output_format": self.config.output_format},
                headers={"xi-api-key": self.config.api_key},
                json=body,
            )
            if response.status_code in RETRY_STATUSES and attempt < 4:
                time.sleep(2 ** (attempt + 1))
                continue
            if response.status_code != 200:
                raise TTSError(f"ElevenLabs returned {response.status_code}: {response.text}")
            return response.content, response.headers.get("request-id")
        raise AssertionError("unreachable")

    def synthesize(
        self,
        chunks: Iterable[str],
        language: str,
        out_path: Path,
        on_chunk: Callable[[int], None] | None = None,
    ) -> None:
        """Synthesize all chunks and write them one after another into a single MP3.

        Concatenated MP3 frames of the same format play back as one continuous file, once
        each chunk's own ID3 tag and Xing/Info header (which state that chunk's length) are
        removed.
        """
        voice_id = self.config.voices.get(language) or self.config.voices["en"]
        request_ids: list[str] = []
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        with tmp_path.open("wb") as out:
            for i, chunk in enumerate(chunks):
                audio, request_id = self.synthesize_chunk(chunk, voice_id, language, request_ids)
                out.write(strip_mp3_headers(audio))
                if request_id:
                    request_ids.append(request_id)
                if on_chunk:
                    on_chunk(i)
        tmp_path.replace(out_path)


def mp3_duration_seconds(size_bytes: int, output_format: str) -> int:
    """Estimate the duration of a constant-bitrate MP3 such as ElevenLabs' mp3_44100_128."""
    try:
        kbps = int(output_format.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        kbps = 128
    return round(size_bytes * 8 / (kbps * 1000))


# Bitrates in kbps for MPEG-1 and MPEG-2/2.5 Layer III, indexed by the header's bitrate bits.
_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _layer3_frame_length(header: bytes) -> int | None:
    if len(header) < 4 or header[0] != 0xFF or header[1] & 0xE0 != 0xE0:
        return None
    version = (header[1] >> 3) & 0x3  # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
    layer = (header[1] >> 1) & 0x3  # 1 = Layer III
    bitrate_index = header[2] >> 4
    rate_index = (header[2] >> 2) & 0x3
    if version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
        return None
    bitrate = _BITRATES[1 if version == 3 else 2][bitrate_index] * 1000
    sample_rate = _SAMPLE_RATES[version][rate_index]
    padding = (header[2] >> 1) & 0x1
    coefficient = 144 if version == 3 else 72
    return coefficient * bitrate // sample_rate + padding


def strip_mp3_headers(data: bytes) -> bytes:
    """Remove a leading ID3v2 tag and a Xing/Info/VBRI header frame, keeping only audio."""
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        footer = 10 if data[5] & 0x10 else 0
        data = data[10 + size + footer :]
    frame_length = _layer3_frame_length(data[:4])
    if frame_length:
        first_frame = data[:frame_length]
        if any(tag in first_frame[:64] for tag in (b"Xing", b"Info", b"VBRI")):
            data = data[frame_length:]
    return data
