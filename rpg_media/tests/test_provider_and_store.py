from __future__ import annotations

import random

import pytest

from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.errors import MediaInvalidImageError
from rpg_media.image_store import WorkspaceImageStore, inspect_image_bytes
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.providers.selection import RandomFileSelectionStrategy
from rpg_media.types import MediaGenerationRequest, VisualBrief

PNG_A = b"\x89PNG\r\n\x1a\nA"
PNG_B = b"\x89PNG\r\n\x1a\nB"


@pytest.mark.asyncio
async def test_local_provider_uses_injectable_deterministic_random_strategy(tmp_path) -> None:
    (tmp_path / "a.png").write_bytes(PNG_A)
    (tmp_path / "b.png").write_bytes(PNG_B)

    async def not_cancelled() -> bool:
        return False

    request = MediaGenerationRequest(
        job_id="job",
        session_id="session",
        prompt="prompt",
        visual_brief=VisualBrief(scene_description="scene"),
    )
    first = LocalFileProvider(
        tmp_path,
        selection_strategy=RandomFileSelectionStrategy(random.Random(7)),
    )
    second = LocalFileProvider(
        tmp_path,
        selection_strategy=RandomFileSelectionStrategy(random.Random(7)),
    )

    first_result = await first.generate(request, is_cancelled=not_cancelled)
    second_result = await second.generate(request, is_cancelled=not_cancelled)

    assert first_result.data == second_result.data
    assert first_result.provider_asset_id == second_result.provider_asset_id
    assert first.descriptor.available is True


def test_image_magic_is_canonical_source_of_extension() -> None:
    assert inspect_image_bytes(PNG_A).canonical_ext == "png"
    assert inspect_image_bytes(b"\xff\xd8\xffjpeg").canonical_ext == "jpg"
    assert inspect_image_bytes(b"RIFF\x00\x00\x00\x00WEBPdata").canonical_ext == "webp"
    with pytest.raises(MediaInvalidImageError):
        inspect_image_bytes(b"not-an-image")


def test_workspace_store_uses_hash_path_and_deduplicates_file(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "store.sqlite3")
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(tmp_path / "workspace"),),
    )
    store = WorkspaceImageStore(gateway.catalog)

    first = store.put("demo_workspace", PNG_A)
    second = store.put("demo_workspace", PNG_A)

    assert first.relative_path == f"assets/images/{first.image.sha256}.png"
    assert first.file_created is True
    assert second.file_created is False
    assert (tmp_path / "workspace" / first.relative_path).read_bytes() == PNG_A
