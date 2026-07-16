"""TTS application facade independent from Agent and HTTP frameworks."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from llm_client.keys import TTS_REPLY_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMSpeechProfile
from rpg_data import models
from rpg_data.services.tts import TTSCompletedPart, TTSDataService
from rpg_tts.audio_store import (
    StoredAudio,
    WorkspaceAudioStore,
    inspect_mp3,
    inspect_mp3_file,
)
from rpg_tts.errors import TTSError, TTSSourceChangedError
from rpg_tts.settings import settings
from rpg_tts.text import normalize_spoken_text, split_spoken_text


class TTSFacade:
    def __init__(
        self,
        *,
        data: TTSDataService,
        audio_store: WorkspaceAudioStore | None = None,
        llm_manager: LLMClientManager | None = None,
    ) -> None:
        self._data = data
        self._audio_store = audio_store or WorkspaceAudioStore()
        self._llm = llm_manager or LLMClientManager.get()
        self._storage_lock = asyncio.Lock()

    async def create_job(self, session_id: str, message_id: int) -> models.TTSJob:
        source = self._data.get_message_source(session_id, message_id)
        spoken = normalize_spoken_text(source.content)
        if not spoken:
            raise ValueError("TTS source message has no speakable text")
        profile = await self._llm.client.get_speech_profile(self.biz_key)
        _validate_speech_profile(self.biz_key, profile)
        return self._data.create_or_get_job(
            session_id=session_id,
            message_id=message_id,
            source_fingerprint=_fingerprint(source.content),
            config_fingerprint=profile.config_fingerprint,
            normalization_revision=self.normalization_revision,
        )

    async def execute_job(self, job_id: str) -> models.TTSJob | None:
        job = self._data.get_job_for_worker(job_id)
        if job is None:
            return None
        if job.status != models.TTS_JOB_STATUS_RUNNING:
            return job
        audio_payloads: list[bytes] = []
        try:
            source = self._data.get_message_source(job.session_id, job.message_id)
            if _fingerprint(source.content) != job.source_fingerprint:
                raise TTSSourceChangedError("TTS source message changed before generation")
            if job.normalization_revision != self.normalization_revision:
                raise TTSSourceChangedError(
                    "TTS text normalization configuration changed before generation"
                )
            profile = await self._llm.client.get_speech_profile(self.biz_key)
            _validate_speech_profile(self.biz_key, profile)
            if profile.config_fingerprint != job.config_fingerprint:
                raise TTSSourceChangedError(
                    "TTS speech configuration changed before generation"
                )
            spoken = normalize_spoken_text(source.content)
            parts = split_spoken_text(spoken, settings.synthesis.max_chars_per_part)
            if not parts:
                raise ValueError("TTS source message has no speakable text")
            for part in parts:
                audio = await self._llm.client.speech(
                    biz_key=self.biz_key,
                    provider_key=profile.provider_key,
                    text=part,
                )
                if audio.config_fingerprint != job.config_fingerprint:
                    raise TTSSourceChangedError(
                        "TTS speech configuration changed during generation"
                    )
                inspect_mp3(audio.content)
                audio_payloads.append(bytes(audio.content))
            async with self._storage_lock:
                stored_parts: list[StoredAudio] = []
                for audio_payload in audio_payloads:
                    stored_parts.append(
                        await asyncio.to_thread(
                            self._audio_store.put,
                            source.workspace_root,
                            audio_payload,
                        )
                    )
                current = self._data.get_message_source(job.session_id, job.message_id)
                if _fingerprint(current.content) != job.source_fingerprint:
                    raise TTSSourceChangedError("TTS source message changed before publish")
                return self._data.complete_job(
                    job.id,
                    tuple(
                        TTSCompletedPart(
                            sha256=part.sha256,
                            byte_size=part.byte_size,
                            relative_path=part.relative_path,
                        )
                        for part in stored_parts
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_code = (
                exc.error_code
                if isinstance(exc, TTSError)
                else "TTS_GENERATION_FAILED"
            )
            return self._data.mark_failed(
                job.id,
                error_code=error_code,
                error_message=str(exc),
            )

    async def retry_job(self, session_id: str, job_id: str) -> models.TTSJob | None:
        job = self._data.get_job(session_id, job_id)
        if job is None:
            return None
        if job.status == models.TTS_JOB_STATUS_SUCCEEDED:
            cached_parts = self._data.list_parts(session_id, job_id)
            if not cached_parts and job.cache_entry_id:
                self._data.invalidate_cache(job.cache_entry_id)
                job = self._data.get_job(session_id, job_id)
                if job is None:
                    return None
            for _part, blob in cached_parts:
                try:
                    path = self._audio_store.resolve(
                        self._data.get_workspace_root(blob.workspace_id),
                        sha256=blob.sha256,
                        relative_path=blob.relative_path,
                    )
                    digest, byte_size = await asyncio.to_thread(inspect_mp3_file, path)
                    valid = digest == blob.sha256 and byte_size == blob.byte_size
                except Exception:
                    valid = False
                    path = None
                if valid:
                    continue
                self._data.invalidate_blob(blob.id)
                if path is not None and path.is_file():
                    await asyncio.to_thread(path.unlink)
                job = self._data.get_job(session_id, job_id)
                if job is None:
                    return None
                break
        source = self._data.get_message_source(session_id, job.message_id)
        profile = await self._llm.client.get_speech_profile(self.biz_key)
        _validate_speech_profile(self.biz_key, profile)
        if (
            _fingerprint(source.content) != job.source_fingerprint
            or profile.config_fingerprint != job.config_fingerprint
            or job.normalization_revision != self.normalization_revision
        ):
            return await self.create_job(session_id, job.message_id)
        return self._data.retry_job(session_id, job_id)

    def resolve_audio_part(self, session_id: str, job_id: str, part_index: int) -> Path:
        parts = self._data.list_parts(session_id, job_id)
        matched = next(
            (item for item in parts if item[0].part_index == part_index),
            None,
        )
        if matched is None:
            raise FileNotFoundError(f"TTS audio part not found: {part_index}")
        _part, blob = matched
        job = self._data.get_job(session_id, job_id)
        if job is None:
            raise FileNotFoundError(f"TTS job not found: {job_id}")
        source = self._data.get_message_source(session_id, job.message_id)
        path = self._audio_store.resolve(
            source.workspace_root,
            sha256=blob.sha256,
            relative_path=blob.relative_path,
        )
        if not path.is_file():
            self._data.invalidate_blob(blob.id)
        return path

    async def reconcile_workspace(self, workspace_id: str) -> "TTSReconcileResult":
        async with self._storage_lock:
            return await self._reconcile_workspace(workspace_id)

    async def _reconcile_workspace(self, workspace_id: str) -> "TTSReconcileResult":
        workspace_root = self._data.get_workspace_root(workspace_id)
        blobs = self._data.list_blobs(workspace_id)
        removed_blobs = 0
        for blob in blobs:
            path = self._audio_store.resolve(
                workspace_root,
                sha256=blob.sha256,
                relative_path=blob.relative_path,
            )
            valid = False
            if path.is_file():
                try:
                    digest, byte_size = await asyncio.to_thread(inspect_mp3_file, path)
                    valid = digest == blob.sha256 and byte_size == blob.byte_size
                except Exception:
                    valid = False
            if valid and self._data.blob_is_referenced(blob.id):
                continue
            self._data.invalidate_blob(blob.id)
            if path.exists():
                await asyncio.to_thread(path.unlink)
            removed_blobs += 1

        # Invalidating one cache entry can orphan other blobs that appeared
        # earlier in the first pass, so sweep references once more.
        for blob in self._data.list_blobs(workspace_id):
            if self._data.blob_is_referenced(blob.id):
                continue
            path = self._audio_store.resolve(
                workspace_root,
                sha256=blob.sha256,
                relative_path=blob.relative_path,
            )
            self._data.invalidate_blob(blob.id)
            if path.exists():
                await asyncio.to_thread(path.unlink)
            removed_blobs += 1

        removed_files = 0
        indexed_paths = {
            blob.relative_path for blob in self._data.list_blobs(workspace_id)
        }
        audio_dir = self._audio_store.audio_directory(workspace_root)
        if audio_dir.is_dir():
            for path in audio_dir.glob("*.mp3"):
                relative_path = f"assets/audio/{path.name}"
                if relative_path in indexed_paths:
                    continue
                await asyncio.to_thread(path.unlink)
                removed_files += 1
            for path in audio_dir.glob(".*.tmp"):
                if not path.is_file():
                    continue
                await asyncio.to_thread(path.unlink)
                removed_files += 1
        return TTSReconcileResult(
            workspace_id=workspace_id,
            scanned_blobs=len(blobs),
            removed_blobs=removed_blobs,
            removed_files=removed_files,
        )

    @property
    def biz_key(self) -> str:
        return settings.synthesis.biz_key or TTS_REPLY_BIZ_KEY

    @property
    def normalization_revision(self) -> str:
        synthesis = settings.synthesis
        return (
            f"{synthesis.normalization_revision};"
            f"max_chars={synthesis.max_chars_per_part}"
        )


def _fingerprint(content: str) -> str:
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


def _validate_speech_profile(biz_key: str, profile: LLMSpeechProfile) -> None:
    if profile.biz_key != biz_key:
        raise ValueError("LLM speech profile does not match the requested TTS biz key")
    if profile.response_format != "mp3":
        raise ValueError("SessionRoom TTS requires an MP3 speech profile")
    if len(profile.config_fingerprint) != 64:
        raise ValueError("LLM speech profile returned an invalid config fingerprint")
    try:
        bytes.fromhex(profile.config_fingerprint)
    except ValueError as exc:
        raise ValueError(
            "LLM speech profile returned an invalid config fingerprint"
        ) from exc


@dataclass(frozen=True)
class TTSReconcileResult:
    workspace_id: str
    scanned_blobs: int
    removed_blobs: int
    removed_files: int
