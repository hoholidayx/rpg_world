ALTER TABLE rpg_stories
ADD COLUMN main_llm_provider_key TEXT;

ALTER TABLE rpg_session_profiles
ADD COLUMN main_llm_provider_key TEXT;
