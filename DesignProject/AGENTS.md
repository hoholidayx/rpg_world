# Story Design Workspace

This directory is one portable Story design project. For every request about
story ideation, worldbuilding, characters, lore, status tables, plot
scheduling, visual specifications, Story Pack creation, or RPG World
synchronization, use the workspace-discovered `rpg-story-authoring` Skill for
the entire turn.

## Persistent design rules

- At the start of a design turn, call `story_design_get_resume_context`.
- Treat `design/current.json`, `design/revisions/`, and
  `design/checkpoints/` as MCP-owned state. Do not edit them directly.
- Save every user-confirmed design decision through `story_design_patch`
  during the turn. Supply the current revision as `expectedHead`; reload on a
  stale-head conflict.
- Store structured decisions and concise rationale, not raw conversation
  transcripts. Open questions belong in `openQuestions`.
- Revisions are immutable and linear. Restoring an old revision creates a new
  revision. Named checkpoints are immutable.
- Build one Story per Story Pack. Use section-scoped packs when a smaller,
  reviewable import is sufficient.
- Character cards, lorebook entries, and status tables are owned directly by
  the Story. Do not model a workspace asset library or mount layer for them.
- Narrative styles remain workspace-owned and Story-bound because that is the
  runtime contract.
- Runtime changes require a preview followed by a separate apply tool call
  after explicit user confirmation. Never represent confirmation as a boolean
  argument.
- Do not infer deletion from omission. Story Pack v2 is merge-only and never
  deletes missing runtime resources.
- Character prose at the top level is limited to `name + description`.
  `description` contains objective identity/history only; personality, speech,
  behavior, and psychology belong in tagged details and automatically carry
  `scope:npc_portrayal`.
- `message_mode` is a code-owned, empty-config RP Module with
  `neutral | ic | ooc | gm`; do not model Workspace mode or prompt resources.
- Story Design, Story Pack, DesignProject, and MCP contracts are 2.0 hard cuts.
  Reject v1 inputs; do not create a converter.

## Portability rules

- Keep every project path relative to this directory.
- Do not store credentials, a database path, the RPG World source path, or an
  absolute local path in project data.
- This workspace must not import or depend on any `rpg_*` Python module.
  Runtime access is exclusively through the installed `rpg-world-mcp`
  command.
- The local ChatGPT/Codex conversation is not a source of durable truth.
  Resume from the persisted design revision after compression, reconnect, or
  moving the directory.
- `viewer/` is a read-only local projection. It may read the manifest,
  revisions, schemas, and built Story Packs, but must never become an alternate
  writer for MCP-owned design state or runtime synchronization.
