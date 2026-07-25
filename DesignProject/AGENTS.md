# Story Design Workspace

This directory is one portable Story design project. For every request about
story ideation, worldbuilding, characters, lore, status tables, plot
scheduling, visual specifications, Story Pack creation, or RPG World
synchronization, use the workspace-discovered `rpg-story-authoring` Skill for
the entire turn.

## Persistent design rules

- At the start of a design turn, call `story_design_get_resume_context`.
- When a field's duty, example, or runtime effect is uncertain, call
  `story_design_get_authoring_rules` and read only the relevant domain. The
  generated field references and machine-readable catalog are the semantic
  source; do not reinterpret a field from its name.
- Treat `design/current.json`, `design/revisions/`, and
  `design/checkpoints/` as MCP-owned state. Do not edit them directly.
- Save every user-confirmed design decision through `story_design_patch`
  during the turn. Supply the current revision as `expectedHead`; reload on a
  stale-head conflict. Review returned `advisoryDiagnostics` and correct or
  explicitly justify field-duty warnings.
- Store structured decisions and concise rationale, not raw conversation
  transcripts. Open questions belong in `openQuestions`.
- Revisions are immutable and linear. Restoring an old revision creates a new
  revision. Named checkpoints are immutable.
- Build one Story per Story Pack. Use section-scoped packs when a smaller,
  reviewable import is sufficient.
- A local revision is not a release. Build only from the current revision;
  historical revisions and files under `design/sources/` remain references.
  Their presence does not authorize importing their content. Re-select,
  author, and confirm content into the current revision first.
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
- For status tables, put table-wide semantics, value formats, and shared
  immediate-update rules in `description`. Put only field-specific conditions
  in each row `updateRule`; do not assume that `value` is numeric. A `value`
  is a string that may express a number, enum, list, short description, or
  current fact state. Status tables hold current state that needs per-turn
  visibility and updates. Memory is better suited to time-ordered narrative
  history, but current facts, commitments, contacts, or event states may still
  be modeled as status rows.
- `message_mode` is a code-owned, empty-config RP Module with
  `neutral | ic | ooc | gm`; do not model Workspace mode or prompt resources.
- Story Design, Story Pack, DesignProject, and MCP contracts are 2.0 hard cuts.
  Reject v1 inputs; do not create a converter.
- `authoringRulesVersion` is independent from Story Pack `contractVersion`.
  Validate with `profile=draft` while iterating and `profile=package` before a
  build. Errors are deterministic gates; warnings are structured authoring
  review items.
- Rule, Schema, Skill, and generated field-reference refreshes require the
  dedicated preview/apply tools. They may update managed assets and manifest
  digests only; they must not modify current/revisions/checkpoints, Story
  Packs, or runtime integration files.

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
  revisions, authoring rules/diagnostics, schemas, and built Story Packs, but
  must never become an alternate writer for MCP-owned design state or runtime
  synchronization.
