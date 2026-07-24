# MCP delivery and recovery

## Contents

- Command and modes
- Codex workspace connection
- ChatGPT App connection
- Streamable HTTP Inspector
- Confirmation model
- Authoring rule asset refresh
- Cross-store recovery
- Relocation

## Command and modes

RPG World installs one command:

```text
rpg-world-mcp --mode design|runtime|all
```

- `design` reads and writes only DesignProject files. It does not initialize
  RPG modules or SQLite.
- `runtime` reads and writes only RPG World runtime data. A project root is
  optional unless a relative Story Pack or local integration report is used.
- `all` exposes both groups plus compare, preview-sync, apply-sync, and
  reconcile tools.

The default transport is stdio.

## Codex workspace connection

`.codex/config.toml` refers only to the installed command and passes
`--project-root .`. Install the command before opening this directory as a
standalone Codex workspace. It intentionally defaults to `--mode design`, so
ordinary authoring does not initialize the RPG database. Before runtime
compare, preview, apply, or reconcile work, change that argument to
`--mode all` and restart the MCP connection; switch back to `design` afterward
if runtime access is no longer needed. Do not register both modes
simultaneously because their design tool names overlap. Do not replace the
command with an absolute path to the RPG World repository.

## ChatGPT App connection

ChatGPT requires an HTTPS-facing MCP connection. Use OpenAI Secure MCP Tunnel
to forward to the same local stdio command, with this directory as the Tunnel
working directory/project root. Select the developer App in each conversation
where the tools are needed.

The App and model cannot automatically capture or read the complete ChatGPT
conversation history. Durable state exists only after explicit design tool
calls. Reconnect and call `story_design_get_resume_context` to resume.

## Streamable HTTP Inspector

For local inspection only:

```text
rpg-world-mcp --mode all --project-root . \
  --transport streamable-http --host 127.0.0.1 --port 8765
```

The command rejects non-loopback HTTP hosts. Use the Tunnel instead of opening
the Inspector port publicly.

## Confirmation model

Runtime preview tools create an opaque operation ID and a persistent plan.
Their apply tools accept that operation ID only. They intentionally do not
accept `confirmed=true`; the user confirms in the conversation before the
model calls the destructive apply tool. Each runtime operation ID is tied to
its preview lane (`story_pack`, `changes`, or `runtime_sync`) and must use the
matching apply tool.

The local authoring-rule refresh preview is read-only: its opaque ID is bound
to the exact current and expected asset digests. Apply recomputes those
digests and rejects a stale ID, so no preview ledger or design revision is
needed.

## Authoring rule asset refresh

`authoringRulesVersion` evolves independently from the v2 Story Pack
contract. When an updated `rpg-world-mcp` reports stale rule assets:

1. Call `story_design_preview_authoring_rules_refresh`.
2. Review every create/update path and the protected-path list.
3. Ask for explicit user confirmation.
4. Call `story_design_apply_authoring_rules_refresh` with only the returned
   operation ID.
5. Run `story_design_doctor`.

The apply call may update only generated Schema, the machine-readable rule
catalog, the workspace Skill, generated field references, and their manifest
digests. It must leave `design/current.json`, revisions, checkpoints, Story
Packs, and runtime integration files byte-identical. v1 DesignProjects are
rejected before any write; there is no conversion path.

## Cross-store recovery

An apply commits the RPG database transaction first. It then updates
`integrations/rpg-world.json` and writes a report under `reports/`.

If the file update fails, the operation becomes
`applied_with_local_sync_pending`. Call the same apply tool again with the
same operation ID and a valid project root. The binding/audit ledger prevents
the database write from running twice.

## Relocation

Move this directory as one unit. Project data contains only relative paths.
After moving:

1. Open the new directory as the Codex workspace.
2. Ensure `rpg-world-mcp` remains installed on `PATH`.
3. Update the Secure MCP Tunnel working directory/project root.
4. Run `story_design_doctor`.

No Story design or revision path needs rewriting.
