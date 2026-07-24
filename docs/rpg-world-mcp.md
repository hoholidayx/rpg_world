# RPG World MCP service

`rpg-world-mcp` is an independent process boundary. It is not started by
`run_all.py` and does not join Agent, Play API, Media, TTS, Dream, or LLM
runtimes.

## Delivery

The installed command has one mode switch:

```text
rpg-world-mcp --mode design|runtime|all
```

- `design` loads only the neutral `rpg_mcp` contracts and file-backed
  DesignProject store. It must not import or initialize `rpg_core`,
  `rpg_data`, or SQLite.
- `runtime` lazily composes narrow RPG application/data services and exposes
  runtime reads plus Story Pack validation, preview, apply, snapshot, and
  operation-result tools.
- `all` exposes both groups and the compare, preview-sync, apply-sync, and
  reconcile tools.

The default transport is stdio. Streamable HTTP exists only for a local
Inspector and the CLI rejects non-loopback hosts. ChatGPT uses OpenAI Secure
MCP Tunnel to forward to the same local command rather than opening public
ingress.

## Story design boundary

A DesignProject is a standalone, movable directory. It contains:

- a workspace `AGENTS.md` and auto-discovered
  `.agents/skills/rpg-story-authoring/`;
- a structured current design;
- linear immutable revisions with expected-head CAS;
- immutable named checkpoints;
- neutral JSON Schema and MCP contract files;
- full or section-scoped Story Packs;
- runtime snapshots, integration state, and reports.

It stores only relative paths and never imports an RPG package. Complete chat
history is intentionally not persisted; confirmed decisions, open questions,
source summaries, and Story resources are.

## Story Pack v1

One pack contains one Story. Sections are:

```text
story, openings, characters, lorebook, statusTables, composer,
rpModules, plotSchedule, visualCatalog
```

The policy is always merge-only with `deleteMissing=false`. Character,
lorebook, and status resources are Story-owned. Narrative styles are
workspace-owned and Story-bound. Visual specifications are archived in the
pack/operation but do not create media data.

A status-only pack may refer to a Character omitted from that pack only when
the target Story already has the same-project stable Character binding.
Preview reports missing, stale, or foreign bindings as conflicts.

Status rows use the same hard-cut contract as RPG World runtime schema v2:
`key`, `value`, `runtimeKeyLocked`, `updateRule`, and `metadata`. All values
are eligible for current-turn Agent updates. `updateRule` is semantic guidance
only, while `runtimeKeyLocked` protects key structure only. Legacy frequency,
interval, or replacement write-permission fields are rejected by the generated
schemas, portable validator, preview, apply, compare, and reconcile paths.

The importer never creates Sessions, messages, media jobs, TTS jobs, or
binaries.

## Confirmation and recovery

Preview and apply are separate tools. A preview persists an opaque operation
ID and per-resource plan. Apply accepts only that ID and has a destructive
tool annotation; it intentionally has no confirmation boolean. An operation
must be applied through the lane that created it (`story_pack`, `changes`, or
`runtime_sync`).

Runtime resource identity is stored in `rpg_story_pack_bindings`. The binding
baseline includes source digest and runtime resource version, enabling a
conservative three-way decision:

- unchanged source + unchanged runtime: unchanged;
- unchanged source + changed runtime: preserve as `runtime_modified`;
- changed source + unchanged runtime: update;
- changed source + changed runtime: conflict.

Narrative-style bindings additionally track the Story mount version and
`isBase`, so an unmount or base-style change participates in the same drift
decision. Story fields that have no first-class runtime column (`timeSetting`,
`logline`, `themes`, and `boundaries`) are round-tripped through reserved Story
metadata instead of being silently discarded.

`rpg_story_pack_operations` is the preview/apply audit and recovery truth.
Database business writes and the `applied` transition commit in one
transaction. In all mode, DesignProject integration/report files are written
afterward. A file failure changes the operation to
`applied_with_local_sync_pending`; retrying the same operation ID repairs only
the files and cannot repeat the business write.

## Maintenance checks

Focused checks:

```text
uv run python -m pytest rpg_mcp/tests \
  rpg_data/tests/test_story_pack_service.py \
  rpg_data/tests/test_architecture_boundaries.py \
  rpg_data/tests/test_migrations.py -q
```

Skill validation:

```text
uv run python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  DesignProject/.agents/skills/rpg-story-authoring
```

Regenerate checked-in neutral schemas after a contract-model change:

```text
uv run python -m rpg_mcp.generate_design_assets DesignProject
```
