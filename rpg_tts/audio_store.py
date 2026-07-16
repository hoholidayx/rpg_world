"""Validated content-addressed MP3 storage inside a workspace."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rpg_data.settings import resolve_workspace_relative_path
from rpg_tts.errors import TTSInvalidAudioError


@dataclass(frozen=True)
class StoredAudio:
    sha256: str
    byte_size: int
    relative_path: str
    absolute_path: str


def inspect_mp3(data: bytes) -> tuple[str, int]:
    payload = bytes(data)
    has_id3 = payload.startswith(b"ID3")
    has_frame = len(payload) >= 2 and payload[0] == 0xFF and (payload[1] & 0xE0) == 0xE0
    if not payload or not (has_id3 or has_frame):
        raise TTSInvalidAudioError("Speech provider did not return a valid MP3 payload")
    return hashlib.sha256(payload).hexdigest(), len(payload)


def inspect_mp3_file(path: Path) -> tuple[str, int]:
    return inspect_mp3(path.read_bytes())


class WorkspaceAudioStore:
    def audio_directory(self, workspace_root: str) -> Path:
        return resolve_workspace_relative_path(Path(workspace_root), "assets/audio")

    def put(self, workspace_root: str, data: bytes) -> StoredAudio:
        sha256, byte_size = inspect_mp3(data)
        relative_path = f"assets/audio/{sha256}.mp3"
        target = resolve_workspace_relative_path(Path(workspace_root), relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing_sha256, existing_size = inspect_mp3_file(target)
            if existing_sha256 != sha256 or existing_size != byte_size:
                raise TTSInvalidAudioError(
                    f"Existing content-addressed audio is corrupt: {relative_path}"
                )
        else:
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{sha256}.",
                    suffix=".tmp",
                    dir=target.parent,
                    delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            finally:
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()
        return StoredAudio(
            sha256=sha256,
            byte_size=byte_size,
            relative_path=relative_path,
            absolute_path=str(target),
        )

    def resolve(self, workspace_root: str, *, sha256: str, relative_path: str) -> Path:
        expected = f"assets/audio/{sha256}.mp3"
        if relative_path != expected:
            raise ValueError(f"invalid TTS blob path: {relative_path}")
        return resolve_workspace_relative_path(Path(workspace_root), relative_path)
