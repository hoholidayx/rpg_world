"""TTS application service independent from Agent and HTTP frameworks."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from llm_client.keys import TTS_REPLY_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMSpeechProfile
from rpg_data.model import tts as models
from rpg_data.model.session import MESSAGE_ROLE_ASSISTANT
from rpg_tts.audio_store import (
    StoredAudio,
    WorkspaceAudioStore,
    inspect_mp3,
    inspect_mp3_file,
)
from rpg_tts.errors import (
    TTS_ERROR_CODE_CACHE_MISSING,
    TTS_ERROR_CODE_GENERATION_FAILED,
    TTS_ERROR_CODE_JOB_INTERRUPTED,
    TTSError,
    TTSSourceChangedError,
)
from rpg_tts.settings import settings
from rpg_tts.text import normalize_spoken_text, split_spoken_text


class TTSDataPort(Protocol):
    def get_message_source(
        self,
        session_id: str,
        message_id: int,
    ) -> models.TTSMessageSource: ...

    def get_workspace_root(self, workspace_id: str) -> str: ...

    def list_blobs(self, workspace_id: str) -> list[models.TTSBlob]: ...

    def invalidate_blob(
        self,
        blob_id: str,
        *,
        job_status: models.TTSJobStatus,
        error_code: str,
        error_message: str,
    ) -> bool: ...

    def invalidate_cache(
        self,
        cache_entry_id: str,
        *,
        job_status: models.TTSJobStatus,
        error_code: str,
        error_message: str,
    ) -> bool: ...

    def blob_is_referenced(self, blob_id: str) -> bool: ...

    def find_cache_entry(
        self,
        *,
        workspace_id: str,
        source_fingerprint: str,
        config_fingerprint: str,
        normalization_revision: str,
    ) -> models.TTSCacheEntry | None: ...

    def create_or_get_job(
        self,
        *,
        session_id: str,
        message_id: int,
        source_fingerprint: str,
        config_fingerprint: str,
        normalization_revision: str,
        status: models.TTSJobStatus,
        cache_entry_id: str | None,
    ) -> models.TTSJob: ...

    def get_job(self, session_id: str, job_id: str) -> models.TTSJob | None: ...

    def get_job_for_worker(self, job_id: str) -> models.TTSJob | None: ...

    def claim_next_job(self) -> models.TTSJob | None: ...

    def transition_job(
        self,
        session_id: str,
        job_id: str,
        *,
        from_statuses: Iterable[models.TTSJobStatus],
        to_status: models.TTSJobStatus,
        error_code: str = "",
        error_message: str = "",
        clear_started_at: bool = False,
    ) -> models.TTSJob | None: ...

    def transition_jobs(
        self,
        *,
        from_statuses: Iterable[models.TTSJobStatus],
        to_status: models.TTSJobStatus,
        error_code: str = "",
        error_message: str = "",
    ) -> int: ...

    def finish_job(
        self,
        job_id: str,
        *,
        from_statuses: Iterable[models.TTSJobStatus],
        status: models.TTSJobStatus,
        error_code: str = "",
        error_message: str = "",
    ) -> models.TTSJob | None: ...

    def complete_job(
        self,
        job_id: str,
        write: models.TTSJobCompletionWrite,
    ) -> models.TTSJob | None: ...

    def list_parts(
        self,
        session_id: str,
        job_id: str,
    ) -> list[tuple[models.TTSAudioPart, models.TTSBlob]]: ...


class TTSApplicationService:
    def __init__(
        self,
        *,
        data: TTSDataPort,
        audio_store: WorkspaceAudioStore | None = None,
        llm_manager: LLMClientManager | None = None,
    ) -> None:
        self._data = data
        self._audio_store = audio_store or WorkspaceAudioStore()
        self._llm = llm_manager or LLMClientManager.get()
        self._storage_lock = asyncio.Lock()

    async def create_job(self, session_id: str, message_id: int) -> models.TTSJob:
        source = self._data.get_message_source(session_id, message_id)
        _validate_message_source(source)
        spoken = normalize_spoken_text(source.content)
        if not spoken:
            raise ValueError("TTS source message has no speakable text")
        profile = await self._llm.client.get_speech_profile(self.biz_key)
        _validate_speech_profile(self.biz_key, profile)
        source_fingerprint = _fingerprint(source.content)
        cache = self._data.find_cache_entry(
            workspace_id=source.workspace_id,
            source_fingerprint=source_fingerprint,
            config_fingerprint=profile.config_fingerprint,
            normalization_revision=self.normalization_revision,
        )
        return self._data.create_or_get_job(
            session_id=session_id,
            message_id=message_id,
            source_fingerprint=source_fingerprint,
            config_fingerprint=profile.config_fingerprint,
            normalization_revision=self.normalization_revision,
            status=(
                models.TTS_JOB_STATUS_SUCCEEDED
                if cache is not None
                else models.TTS_JOB_STATUS_QUEUED
            ),
            cache_entry_id=cache.id if cache is not None else None,
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
            _validate_message_source(source)
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
                _validate_message_source(current)
                if _fingerprint(current.content) != job.source_fingerprint:
                    raise TTSSourceChangedError("TTS source message changed before publish")
                return self._data.complete_job(
                    job.id,
                    models.TTSJobCompletionWrite(
                        workspace_id=source.workspace_id,
                        source_fingerprint=job.source_fingerprint,
                        config_fingerprint=job.config_fingerprint,
                        normalization_revision=job.normalization_revision,
                        parts=tuple(
                            models.TTSCompletedPart(
                                sha256=part.sha256,
                                byte_size=part.byte_size,
                                relative_path=part.relative_path,
                            )
                            for part in stored_parts
                        ),
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_code = (
                exc.error_code
                if isinstance(exc, TTSError)
                else TTS_ERROR_CODE_GENERATION_FAILED
            )
            return self.fail_job(
                job.id,
                error_code=error_code,
                error_message=str(exc),
            )

    async def retry_job(self, session_id: str, job_id: str) -> models.TTSJob | None:
        job = self._data.get_job(session_id, job_id)
        if job is None:
            return None
        if job.status == models.TTS_JOB_STATUS_SUCCEEDED:
            cached_parts = self.list_parts(session_id, job_id)
            if not cached_parts and job.cache_entry_id:
                self._invalidate_cache(job.cache_entry_id)
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
                self._invalidate_blob(blob.id)
                if path is not None and path.is_file():
                    await asyncio.to_thread(path.unlink)
                job = self._data.get_job(session_id, job_id)
                if job is None:
                    return None
                break
        source = self._data.get_message_source(session_id, job.message_id)
        _validate_message_source(source)
        profile = await self._llm.client.get_speech_profile(self.biz_key)
        _validate_speech_profile(self.biz_key, profile)
        if (
            _fingerprint(source.content) != job.source_fingerprint
            or profile.config_fingerprint != job.config_fingerprint
            or job.normalization_revision != self.normalization_revision
        ):
            return await self.create_job(session_id, job.message_id)
        if job.status in {
            models.TTS_JOB_STATUS_FAILED,
            models.TTS_JOB_STATUS_INTERRUPTED,
        }:
            return self._data.transition_job(
                session_id,
                job_id,
                from_statuses=(
                    models.TTS_JOB_STATUS_FAILED,
                    models.TTS_JOB_STATUS_INTERRUPTED,
                ),
                to_status=models.TTS_JOB_STATUS_QUEUED,
                clear_started_at=True,
            )
        return job

    def get_job(self, session_id: str, job_id: str) -> models.TTSJob | None:
        return self._data.get_job(session_id, job_id)

    def list_parts(
        self,
        session_id: str,
        job_id: str,
    ) -> list[tuple[models.TTSAudioPart, models.TTSBlob]]:
        job = self._data.get_job(session_id, job_id)
        if job is None or job.status != models.TTS_JOB_STATUS_SUCCEEDED:
            return []
        return self._data.list_parts(session_id, job_id)

    def claim_next_job(self) -> models.TTSJob | None:
        return self._data.claim_next_job()

    def interrupt_active_jobs(self) -> int:
        return self._data.transition_jobs(
            from_statuses=(models.TTS_JOB_STATUS_RUNNING,),
            to_status=models.TTS_JOB_STATUS_INTERRUPTED,
            error_code=TTS_ERROR_CODE_JOB_INTERRUPTED,
            error_message="TTS service stopped while the job was running",
        )

    def fail_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.TTSJob | None:
        return self._data.finish_job(
            job_id,
            from_statuses=(models.TTS_JOB_STATUS_RUNNING,),
            status=models.TTS_JOB_STATUS_FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def resolve_audio_part(self, session_id: str, job_id: str, part_index: int) -> Path:
        parts = self.list_parts(session_id, job_id)
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
        _validate_message_source(source)
        path = self._audio_store.resolve(
            source.workspace_root,
            sha256=blob.sha256,
            relative_path=blob.relative_path,
        )
        if not path.is_file():
            self._invalidate_blob(blob.id)
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
            self._invalidate_blob(blob.id)
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
            self._invalidate_blob(blob.id)
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

    def _invalidate_blob(self, blob_id: str) -> bool:
        return self._data.invalidate_blob(
            blob_id,
            job_status=models.TTS_JOB_STATUS_FAILED,
            error_code=TTS_ERROR_CODE_CACHE_MISSING,
            error_message="Cached TTS audio is missing or corrupt",
        )

    def _invalidate_cache(self, cache_entry_id: str) -> bool:
        return self._data.invalidate_cache(
            cache_entry_id,
            job_status=models.TTS_JOB_STATUS_FAILED,
            error_code=TTS_ERROR_CODE_CACHE_MISSING,
            error_message="Cached TTS audio is missing or corrupt",
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


def _validate_message_source(source: models.TTSMessageSource) -> None:
    if (
        source.role != MESSAGE_ROLE_ASSISTANT
        or source.turn_id <= 0
        or source.seq_in_turn <= 0
    ):
        raise ValueError("TTS only supports persisted assistant messages")
    if not source.content.strip():
        raise ValueError("TTS source message is empty")


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
