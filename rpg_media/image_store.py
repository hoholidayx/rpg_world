"""Validated content-addressed image storage inside catalog workspaces."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from rpg_data import models
from rpg_data.services.catalog import CatalogService
from rpg_data.settings import resolve_workspace_relative_path
from rpg_media.errors import MediaInvalidImageError
from rpg_media.types import InspectedImage, StoredImage

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def inspect_image_bytes(data: bytes) -> InspectedImage:
    payload = bytes(data)
    if payload.startswith(_PNG_SIGNATURE):
        canonical_ext = "png"
        mime_type = "image/png"
    elif len(payload) >= 4 and payload.startswith(b"\xff\xd8\xff"):
        canonical_ext = "jpg"
        mime_type = "image/jpeg"
    elif (
        len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
    ):
        canonical_ext = "webp"
        mime_type = "image/webp"
    else:
        raise MediaInvalidImageError(
            "Generated content is not a supported PNG, JPEG, or WebP image."
        )
    digest = hashlib.sha256(payload).hexdigest()
    return InspectedImage(
        data=payload,
        sha256=digest,
        canonical_ext=canonical_ext,
        mime_type=mime_type,
        byte_size=len(payload),
    )


class WorkspaceImageStore:
    def __init__(self, catalog: CatalogService) -> None:
        self._catalog = catalog

    def put(self, workspace_id: str, data: bytes) -> StoredImage:
        image = inspect_image_bytes(data)
        relative_path = f"assets/images/{image.sha256}.{image.canonical_ext}"
        workspace_root = self._catalog.get_workspace_runtime_dir(str(workspace_id))
        target = resolve_workspace_relative_path(workspace_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing_hash = _hash_file(target)
            if existing_hash != image.sha256:
                raise MediaInvalidImageError(
                    f"Existing content-addressed image is corrupt: {relative_path}"
                )
            return StoredImage(
                image=image,
                relative_path=relative_path,
                absolute_path=str(target),
                file_created=False,
            )

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{image.sha256}.",
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(image.data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
        return StoredImage(
            image=image,
            relative_path=relative_path,
            absolute_path=str(target),
            file_created=True,
        )

    def resolve_blob_path(self, blob: models.MediaBlob) -> Path:
        expected = f"assets/images/{blob.sha256}.{blob.canonical_ext}"
        if blob.relative_path != expected:
            raise ValueError(f"invalid media blob path: {blob.relative_path}")
        workspace_root = self._catalog.get_workspace_runtime_dir(blob.workspace_id)
        return resolve_workspace_relative_path(workspace_root, blob.relative_path)

    def delete_blob_file(self, blob: models.MediaBlob) -> None:
        path = self.resolve_blob_path(blob)
        try:
            path.unlink()
        except FileNotFoundError:
            return

    def delete_stored_file(self, workspace_id: str, stored: StoredImage) -> None:
        workspace_root = self._catalog.get_workspace_runtime_dir(str(workspace_id))
        target = resolve_workspace_relative_path(workspace_root, stored.relative_path)
        if target != Path(stored.absolute_path):
            raise ValueError("stored media path does not match workspace path")
        try:
            target.unlink()
        except FileNotFoundError:
            return


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
