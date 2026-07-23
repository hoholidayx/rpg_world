# MCP delivery and recovery

## Contents

- Command and modes
- Codex workspace connection
- ChatGPT App connection
- Streamable HTTP Inspector
- Confirmation model
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

Preview tools create an opaque operation ID and a persistent plan. Apply tools
accept that operation ID only. They intentionally do not accept
`confirmed=true`; the user confirms in the conversation before the model calls
the destructive apply tool. Each operation ID is tied to its preview lane
(`story_pack`, `changes`, or `runtime_sync`) and must use the matching apply
tool.

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
