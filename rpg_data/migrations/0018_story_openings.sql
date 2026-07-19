CREATE TABLE IF NOT EXISTS rpg_story_openings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    story_id INTEGER NOT NULL,
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    message TEXT NOT NULL CHECK (length(trim(message)) > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id, workspace_id) REFERENCES rpg_stories(id, workspace_id) ON DELETE CASCADE,
    UNIQUE (story_id, title)
);

CREATE INDEX IF NOT EXISTS idx_rpg_story_openings_story
ON rpg_story_openings(story_id, sort_order, id);

INSERT OR IGNORE INTO rpg_story_openings (
    workspace_id,
    story_id,
    title,
    message,
    sort_order
)
SELECT
    workspace_id,
    id,
    '默认开局',
    trim(first_message),
    0
FROM rpg_stories
WHERE length(trim(first_message)) > 0;

ALTER TABLE rpg_session_profiles
ADD COLUMN story_opening_id INTEGER
REFERENCES rpg_story_openings(id) ON DELETE SET NULL;

UPDATE rpg_session_profiles
SET story_opening_id = (
    SELECT opening.id
    FROM rpg_sessions AS session
    JOIN rpg_story_openings AS opening
      ON opening.story_id = session.story_id
    WHERE session.id = rpg_session_profiles.session_id
    ORDER BY opening.sort_order, opening.id
    LIMIT 1
)
WHERE story_opening_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_rpg_session_profiles_story_opening
ON rpg_session_profiles(story_opening_id);
