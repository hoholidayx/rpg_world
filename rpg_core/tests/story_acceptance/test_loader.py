from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.story_acceptance.loader import (
    StoryAcceptanceInputError,
    load_acceptance_profile,
    load_story_pack,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _project(tmp_path: Path, pack: dict, *extra_packs: dict) -> Path:
    root = tmp_path / "DesignProject"
    _write_json(
        root / "design-project.json",
        {
            "projectId": pack["projectId"],
            "currentRevision": pack["sourceRevision"],
            "headDigest": pack["sourceDigest"],
        },
    )
    _write_json(root / "artifacts/story-packs/a.json", pack)
    for index, value in enumerate(extra_packs, start=1):
        _write_json(root / f"artifacts/story-packs/z{index}.json", value)
    return root


def test_selects_current_complete_pack(story_pack_value: dict, tmp_path: Path) -> None:
    root = _project(tmp_path, story_pack_value)

    loaded = load_story_pack(project_root=root)

    assert loaded.pack.source_revision == "r000002"
    assert loaded.project_root == root.resolve()
    assert loaded.path.name == "a.json"


def test_rejects_stale_project_pack(story_pack_value: dict, tmp_path: Path) -> None:
    root = _project(tmp_path, story_pack_value)
    manifest = json.loads((root / "design-project.json").read_text())
    manifest["currentRevision"] = "r000003"
    _write_json(root / "design-project.json", manifest)

    with pytest.raises(StoryAcceptanceInputError, match="no current full"):
        load_story_pack(project_root=root)


def test_rejects_multiple_different_current_packs(
    story_pack_value: dict,
    tmp_path: Path,
) -> None:
    different = deepcopy(story_pack_value)
    different["story"]["summary"] = "不同但仍声明同 revision 的 Pack。"
    root = _project(tmp_path, story_pack_value, different)

    with pytest.raises(StoryAcceptanceInputError, match="multiple different"):
        load_story_pack(project_root=root)


def test_profile_identity_and_stable_refs_are_validated(
    story_pack_value: dict,
    tmp_path: Path,
) -> None:
    pack_path = tmp_path / "pack.json"
    _write_json(pack_path, story_pack_value)
    loaded = load_story_pack(pack_path=pack_path)
    profile = load_acceptance_profile(
        loaded,
        profile_path=None,
        player_character_ref="character-player",
    )
    assert profile.opening_ref == "opening-main"

    with pytest.raises(StoryAcceptanceInputError, match="absent"):
        load_acceptance_profile(
            loaded,
            profile_path=None,
            player_character_ref="character-missing",
        )


def test_requires_exactly_one_pack_source() -> None:
    with pytest.raises(StoryAcceptanceInputError, match="exactly one"):
        load_story_pack()
