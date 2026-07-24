# Story design contract

## Contents

- Ownership model
- Top-level document
- Story resources
- Status rules
- Plot scheduling rules
- Visual catalog
- Story Pack sections

## Ownership model

One DesignProject contains one Story. Character cards, lorebook entries, and
status tables belong directly to that Story. They are not workspace assets and
do not use mounts. Narrative styles are the sole workspace-owned resource in
this contract and are bound to the Story at import.

Every importable resource uses a stable textual ID. Runtime numeric IDs are
stored only in RPG World's binding ledger and integration report.
Character-detail IDs and plot-node IDs must also be unique across the whole
Story, not merely within their parent Character or outline.

## Top-level document

`design/current.json` contains:

- `project`: project identity and current design phase.
- `target`: optional runtime target used for Story Pack builds.
- `story`: Story identity, summary, prompt, time setting, themes, and
  boundaries.
- `resources`: importable and visual resources.
- `decisions`: confirmed, tentative, or superseded decision summaries.
- `openQuestions`: unresolved decisions with candidate options.
- `sources`: source references, not copied conversation history.
- `notes`: concise working notes.

The MCP service validates the exact JSON Schema in
`schemas/story-design-v2.schema.json`.
Do not use `_rpgStoryDesign` in Story metadata; the runtime adapter reserves
that key to round-trip design-only Story fields through runtime metadata.
Copy local source material under `design/sources/` and store only a safe
project-relative locator. External URLs and provider IDs are allowed; absolute
paths, `file:` URLs, and parent-directory traversal are rejected.

## Story resources

- `openings`: zero to three title/message pairs.
- `characters`: Story-owned cards with details and visual identity data.
- `lorebook`: Story-owned places, organizations, eras, objects, and rules.
- `statusTables`: Story definitions copied into a Session at creation/reset.
- `narrativeStyles`: workspace-owned styles to create or update and bind.
- `quickReplies`: Story-owned composer shortcuts.
- `rpModules`: Story RP Module settings.
- `plotSchedule`: pools, events, outlines, and nodes.
- `visualCatalog`: independent, image-generation-ready briefs; archived by
  the Story Pack but not materialized as media jobs.

Character top-level data is only `name + description`; `description` contains
identity, history, and objective facts, never personality, speech, behavior,
or psychology that would constrain a player. Put those optional portrayal
settings in Character details. Built-in objective tags are
`kind:appearance | kind:background | kind:relationship | kind:ability`;
portrayal tags are
`kind:personality | kind:speech | kind:behavior | kind:psychology`.
Every portrayal tag automatically carries the locked
`scope:npc_portrayal` tag. Runtime omits those details from a bound player's
Fixed Layer and injects them only when the Character is an NPC or a GM turn
temporarily delegates the player Character.

Message modes are the code-owned `message_mode` RP Module. Its modes are
`neutral | ic | ooc | gm`, its config is empty, and `neutral` is the default.
Mode labels and prompts are not Workspace resources.

## Status rules

`statusKind` is `scene` or `normal`. Scene tables must contain the fixed keys
`时间`, `位置`, and `在场人物`. A Scene time uses the runtime form:

```text
第 2019 年 1 月 1 日 9 时
```

Every status value is eligible for immediate Agent updates in the current
turn. `updateRule` is an optional, trimmed semantic condition layered on top
of the default rule: update only when a fact is explicit and the value
actually changes. It does not schedule delayed or periodic work.

`runtimeKeyLocked` protects only the row key from runtime deletion or rename;
it never makes the value read-only. Status rows do not accept
`updateFrequency`, `deferredIntervalTurns`, or replacement write-permission
fields.

`characterRef` points to one Character stable ID in the same Story. A full
design validates this reference locally. A `statusTables`-only Story Pack may
omit the Character payload only when the target Story already has that stable
Character binding; runtime preview reports a conflict otherwise.

## Plot scheduling rules

Every event references one pool. Every outline node references one event.
Node times must be nondecreasing by node position. Event windows use
`[scheduledTime, deadlineTime)` and therefore require the deadline to be later
than the scheduled time. Non-repeating events use a zero cooldown; repeating
events require a positive cooldown.

An injected outline node means the directive was triggered, not that a
chapter was completed.

## Visual catalog

Use an independent visual specification when an image could be generated and
reused: portraits, sprites, locations, scenes, objects, maps, or costumes.
Keep immutable identity anchors separate from variable costume, pose, light,
and composition details in the resource metadata.

Story Pack v2 archives these briefs. It does not create image binaries, media
assets, jobs, messages, or message metadata.

## Story Pack sections

Valid sections are:

```text
story, openings, characters, lorebook, statusTables, composer,
rpModules, plotSchedule, visualCatalog
```

The schema is `schemas/story-pack-v2.schema.json`. Import policy is always
`mode=merge` and `deleteMissing=false` in v2. Story Design, Story Pack, and
DesignProject v1 inputs are rejected; there is no v1 converter.
