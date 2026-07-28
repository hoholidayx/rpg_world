---
name: rpg-story-authoring
description: Persist, resume, revise, inspect, validate, and package a portable RPG Story design, including story architecture, characters, lorebook entries, status tables, openings, composer settings, plot schedules, and image-worthy visual specifications. Use for story brainstorming or decisions, continuing after context compression or a new session, interpreting field semantics or diagnostics, opening the live read-only revision/schema/field-guide/Story Pack viewer, creating checkpoints, building full or section-scoped Story Packs, comparing a design with RPG World, and previewing or applying an explicitly confirmed runtime synchronization.
---

# RPG Story Authoring

<!-- authoring-rules-version: 1.3 -->
<!-- authoring-rules-digest: 340c9ac89c0854acee8f39bf0badd0e49c1171d21a497ef009431a680df9d431 -->

Persist the Story design as immutable local revisions and use
`rpg-world-mcp` as the only runtime boundary. Never rely on conversation
history as the durable design source.

## Start or resume

1. Call `story_design_get_resume_context` before discussing or changing the
   design.
2. Summarize the current revision, confirmed decisions, unresolved questions,
   and the next useful decision.
3. Call `story_design_get_authoring_rules` when a field's meaning or runtime
   effect is uncertain. Do not infer semantics from its name alone.
4. If the MCP tool is unavailable, stop before editing design state and run
   `scripts/portable_doctor.py` only for read-only diagnosis.

## Discuss and persist

Offer concrete options for consequential, unresolved choices. Do not invent a
confirmation. Once the user confirms a choice:

1. Prepare one minimal JSON Patch containing the design changes.
2. Append or supersede a concise record in `/decisions`.
3. Resolve the corresponding `/openQuestions` item if present.
4. Call `story_design_patch` with the current revision as `expectedHead` and a
   specific reason.
5. Read `advisoryDiagnostics`; correct field-duty warnings or explain a
   deliberate exception.
6. Treat a stale-head response as a CAS conflict: reload resume context,
   rebase the intended change, and never overwrite the newer head.

Save confirmed decisions during the turn, not only at the end. Keep tentative
ideas as open questions or notes; do not label them confirmed. Read
`references/authoring-workflow.md` for patch examples and milestone rules.

## Model the Story

Keep one Story in the project. Character, lorebook, and status resources are
Story-owned. Include image-worthy material in both the relevant resource's
`visual` field and `/resources/visualCatalog` when it deserves an independent
generation brief. Use Story virtual calendar years such as 2019 or 2020 when
the fiction is anchored to those years; do not replace them with placeholder
year 1.

Treat `neutral | ic | gm` as non-OOC body turns; OOC and commands do not
advance world facts. Do not model automatic Plot selection as a per-turn
poll. A successfully committed net change to the entire active Scene document
creates one opportunity for the next non-OOC turn; `scheduledTime` and
`deadlineTime` only gate candidates inside that opportunity. Do not author
no-op Scene changes to poll Plot.

An event referenced by any outline node is exclusive to the outline lane and
does not consume pool-lane selection until every node reference is removed.
`cooldownMinutes` pauses the whole pool after any scheduler-origin pool event
is successfully injected; manual and outline injections do not change that
pool-level anchor.

Keep `plot_event_mark_next` state out of Story Design and Story Pack fields.
It is an OOC/GM Session runtime snapshot for the next non-OOC turn, may
temporarily override `title` and `directive`, and ignores all automatic
eligibility rules without changing the source event or pool-level cooldown.

Read the relevant generated field reference before adding or substantially
rewriting that domain:

- Project, Story, Opening, target, or Story Pack:
  `references/fields-project-story.md`
- Character or Lorebook:
  `references/fields-characters-lorebook.md`
- Status or Scene:
  `references/fields-status-scene.md`
- Plot, RP Module, Narrative Style, or Quick Reply:
  `references/fields-plot-rp-composer.md`
- Visual Catalog, sources, decisions, or open questions:
  `references/fields-visual-workflow.md`

Use `references/story-design-contract.md` for ownership and cross-resource
invariants. Do not copy the whole field catalog into the active context when
only one domain is needed.

## Validate and checkpoint

Call `story_design_validate(profile="draft")` while iterating. Before a
milestone or package build, use `profile="package"` and resolve every error;
warnings identify field-duty or quality risks and do not silently become
errors. Package builds always run the package profile again.

Create a named checkpoint after a stable architecture, resource set, or
import-ready state. Checkpoints do not replace automatic revisions. Use
`story_design_diff_revisions` before restoring a revision, and restore with
`story_design_restore_revision`; never alter or delete an old revision file.

## Run the read-only viewer

When the user asks to start, open, or inspect the Story visualization,
revision history, field guide, diagnostics, Schema, or built Story Packs:

1. Treat the current workspace as the DesignProject root and require
   `viewer/serve.py`. Do not copy the viewer elsewhere or import RPG modules.
2. If `http://127.0.0.1:8787/api/project` already returns this project's
   `projectId` and `headDigest`, reuse it. If the port is occupied by another
   process or project, do not stop it; start with `--port 0` and use the URL
   printed by the server.
3. Otherwise start a retained process from the project root with
   `python3 viewer/serve.py --port 8787`. Add `--open` only when the user asks
   to open the browser and GUI launch is permitted.
4. Verify `/api/project` reports the current revision, keep the process
   running, and return the exact loopback URL.
5. For stop or restart requests, target only the exact retained Viewer
   process; never terminate an unknown listener.

A Viewer-only request is operational and read-only; do not call mutation tools
merely to start it. Viewer failures never authorize direct edits to MCP-owned
design state or Story Packs.

## Build and synchronize

Build a full Story Pack by default. For small reviewable packages, pass only
the required sections to `story_design_build_pack`; every pack remains
merge-only and contains one Story. A status-only pack may refer to a Character
from an earlier pack, but runtime preview must confirm that stable binding.

For runtime work:

1. Validate the pack.
2. Call a preview tool and show conflicts, creates, updates, unchanged
   resources, warnings, and the opaque operation id.
3. Wait for explicit user confirmation.
4. Call the corresponding apply tool with the operation id. Do not add a
   `confirmed` input or switch to a different apply lane.
5. If the result is `applied_with_local_sync_pending`, retry the same apply
   operation after fixing the project path; do not repeat the database write.

Read `references/mcp-delivery.md` for modes, local Inspector transport,
ChatGPT Secure MCP Tunnel, relocation, rule-asset refresh, and recovery.

## Boundaries

- Do not write raw conversation transcripts.
- Do not directly edit MCP-owned revision files.
- Do not access RPG SQLite or import an `rpg_*` module from this workspace.
- Do not create Session, messages, media jobs, image binaries, or TTS jobs
  from a Story Pack.
- Do not delete runtime resources merely because a small pack omits them.
