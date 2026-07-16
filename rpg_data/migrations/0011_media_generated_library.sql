WITH generated_assets AS (
    SELECT
        asset.id AS asset_id,
        asset.workspace_id AS workspace_id,
        session.story_id AS story_id,
        asset.created_at AS created_at,
        asset.updated_at AS updated_at,
        CASE
            WHEN json_valid(asset.visual_brief_json)
            THEN trim(CAST(COALESCE(
                json_extract(asset.visual_brief_json, '$.sceneDescription'),
                ''
            ) AS TEXT))
            ELSE ''
        END AS scene_description
    FROM rpg_media_assets AS asset
    JOIN rpg_session_media_gallery_items AS gallery
      ON gallery.asset_id = asset.id
    JOIN rpg_sessions AS session
      ON session.id = gallery.session_id
    LEFT JOIN rpg_media_library_items AS library_item
      ON library_item.asset_id = asset.id
    WHERE asset.origin_kind = 'generated'
      AND library_item.id IS NULL
)
INSERT INTO rpg_media_library_items (
    id,
    workspace_id,
    asset_id,
    scope,
    story_id,
    title,
    description,
    is_default,
    version,
    created_at,
    updated_at
)
SELECT
    lower(hex(randomblob(16))),
    workspace_id,
    asset_id,
    'story',
    story_id,
    CASE
        WHEN length(scene_description) > 0
        THEN substr(scene_description, 1, 96)
        ELSE 'Session generated image'
    END,
    CASE
        WHEN length(scene_description) > 0
        THEN scene_description
        ELSE 'Image generated from a committed Session turn.'
    END,
    0,
    1,
    created_at,
    updated_at
FROM generated_assets;

INSERT OR IGNORE INTO rpg_media_library_item_tags (item_id, tag, created_at)
SELECT id, 'generated', created_at
FROM rpg_media_library_items
WHERE asset_id IN (
    SELECT id
    FROM rpg_media_assets
    WHERE origin_kind = 'generated'
);
