CREATE TABLE rpg_media_library_items_next (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL CHECK (scope IN ('story', 'workspace')),
    story_id INTEGER,
    media_type TEXT NOT NULL DEFAULT 'background'
        CHECK (media_type IN (
            'background',
            'avatar',
            'character_sprite',
            'scene_illustration',
            'map',
            'item',
            'ui',
            'reference',
            'other'
        )),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES rpg_workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES rpg_media_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (story_id) REFERENCES rpg_stories(id) ON DELETE CASCADE,
    CHECK (
        (scope = 'story' AND story_id IS NOT NULL)
        OR (scope = 'workspace' AND story_id IS NULL)
    ),
    CHECK (scope = 'story' OR is_default = 0),
    CHECK (media_type = 'background' OR is_default = 0)
);

INSERT INTO rpg_media_library_items_next (
    id,
    workspace_id,
    asset_id,
    scope,
    story_id,
    media_type,
    title,
    description,
    is_default,
    version,
    created_at,
    updated_at
)
SELECT
    id,
    workspace_id,
    asset_id,
    CASE scope
        WHEN 'workspace_fallback' THEN 'workspace'
        ELSE scope
    END,
    story_id,
    'background',
    title,
    description,
    is_default,
    version,
    created_at,
    updated_at
FROM rpg_media_library_items;

CREATE TABLE rpg_media_library_item_tags_next (
    item_id TEXT NOT NULL,
    tag TEXT NOT NULL CHECK (length(trim(tag)) > 0),
    normalized_tag TEXT GENERATED ALWAYS AS (lower(trim(tag))) STORED,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id, tag),
    UNIQUE (item_id, normalized_tag),
    FOREIGN KEY (item_id) REFERENCES rpg_media_library_items_next(id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO rpg_media_library_item_tags_next (
    item_id,
    tag,
    created_at
)
SELECT
    item_id,
    trim(tag),
    created_at
FROM rpg_media_library_item_tags;

DROP TABLE rpg_media_library_item_tags;
DROP TABLE rpg_media_library_items;

ALTER TABLE rpg_media_library_items_next RENAME TO rpg_media_library_items;
ALTER TABLE rpg_media_library_item_tags_next RENAME TO rpg_media_library_item_tags;

CREATE UNIQUE INDEX idx_rpg_media_library_story_default
ON rpg_media_library_items(story_id)
WHERE scope = 'story' AND media_type = 'background' AND is_default = 1;

CREATE INDEX idx_rpg_media_library_workspace_taxonomy
ON rpg_media_library_items(workspace_id, media_type, scope, story_id, updated_at, id);

CREATE INDEX idx_rpg_media_library_tags_normalized
ON rpg_media_library_item_tags(normalized_tag, item_id);
