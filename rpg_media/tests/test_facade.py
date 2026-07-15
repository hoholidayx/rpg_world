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
    brief_result = facade.create_visual_brief(
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


def test_job_creation_rejects_changed_source(tmp_path) -> None:
    gateway, session, message, facade, _workspace_root = _facade(tmp_path)
    result = facade.create_visual_brief(
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
