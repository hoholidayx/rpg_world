-- Normalize per-fact Story Memory source identity into immutable Evidence rows.
-- message_id deliberately has no foreign key so edited/deleted history can be
-- detected without erasing the audit identity, matching Persistent Memory.
CREATE TABLE rpg_session_story_memory_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_memory_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL CHECK (message_id > 0),
    turn_id INTEGER NOT NULL CHECK (turn_id > 0),
    message_version INTEGER NOT NULL CHECK (message_version > 0),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (story_memory_id) REFERENCES rpg_session_story_memories(id) ON DELETE CASCADE,
    UNIQUE (story_memory_id, message_id)
);

CREATE INDEX idx_rpg_session_story_memory_evidence_message
    ON rpg_session_story_memory_evidence(message_id, message_version, content_hash);

-- Existing manifests were validated at the write boundary. The additional SQL
-- guards make migration tolerant of a manually corrupted runtime database.
INSERT OR IGNORE INTO rpg_session_story_memory_evidence (
    story_memory_id,
    message_id,
    turn_id,
    message_version,
    content_hash
)
SELECT
    memory.id,
    CAST(json_extract(item.value, '$.messageId') AS INTEGER),
    CAST(json_extract(item.value, '$.turnId') AS INTEGER),
    CAST(json_extract(item.value, '$.messageVersion') AS INTEGER),
    lower(json_extract(item.value, '$.contentHash'))
FROM rpg_session_story_memories AS memory
JOIN json_each(
    CASE
        WHEN json_valid(memory.source_messages_manifest_json) THEN
            CASE
                WHEN json_type(memory.source_messages_manifest_json) = 'array'
                THEN memory.source_messages_manifest_json
                ELSE '[]'
            END
        ELSE '[]'
    END
) AS item
WHERE json_type(item.value) = 'object'
  AND json_type(item.value, '$.messageId') = 'integer'
  AND json_extract(item.value, '$.messageId') > 0
  AND json_type(item.value, '$.turnId') = 'integer'
  AND json_extract(item.value, '$.turnId') > 0
  AND json_type(item.value, '$.messageVersion') = 'integer'
  AND json_extract(item.value, '$.messageVersion') > 0
  AND json_type(item.value, '$.contentHash') = 'text'
  AND length(json_extract(item.value, '$.contentHash')) = 64
  AND lower(json_extract(item.value, '$.contentHash')) NOT GLOB '*[^0-9a-f]*';

ALTER TABLE rpg_session_story_memories
    DROP COLUMN source_messages_manifest_json;
