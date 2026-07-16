from __future__ import annotations

import pytest

from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.errors import MediaAssetInUseDomainError, MediaSourceChangedError
from rpg_media.facade import MediaFacade
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.types import VisualBrief

PNG = b"\x89PNG\r\n\x1a\nfacade"


def _facade(tmp_path):  # noqa: ANN202
    gateway = get_data_service_gateway(tmp_path / "facade.sqlite3")
    workspace_root = tmp_path / "workspace"
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(workspace_root),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="facade")
    assert session is not None
    source_dir = tmp_path / "provider"
    source_dir.mkdir()
    (source_dir / "sample.png").write_bytes(PNG)
    providers = MediaProviderCatalog(
        (LocalFileProvider(source_dir),),
        default_key="local_file",
    )
    facade = MediaFacade(
        data=gateway.media,
        catalog=gateway.catalog,
        planner=DemoVisualBriefPlanner(),
        providers=providers,
    )
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "进入月光下的森林",
        turn_id=1,
        seq_in_turn=1,
    )
    return gateway, session, message, facade, workspace_root


@pytest.mark.asyncio
async def test_manual_brief_job_gallery_background_and_stale_flow(tmp_path) -> None:
    gateway, session, message, facade, workspace_root = _facade(tmp_path)
    brief_result = await facade.create_visual_brief(
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    edited_brief = VisualBrief(
        **{
            **brief_result.brief.__dict__,
            "style": "edited painterly style",
        }
    )
    job = facade.create_job(
        session.id,
        provider_key="local_file",
        start_turn_id=1,
        end_turn_id=1,
        source_fingerprint=brief_result.source.fingerprint,
        visual_brief=edited_brief,
    )
    claimed = gateway.media.claim_next_job()
    assert claimed is not None and claimed.id == job.id

    completed = await facade.execute_job(job.id)

    assert completed is not None
    assert completed.status == models.MEDIA_JOB_STATUS_SUCCEEDED
    gallery = facade.list_gallery(session.id)
    assert len(gallery) == 1
    assert gallery[0].source_stale is False
    assert VisualBrief.from_json(gallery[0].bundle.asset.visual_brief_json).style == "edited painterly style"
    library = facade.list_library_assets(
        "demo_workspace",
        scope=models.MEDIA_LIBRARY_SCOPE_STORY,
        story_id=1,
    )
    assert len(library) == 1
    assert library[0].asset.id == gallery[0].bundle.asset.id
    assert library[0].asset.origin_kind == models.MEDIA_ASSET_ORIGIN_GENERATED
    assert library[0].item.title.startswith("依据所选剧情还原这一幕")
    assert "generated" in library[0].tags
    assert "edited painterly style" in library[0].tags
    content_path, mime_type = facade.resolve_asset_content(
        session.id,
        gallery[0].bundle.asset.id,
    )
    assert content_path.read_bytes() == PNG
    assert content_path.is_relative_to(workspace_root)
    assert mime_type == "image/png"

    facade.set_background(session.id, gallery[0].bundle.asset.id)
    with pytest.raises(MediaAssetInUseDomainError):
        facade.delete_asset(session.id, gallery[0].bundle.asset.id)

    gateway.messages.update(message.id, content="剧情已经改变")
    assert facade.list_gallery(session.id)[0].source_stale is True

    assert facade.clear_background(session.id) is True
    assert facade.delete_asset(session.id, gallery[0].bundle.asset.id) is True
    assert not content_path.exists()


@pytest.mark.asyncio
async def test_job_creation_rejects_changed_source(tmp_path) -> None:
    gateway, session, message, facade, _workspace_root = _facade(tmp_path)
    result = await facade.create_visual_brief(
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    gateway.messages.update(message.id, content="changed")

    with pytest.raises(MediaSourceChangedError) as exc_info:
        facade.create_job(
            session.id,
            provider_key="local_file",
            start_turn_id=1,
            end_turn_id=1,
            source_fingerprint=result.source.fingerprint,
            visual_brief=result.brief,
        )

    assert exc_info.value.code == "MEDIA_SOURCE_CHANGED"


@pytest.mark.asyncio
async def test_missing_workspace_image_prunes_gallery_library_and_background(tmp_path) -> None:
    gateway, session, _message, facade, _workspace_root = _facade(tmp_path)
    brief_result = await facade.create_visual_brief(
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    job = facade.create_job(
        session.id,
        provider_key="local_file",
        start_turn_id=1,
        end_turn_id=1,
        source_fingerprint=brief_result.source.fingerprint,
        visual_brief=brief_result.brief,
    )
    assert gateway.media.claim_next_job() is not None
    assert await facade.execute_job(job.id) is not None
    gallery = facade.list_gallery(session.id)
    assert len(gallery) == 1
    asset_id = gallery[0].bundle.asset.id
    content_path, _mime_type = facade.resolve_asset_content(session.id, asset_id)
    facade.set_background(session.id, asset_id)

    content_path.unlink()

    assert facade.list_gallery(session.id) == []
    assert facade.list_library_assets("demo_workspace") == []
    assert gateway.media.get_session_asset(session.id, asset_id) is not None
    assert gateway.media.get_background(session.id) is not None
    background = facade.get_background(session.id)
    assert background is not None
    assert background.asset is None
    assert gateway.media.get_session_asset(session.id, asset_id) is None
    assert gateway.media.get_background(session.id) is None


@pytest.mark.asyncio
async def test_reconcile_scans_workspace_and_leaves_unindexed_files_untouched(tmp_path) -> None:
    gateway, session, _message, facade, workspace_root = _facade(tmp_path)

    async def upload(title: str, payload: bytes):  # noqa: ANN202
        return await facade.upload_library_asset(
            workspace_id="demo_workspace",
            scope=models.MEDIA_LIBRARY_SCOPE_STORY,
            story_id=1,
            title=title,
            description=f"{title} description",
            tags=(title.casefold(),),
            is_default=False,
            data=payload,
        )

    missing = await upload("Missing", b"\x89PNG\r\n\x1a\nmissing")
    invalid = await upload("Invalid", b"\x89PNG\r\n\x1a\ninvalid")
    existing = await upload("Existing", b"\x89PNG\r\n\x1a\nexisting")
    missing_path, _ = facade.resolve_library_asset_content(
        "demo_workspace",
        missing.item.id,
    )
    invalid_original_path, _ = facade.resolve_library_asset_content(
        "demo_workspace",
        invalid.item.id,
    )
    existing_path, _ = facade.resolve_library_asset_content(
        "demo_workspace",
        existing.item.id,
    )
    facade.set_background(session.id, missing.asset.id)
    missing_path.unlink()
    gateway.database.execute_sql(
        "UPDATE rpg_media_blobs SET relative_path = ? WHERE id = ?",
        ("../invalid.png", invalid.blob.id),
    )
    orphan = workspace_root / "assets" / "images" / "not-indexed.png"
    orphan.write_bytes(PNG)

    visible = facade.list_library_assets("demo_workspace")

    assert [bundle.item.id for bundle in visible] == [existing.item.id]
    assert gateway.media.get_library_asset("demo_workspace", missing.item.id) is not None
    assert gateway.media.get_library_asset("demo_workspace", invalid.item.id) is not None

    result = await facade.reconcile_library_assets("demo_workspace")

    assert result == models.MediaLibraryReconcileResult(
        workspace_id="demo_workspace",
        scanned_blobs=3,
        removed_blobs=2,
        removed_assets=2,
        removed_library_items=2,
        removed_gallery_items=0,
        cleared_backgrounds=1,
    )
    assert gateway.media.get_background(session.id) is None
    assert gateway.media.get_library_asset("demo_workspace", missing.item.id) is None
    assert gateway.media.get_library_asset("demo_workspace", invalid.item.id) is None
    assert gateway.media.get_library_asset("demo_workspace", existing.item.id) is not None
    assert existing_path.is_file()
    assert invalid_original_path.is_file()
    assert orphan.is_file()

    repeated = await facade.reconcile_library_assets("demo_workspace")
    assert repeated == models.MediaLibraryReconcileResult(
        workspace_id="demo_workspace",
        scanned_blobs=1,
    )
