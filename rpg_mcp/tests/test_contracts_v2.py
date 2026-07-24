from __future__ import annotations

import pytest
from pydantic import ValidationError

from rpg_mcp.contracts import StoryDesignDocument, StoryPack
from rpg_mcp.tests.test_runtime import _pack


def test_v1_design_and_story_pack_contracts_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StoryDesignDocument.model_validate({"schemaVersion": "story-design/1.0"})

    legacy_pack = _pack()
    legacy_pack["schemaVersion"] = "rpg-story-pack/1.0"
    legacy_pack["contractVersion"] = "1.0"
    with pytest.raises(ValidationError):
        StoryPack.model_validate(legacy_pack)


def test_character_contract_uses_description_and_normalizes_portrayal_scope() -> None:
    document = StoryDesignDocument.model_validate({
        "resources": {
            "characters": [
                {
                    "stableId": "alice",
                    "name": "Alice",
                    "description": "调查记者，随身携带银色录音笔。",
                    "details": [
                        {
                            "stableId": "alice-personality",
                            "name": "性格",
                            "content": "谨慎而敏锐。",
                            "tags": ["kind:personality"],
                        }
                    ],
                }
            ]
        }
    })

    character = document.resources.characters[0]
    assert character.description.startswith("调查记者")
    assert character.details[0].tags == [
        "kind:personality",
        "scope:npc_portrayal",
    ]

    with pytest.raises(ValidationError):
        StoryDesignDocument.model_validate({
            "resources": {
                "characters": [
                    {
                        "stableId": "legacy",
                        "name": "Legacy",
                        "personality": "旧字段",
                        "content": "旧字段",
                    }
                ]
            }
        })


def test_message_mode_module_has_no_story_pack_configuration() -> None:
    with pytest.raises(ValidationError, match="message_mode config must be empty"):
        StoryDesignDocument.model_validate({
            "resources": {
                "rpModules": [
                    {
                        "moduleName": "message_mode",
                        "enabled": True,
                        "config": {"prompt": "custom"},
                    }
                ]
            }
        })
