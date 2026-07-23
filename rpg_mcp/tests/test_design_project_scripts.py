from __future__ import annotations

import json
import shutil
import subprocess
import sys

from rpg_mcp.contracts import digest_json
from rpg_mcp.generate_design_assets import generate
from rpg_mcp.tests.test_runtime import _pack


def test_portable_doctor_survives_project_relocation(tmp_path) -> None:
    moved = tmp_path / "moved-project"
    shutil.copytree("DesignProject", moved)
    completed = subprocess.run(
        [
            sys.executable,
            moved
            / ".agents/skills/rpg-story-authoring/scripts/portable_doctor.py",
            "--project-root",
            moved,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["healthy"] is True
    assert result["currentRevision"] == "r000001"


def test_portable_story_pack_validator_accepts_v1_fixture(tmp_path) -> None:
    path = tmp_path / "pack.json"
    path.write_text(
        json.dumps(_pack(), ensure_ascii=False),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "DesignProject/.agents/skills/rpg-story-authoring/scripts/"
            "validate_story_pack.py",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["valid"] is True


def test_asset_generation_refreshes_manifest_contract_digest(tmp_path) -> None:
    moved = tmp_path / "project"
    shutil.copytree("DesignProject", moved)
    manifest_path = moved / "design-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contractDigest"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    generate(moved)

    refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = json.loads(
        (moved / "schemas/rpg-mcp-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert refreshed["contractDigest"] != "0" * 64
    assert refreshed["contractDigest"] == digest_json(contract)
    assert refreshed["contractVersion"] == contract["contractVersion"]
