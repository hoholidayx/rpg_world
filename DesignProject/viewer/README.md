# Story Design Viewer

This directory contains the dependency-free, read-only viewer for the portable
DesignProject.

Start it from the DesignProject root:

```text
python3 viewer/serve.py
```

Then open `http://127.0.0.1:8787/`. Pass `--open` to open the default browser
after startup or `--port PORT` to select another loopback port.

The viewer follows `design-project.json.currentRevision`, renders the current
and immutable historical revisions, compares revisions, describes the Story
Design and Story Pack schemas, and lists generated Story Packs. It uses a local
SSE connection to refresh when the manifest advances.

The server exposes only `GET` and `HEAD`. It must never edit
`design/current.json`, `design/revisions/`, checkpoints, schemas, Story Packs,
or integration state. Confirmed design changes continue to use
`story_design_patch`; runtime changes continue to use the separate
preview/confirmation/apply workflow.
