# Authoring workflow

## Contents

- Resume protocol
- Decision protocol
- JSON Patch examples
- Checkpoint milestones
- Story Pack workflow

## Resume protocol

Call `story_design_get_resume_context` at the start of every design turn. The
returned `revision` is the only valid `expectedHead` for the first mutation.
Use `story_design_get_section` when a specific resource is too large for the
resume summary.

After context compression or a new conversation, do not reconstruct decisions
from memory. Reload the persisted resume context and continue from it.

## Decision protocol

For an unresolved, consequential choice:

1. Explain two or more concrete options and their tradeoffs.
2. Keep the question in `/openQuestions` while it is unresolved.
3. After the user chooses, update the affected design fields and append a
   concise confirmed decision in the same patch.
4. Change the open question to `resolved`, or remove it only when its context
   has become wholly redundant.

Use deterministic decision IDs, for example `decision-player-role` or
`decision-ending-tone`. When a decision changes, mark the older record
`superseded` and add a new record rather than rewriting history invisibly.

## JSON Patch examples

Append a confirmed decision and update the Story premise:

```json
[
  {
    "op": "replace",
    "path": "/story/logline",
    "value": "一名失忆调查员必须在城市重置前找回自己主动删除的证词。"
  },
  {
    "op": "add",
    "path": "/decisions/-",
    "value": {
      "id": "decision-core-logline",
      "topic": "核心故事钩子",
      "decision": "主角曾主动删除自己的关键证词。",
      "rationale": "让失忆与玩家能动性直接相关。",
      "status": "confirmed",
      "decidedAt": "2026-01-01T00:00:00Z"
    }
  }
]
```

Add a character:

```json
[
  {
    "op": "add",
    "path": "/resources/characters/-",
    "value": {
      "stableId": "character-lin",
      "name": "林澈",
      "description": "一名曾主动删除关键证词的失忆调查员。",
      "aliases": [],
      "details": [
        {
          "stableId": "character-lin-personality",
          "name": "NPC 演绎性格",
          "content": "克制、观察力强，对自己的记忆保持怀疑。",
          "tags": ["kind:personality", "scope:npc_portrayal"],
          "sortOrder": 10
        }
      ],
      "visual": {
        "identityAnchors": ["黑色短发", "旧银色录音笔"]
      },
      "sortOrder": 10,
      "metadata": {}
    }
  }
]
```

Use a `test` operation when the patch depends on a field value in addition to
the revision CAS.

## Checkpoint milestones

Create a named checkpoint after:

- the premise, player role, tone, and safety boundaries are stable;
- the primary characters and world rules are stable;
- openings, status tables, and plot scheduling are internally consistent;
- a Story Pack validates and is ready for runtime preview.

Good names are `architecture-ready`, `resources-ready`, and
`runtime-preview-ready`; avoid contract-version suffixes in milestone names.

## Story Pack workflow

The default section list creates a complete pack. Useful small packages:

- `["story", "openings"]`
- `["characters", "statusTables", "visualCatalog"]`
- `["statusTables"]` after referenced Characters have already been imported
- `["lorebook"]`
- `["plotSchedule", "rpModules"]`
- `["composer"]`

A small pack does not delete resources from omitted sections. A full pack also
uses merge-only semantics in v2.
