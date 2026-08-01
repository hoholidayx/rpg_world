"""Read-only Story Pack and sidecar discovery for acceptance tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from rpg_mcp.contracts import RESOURCE_SECTIONS, StoryPack, digest_json
from tests.story_acceptance.models import (
    StoryAcceptanceProfile,
    generic_profile,
)


class StoryAcceptanceInputError(ValueError):
    """The selected Pack/profile cannot safely drive an acceptance run."""


@dataclass(frozen=True)
class LoadedStoryPack:
    path: Path
    value: dict[str, Any]
    pack: StoryPack
    canonical_digest: str
    file_sha256: str
    project_root: Path | None = None
    project_manifest: dict[str, Any] | None = None


def load_story_pack(
    *,
    project_root: str | Path | None = None,
    pack_path: str | Path | None = None,
) -> LoadedStoryPack:
    """Load exactly one current full Pack without changing its project."""

    if (project_root is None) == (pack_path is None):
        raise StoryAcceptanceInputError(
            "provide exactly one of --story-project or --story-pack"
        )
    if pack_path is not None:
        return _load_pack_path(_resolved_file(pack_path, "Story Pack"))

    root = _resolved_directory(project_root, "DesignProject")
    manifest_path = root / "design-project.json"
    if not manifest_path.is_file():
        raise StoryAcceptanceInputError(
            f"DesignProject manifest not found: {manifest_path}"
        )
    manifest = _json_object(manifest_path)
    revision = _required_text(manifest, "currentRevision", manifest_path)
    head_digest = _required_text(manifest, "headDigest", manifest_path)
    project_id = _required_text(manifest, "projectId", manifest_path)
    candidates: list[LoadedStoryPack] = []
    pack_dir = root / "artifacts" / "story-packs"
    for candidate_path in sorted(pack_dir.glob("*.json")):
        try:
            candidate = _load_pack_path(candidate_path)
        except StoryAcceptanceInputError:
            continue
        pack = candidate.pack
        if (
            pack.project_id == project_id
            and pack.source_revision == revision
            and pack.source_digest == head_digest
            and set(pack.included_sections) == set(RESOURCE_SECTIONS)
        ):
            candidates.append(candidate)
    if not candidates:
        raise StoryAcceptanceInputError(
            "no current full Story Pack matches DesignProject "
            f"revision={revision!r}, headDigest={head_digest!r}; "
            "build the Pack through story_design_build_pack before testing"
        )
    digests = {candidate.canonical_digest for candidate in candidates}
    if len(digests) > 1:
        paths = ", ".join(str(candidate.path) for candidate in candidates)
        raise StoryAcceptanceInputError(
            "multiple different current full Story Packs match the project; "
            f"select one explicitly with --story-pack: {paths}"
        )
    selected = candidates[-1]
    return LoadedStoryPack(
        path=selected.path,
        value=selected.value,
        pack=selected.pack,
        canonical_digest=selected.canonical_digest,
        file_sha256=selected.file_sha256,
        project_root=root,
        project_manifest=manifest,
    )


def load_acceptance_profile(
    loaded: LoadedStoryPack,
    *,
    profile_path: str | Path | None,
    player_character_ref: str | None,
) -> StoryAcceptanceProfile:
    """Load a matching sidecar or construct the portable smoke profile."""

    if profile_path is None:
        player_ref = str(player_character_ref or "").strip()
        if not player_ref:
            raise StoryAcceptanceInputError(
                "--story-player-ref is required when --story-profile is omitted"
            )
        opening_ref = (
            loaded.pack.resources.openings[0].stable_id
            if loaded.pack.resources.openings
            else None
        )
        profile = generic_profile(
            project_id=loaded.pack.project_id,
            source_revision=loaded.pack.source_revision,
            source_digest=loaded.pack.source_digest,
            player_character_ref=player_ref,
            opening_ref=opening_ref,
            has_plot=bool(loaded.pack.resources.plot_schedule.events),
        )
    else:
        path = _resolved_file(profile_path, "Story acceptance profile")
        try:
            profile = StoryAcceptanceProfile.model_validate(_json_object(path))
        except ValidationError as exc:
            raise StoryAcceptanceInputError(
                f"invalid Story acceptance profile {path}: {exc}"
            ) from exc
        if player_character_ref and (
            profile.player_character_ref != str(player_character_ref).strip()
        ):
            raise StoryAcceptanceInputError(
                "--story-player-ref conflicts with the selected profile"
            )
    _validate_profile_refs(loaded.pack, profile)
    return profile


def _load_pack_path(path: Path) -> LoadedStoryPack:
    raw_bytes = path.read_bytes()
    try:
        value = json.loads(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoryAcceptanceInputError(
            f"Story Pack is not valid UTF-8 JSON: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise StoryAcceptanceInputError(f"Story Pack root must be an object: {path}")
    try:
        pack = StoryPack.model_validate(value)
    except ValidationError as exc:
        raise StoryAcceptanceInputError(f"invalid Story Pack {path}: {exc}") from exc
    normalized = pack.model_dump(by_alias=True, exclude_none=True)
    return LoadedStoryPack(
        path=path,
        value=dict(value),
        pack=pack,
        canonical_digest=digest_json(normalized),
        file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _validate_profile_refs(
    pack: StoryPack,
    profile: StoryAcceptanceProfile,
) -> None:
    identity = profile.pack
    expected = (pack.project_id, pack.source_revision, pack.source_digest)
    actual = (
        identity.project_id,
        identity.source_revision,
        identity.source_digest,
    )
    if actual != expected:
        raise StoryAcceptanceInputError(
            "acceptance profile Pack identity does not match selected Story Pack: "
            f"expected={expected!r}, actual={actual!r}"
        )
    character_refs = {
        character.stable_id for character in pack.resources.characters
    }
    if profile.player_character_ref not in character_refs:
        raise StoryAcceptanceInputError(
            "acceptance playerCharacterRef is absent from the Story Pack: "
            f"{profile.player_character_ref}"
        )
    opening_refs = {opening.stable_id for opening in pack.resources.openings}
    if profile.opening_ref is not None and profile.opening_ref not in opening_refs:
        raise StoryAcceptanceInputError(
            "acceptance openingRef is absent from the Story Pack: "
            f"{profile.opening_ref}"
        )
    all_refs = _pack_refs(pack)
    unknown: set[str] = set()
    for flow in profile.flows:
        for step in flow.steps:
            if step.context is not None:
                unknown.update(set(step.context.required_refs) - all_refs)
                unknown.update(set(step.context.forbidden_refs) - all_refs)
            unknown.update(
                item.table_ref for item in step.status if item.table_ref not in all_refs
            )
            for plot in (
                *((step.plot,) if step.plot is not None else ()),
                *step.additional_plot_checks,
            ):
                for ref in (
                    plot.pending_event_ref,
                    plot.decision_event_ref,
                    plot.decision_pool_ref,
                    plot.forbidden_decision_pool_ref,
                    plot.pool_ref,
                ):
                    if ref is not None and ref not in all_refs:
                        unknown.add(ref)
    if unknown:
        raise StoryAcceptanceInputError(
            f"acceptance profile references unknown stableIds: {sorted(unknown)!r}"
        )


def _pack_refs(pack: StoryPack) -> set[str]:
    resources = pack.resources
    refs = {
        pack.story.stable_id,
        *(item.stable_id for item in resources.openings),
        *(item.stable_id for item in resources.characters),
        *(item.stable_id for item in resources.lorebook),
        *(item.stable_id for item in resources.status_tables),
        *(item.stable_id for item in resources.plot_schedule.pools),
        *(item.stable_id for item in resources.plot_schedule.events),
        *(item.stable_id for item in resources.plot_schedule.outlines),
    }
    for character in resources.characters:
        refs.update(item.stable_id for item in character.details)
    for outline in resources.plot_schedule.outlines:
        refs.update(item.stable_id for item in outline.nodes)
    return refs


def _resolved_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise StoryAcceptanceInputError(f"{label} file not found: {path}")
    return path


def _resolved_directory(value: str | Path | None, label: str) -> Path:
    path = Path(str(value or "")).expanduser().resolve()
    if not path.is_dir():
        raise StoryAcceptanceInputError(f"{label} directory not found: {path}")
    return path


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoryAcceptanceInputError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, Mapping):
        raise StoryAcceptanceInputError(f"JSON root must be an object: {path}")
    return dict(value)


def _required_text(
    value: Mapping[str, Any],
    key: str,
    path: Path,
) -> str:
    result = str(value.get(key, "")).strip()
    if not result:
        raise StoryAcceptanceInputError(f"{path} is missing {key!r}")
    return result


__all__ = [
    "LoadedStoryPack",
    "StoryAcceptanceInputError",
    "load_acceptance_profile",
    "load_story_pack",
]
