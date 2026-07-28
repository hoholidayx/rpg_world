# Story design contract

> authoringRulesVersion=1.1 ·
> catalogDigest=1acda22f205196e619d530f3034bbf002d9ced110199a5e35fa5ba089507be2a

## Contract and ownership

- Support only `story-design/2.0`, `rpg-story-pack/2.0`,
  `story-design-project/2.0`, and MCP `contractVersion=2.0`.
- Keep one Story per DesignProject and one Story per Story Pack.
- Own Character, Lorebook, Status, Opening, Quick Reply, RP Module, Plot, and
  Visual Catalog resources directly from the Story. Narrative Style remains
  Workspace-owned and Story-bound because that is the runtime contract.
- Keep every stable ID durable across revision, section-scoped packs, and
  runtime synchronization. Character-detail and plot-node IDs are unique
  across the whole Story.

## Authoring rule source

The complete machine-readable catalog is
`schemas/story-authoring-rules-v1.json`. It supplies every Schema field
description/example, MCP diagnostics, the Viewer field guide, and these
domain references:

- `fields-project-story.md`
- `fields-characters-lorebook.md`
- `fields-status-scene.md`
- `fields-plot-rp-composer.md`
- `fields-visual-workflow.md`

Use the relevant domain reference instead of reinterpreting a field from its
name. The `authoringRulesVersion` evolves independently from Story Pack
`contractVersion`; adding or clarifying author guidance does not by itself
change the import contract.

## Cross-resource invariants

- Character `description` contains only objective identity/history. Put
  personality, speech, behavior, and psychology in tagged details; portrayal
  details carry `scope:npc_portrayal` and are filtered by player/NPC/GM turn.
- Scene tables contain `时间`, `位置`, and `在场人物`. Use parseable virtual
  time such as `2020 年 7 月 18 日 9 时`.
- Status table `description` contains table-wide semantics, value formats,
  and shared immediate-update rules.
- Status rows contain only `key`, `value`, `runtimeKeyLocked`, `updateRule`,
  and `metadata`. `value` is a string that may express a number, enum, list,
  short description, or current fact state. A row `updateRule` contains only
  field-specific immediate conditions and does not assume a numeric model.
- Status tables hold current state that needs per-turn visibility and updates.
  Memory is better suited to time-ordered narrative history, but current
  facts, commitments, contacts, or event states may still be status rows.
- `message_mode` is code-owned, uses `neutral | ic | ooc | gm`, and has empty
  Story config. OOC does not advance world facts.
- Plot event `description`, `suitabilityHint`, and `directive` have separate
  duties. An outline node trigger does not mean chapter completion.
- Visual Catalog is archive-only. A Story Pack never creates media binaries,
  jobs, messages, or message metadata.
- Source records are references only. Re-select, author, and confirm content
  into the current revision before it can enter a Story Pack.

## Story Pack behavior

Valid sections are `story`, `openings`, `characters`, `lorebook`,
`statusTables`, `composer`, `rpModules`, `plotSchedule`, and `visualCatalog`.
Every v2 pack is merge-only with `deleteMissing=false`; omission never grants
deletion authority. Runtime changes always require separate preview and apply
calls after explicit user confirmation.
