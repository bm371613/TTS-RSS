"""Read and write files on the server over SSH, using the system ssh client and ~/.ssh/config."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path, PurePosixPath

from .config import ServerConfig


class RemoteError(Exception):
    pass


class Remote:
    def __init__(self, config: ServerConfig):
        self.host = config.host
        self.root = PurePosixPath(config.path)

    def _ssh(self, command: str, stdin=None, input: bytes | None = None) -> bytes:
        result = subprocess.run(
            ["ssh", self.host, command], stdin=stdin, input=input, capture_output=True
        )
        if result.returncode != 0:
            raise RemoteError(
                f"ssh {self.host} {command!r} failed: {result.stderr.decode().strip()}"
            )
        return result.stdout

    def read_text(self, relative: str) -> str | None:
        """Return the remote file's contents, or None if it does not exist."""
        path = shlex.quote(str(self.root / relative))
        if self._ssh(f"[ -f {path} ] && echo yes || echo no").strip() == b"no":
            return None
        return self._ssh(f"cat {path}").decode()

    def write_text(self, relative: str, content: str) -> None:
        self._put(relative, lambda tmp: self._ssh(f"cat > {tmp}", input=content.encode()))

    def upload_file(self, local: Path, relative: str) -> None:
        with local.open("rb") as f:
            self._put(relative, lambda tmp: self._ssh(f"cat > {tmp}", stdin=f))

    def _put(self, relative: str, write_tmp) -> None:
        """Write to a temporary name, then rename, so readers never see a partial file."""
        target = self.root / relative
        tmp = target.with_name(f".{target.name}.tmp")
        self._ssh(f"mkdir -p {shlex.quote(str(target.parent))}")
        write_tmp(shlex.quote(str(tmp)))
        self._ssh(
            f"chmod 644 {shlex.quote(str(tmp))} && "
            f"mv -f {shlex.quote(str(tmp))} {shlex.quote(str(target))}"
        )
