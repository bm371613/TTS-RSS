import json
import shutil
import subprocess
import time

import httpx
import pytest

from tts_rss.config import ElevenLabsConfig
from tts_rss.tts import ElevenLabs, TTSError, mp3_duration_seconds, strip_mp3_headers


def test_synthesize_concatenates_chunks_and_stitches(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request, body))
        n = len(requests)
        return httpx.Response(200, content=f"audio{n}".encode(), headers={"request-id": f"r{n}"})

    config = ElevenLabsConfig(api_key="key", voices={"en": "EN_VOICE", "pl": "PL_VOICE"})
    client = ElevenLabs(config, client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = tmp_path / "out.mp3"
    client.synthesize(["one", "two", "three", "four", "five"], "pl", out)

    assert out.read_bytes() == b"audio1audio2audio3audio4audio5"
    request, body = requests[0]
    assert request.url.path == "/v1/text-to-speech/PL_VOICE"
    assert request.url.params["output_format"] == "mp3_44100_128"
    assert request.headers["xi-api-key"] == "key"
    assert body == {"text": "one", "model_id": "eleven_multilingual_v2"}
    assert requests[1][1]["previous_request_ids"] == ["r1"]
    assert requests[4][1]["previous_request_ids"] == ["r2", "r3", "r4"]


def test_language_code_is_optional(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=b"x")

    config = ElevenLabsConfig(api_key="k", voices={"en": "V"}, send_language_code=True)
    client = ElevenLabs(config, client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.synthesize(["hi"], "en", tmp_path / "o.mp3")
    assert bodies[0]["language_code"] == "en"


def test_duration_estimate():
    assert mp3_duration_seconds(16_000 * 60, "mp3_44100_128") == 60
    assert mp3_duration_seconds(24_000 * 10, "mp3_44100_192") == 10


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_strip_mp3_headers_on_real_files(tmp_path):
    chunks = []
    for i in range(3):
        path = tmp_path / f"c{i}.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=duration=4",
                "-ar",
                "44100",
                "-b:a",
                "128k",
                str(path),
            ],
            check=True,
        )
        chunks.append(path.read_bytes())
    stripped = [strip_mp3_headers(c) for c in chunks]
    for original, s in zip(chunks, stripped, strict=True):
        assert original.startswith(b"ID3")
        assert s[0] == 0xFF and b"Info" not in s[:200]
        assert len(s) < len(original)

    joined = tmp_path / "joined.mp3"
    joined.write_bytes(b"".join(stripped))
    duration = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(joined),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert abs(float(duration) - 12) < 0.2
    assert abs(mp3_duration_seconds(joined.stat().st_size, "mp3_44100_128") - 12) <= 1


def test_strip_mp3_headers_leaves_plain_audio_alone():
    frame = bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\0" * 413
    assert strip_mp3_headers(frame * 3) == frame * 3


def test_network_errors_are_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"x")

    config = ElevenLabsConfig(api_key="k", voices={"en": "V"})
    client = ElevenLabs(config, client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.synthesize(["hi"], "en", tmp_path / "o.mp3")
    assert len(attempts) == 3
    assert (tmp_path / "o.mp3").read_bytes() == b"x"


def test_persistent_network_error_is_a_tts_error(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)

    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    config = ElevenLabsConfig(api_key="k", voices={"en": "V"})
    client = ElevenLabs(config, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TTSError, match="could not reach ElevenLabs"):
        client.synthesize(["hi"], "en", tmp_path / "o.mp3")
