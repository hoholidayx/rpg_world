from __future__ import annotations

from rpg_core.session.catalog import SessionCatalogService
from rpg_data.services.gateway import DataServiceGateway


def test_story_pack_binding_and_operation_cas(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "runtime.sqlite3")
    try:
        gateway.catalog.create_workspace(
            "pack_world",
            name="Pack World",
            root_path="data/pack_world",
        )
        story = SessionCatalogService(gateway.sessions).create_story(
            "pack_world",
            title="Pack Story",
        )
        assert story is not None

        binding = gateway.story_packs.upsert_binding(
            "pack_world",
            story.id,
            "story",
            "story-main",
            resource_id=story.id,
            source_digest="a" * 64,
            resource_version=story.version,
            metadata={"projectId": "pack-project"},
        )
        assert binding.resource_id == str(story.id)
        assert gateway.story_packs.find_bindings(
            "pack_world",
            "story",
            "story-main",
        ) == [binding]

        operation = gateway.story_packs.create_operation(
            "sp_test",
            operation_kind="story_pack",
            project_id="pack-project",
            pack_id="pack-1",
            pack_digest="b" * 64,
            workspace_id="pack_world",
            story_stable_id="story-main",
            story_id=story.id,
            pack={"schemaVersion": "rpg-story-pack/2.0"},
            plan={"conflicts": []},
        )
        assert operation.status == "previewed"
        with gateway.story_packs.transaction():
            claimed = gateway.story_packs.claim_operation(operation.id)
            assert claimed is not None
            assert gateway.story_packs.claim_operation(operation.id) is None
            completed = gateway.story_packs.complete_operation(
                operation.id,
                story_id=story.id,
                result={"storyId": story.id},
            )
            assert completed is not None
        assert gateway.story_packs.get_operation(operation.id).status == "applied"
        assert gateway.story_packs.find_completed_operation(
            "pack_world",
            "story-main",
            "b" * 64,
            operation_kind="story_pack",
        ).id == operation.id
    finally:
        gateway.close()


def test_story_pack_binding_requires_story_ownership(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "runtime.sqlite3")
    try:
        gateway.catalog.create_workspace(
            "one",
            name="One",
            root_path="data/one",
        )
        gateway.catalog.create_workspace(
            "two",
            name="Two",
            root_path="data/two",
        )
        story = SessionCatalogService(gateway.sessions).create_story(
            "one",
            title="Story",
        )
        assert story is not None
        try:
            gateway.story_packs.upsert_binding(
                "two",
                story.id,
                "story",
                "story-main",
                resource_id=story.id,
                source_digest="a" * 64,
                resource_version=story.version,
            )
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("cross-workspace Story binding must fail")
    finally:
        gateway.close()
