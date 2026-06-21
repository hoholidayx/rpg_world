from __future__ import annotations

from pathlib import Path

import pytest

from rpg_world.rpg_core.llm.openai_provider import OpenAIProvider
from rpg_world.rpg_core import settings as settings_module
from rpg_world.rpg_core.llm import config as llm_config_module


def _write_settings(
    path: Path,
    *,
    agent_extra: str = "",
    profiles: str = "  local: {}\n",
    llm_extra: str = "",
    llm_profiles: str = """  local:\n    file: llm.local.yaml\n  test:\n    file: llm.test.yaml\n  prod:\n    file: llm.prod.yaml\n""",
) -> None:
    path.write_text(
        f"""
base:
  agent:
    api_key_env: TEST_OPENAI_KEY
{agent_extra}
  data:
    character_path: character
    lorebook_path: lorebook
  memory:
    enabled: false
    rerank_score_weight: 0.70
  modules:
    telegram:
      enabled: false
      bots: []
profiles:
{profiles}
""",
        encoding="utf-8",
    )
    llm_path = path.parent / "llm.yaml"
    llm_path.write_text(
        f"""
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.main:
      kind: chat
      provider: openai
      openai:
        model: test-model
        api_key: null
        api_key_env: TEST_OPENAI_KEY
        base_url: null
        max_tokens: null
        temperature: null
    memory.embed:
      kind: embedding
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
    memory.query_planner:
      kind: planner
      provider: llama
      llama:
        model_path: data/models/planner.gguf
        n_ctx: 2048
        n_gpu_layers: 0
        temperature: 0.0
        max_tokens: 512
        request_timeout_ms: 60000
    memory.rerank:
      kind: rerank
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
        n_ctx: 4096
        n_gpu_layers: 0
        temperature: 0.0
        request_timeout_ms: 60000
        verbose: false
{llm_extra}
profiles:
{llm_profiles}
""",
        encoding="utf-8",
    )


def test_get_openai_api_key_priority(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, agent_extra="    api_key: yaml-key\n")
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    monkeypatch.setenv("TEST_OPENAI_KEY", "env-key")

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key("explicit-key") == "explicit-key"
    assert local_settings.get_openai_api_key(None) == "yaml-key"


def test_get_openai_api_key_reads_configured_env(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    monkeypatch.setenv("TEST_OPENAI_KEY", "env-key")
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-key")

    local_settings = settings_module.Settings()

    assert local_settings.get_openai_api_key(None) == "env-key"


def test_llm_profile_files_override_base_config(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        """
base:
  data:
    character_path: character
    lorebook_path: lorebook
  memory:
    enabled: false
  modules:
    telegram:
      enabled: false
      bots: []
profiles:
  local: {}
  test: {}
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.yaml").write_text(
        """
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.main:
      kind: chat
      provider: openai
      openai:
        model: base-model
        api_key: null
        api_key_env: BASE_KEY
        base_url: null
        max_tokens: null
        temperature: null
profiles:
  local:
    file: llm.local.yaml
  test:
    file: llm.test.yaml
  prod:
    file: llm.prod.yaml
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.local.yaml").write_text(
        """
biz:
  agent.main:
    openai:
      api_key: local-key
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.test.yaml").write_text(
        """
biz:
  agent.main:
    openai:
      api_key_env: TEST_KEY
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    local_settings = settings_module.Settings()
    assert local_settings.agent_model == "base-model"
    assert local_settings.get_openai_api_key(None) == "local-key"

    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")
    monkeypatch.setenv("TEST_KEY", "test-key")
    assert settings_module.Settings().get_openai_api_key(None) == "test-key"


def test_resolve_openai_api_key_can_skip_agent_fallback(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, agent_extra="    api_key: yaml-key\n")
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    monkeypatch.setenv("MEMORY_OPENAI_KEY", "memory-env-key")

    local_settings = settings_module.Settings()

    assert local_settings.resolve_openai_api_key(
        explicit=None,
        explicit_env="MEMORY_OPENAI_KEY",
        fallback_to_agent=False,
    ) == "memory-env-key"
    assert local_settings.resolve_openai_api_key(
        explicit=None,
        explicit_env=None,
        fallback_to_agent=False,
    ) is None


def test_memory_settings_merge_shared_openai_and_resolve_nested_llama_paths(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        """
base:
  agent:
    memory_sub_agent:
      enabled: true
  data:
    character_path: character
    lorebook_path: lorebook
  memory:
    enabled: true
    top_k: 5
  modules:
    telegram:
      enabled: false
      bots: []
profiles:
  local:
    file: llm.local.yaml
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.yaml").write_text(
        """
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.main:
      kind: chat
      provider: openai
      openai:
        model: test-model
        api_key: null
        api_key_env: TEST_OPENAI_KEY
        base_url: null
        max_tokens: null
        temperature: null
    memory.embed:
      kind: embedding
      provider: openai
      openai:
        model: embed-model
        api_key: null
        api_key_env: MEMORY_OPENAI_KEY
        base_url: https://memory.example
        max_tokens: null
        temperature: null
    memory.query_planner:
      kind: planner
      provider: llama
      llama:
        model_path: data/models/planner.gguf
        n_ctx: 2048
        n_gpu_layers: 0
        temperature: 0.0
        max_tokens: 512
        request_timeout_ms: 60000
profiles:
  local:
    file: llm.local.yaml
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    local_settings = settings_module.Settings()
    mem = local_settings.memory_settings

    assert mem.embedding_provider.provider == "openai"
    assert mem.query_planner_provider.provider == "llama"


def test_profile_must_be_set_before_settings_construction(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        profiles="""
  local:
    agent:
      max_tool_call_limit: 1
  prod:
    agent:
      max_tool_call_limit: 2
""",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    local_settings = settings_module.Settings()

    monkeypatch.setenv("RPG_WORLD_PROFILE", "prod")

    assert local_settings.max_tool_calls == 1
    assert settings_module.Settings().max_tool_calls == 2


def test_missing_profile_raises_value_error(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "missing")

    with pytest.raises(ValueError, match="missing"):
        settings_module.Settings()


def test_agent_model_is_required(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    assert settings_module.Settings().agent_model == "test-model"


def test_agent_model_uses_llama_model_path_when_llm_provider_is_llama(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    llm_path = tmp_path / "llm.yaml"
    llm_path.write_text(
        """
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.main:
      kind: chat
      provider: llama
      llama:
        model_path: data/models/llama-main.gguf
    memory.embed:
      kind: embedding
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
profiles:
  local: {}
  test: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", llm_path)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    assert settings_module.Settings().agent_model == "data/models/llama-main.gguf"


def test_agent_model_and_openai_overrides_follow_shared_chain(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    llm_path = tmp_path / "llm.yaml"
    llm_path.write_text(
        """
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.shared:
      kind: chat
      provider: openai
      openai:
        model: shared-model
        api_key: shared-key
        base_url: https://shared.example
        max_tokens: 321
        temperature: 0.2
    agent.main:
      kind: chat
      provider: shared
      shared_from: agent.shared
      openai:
        api_key: child-key
        base_url: https://child.example
        temperature: 0.9
    memory.embed:
      kind: embedding
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
profiles:
  local: {}
  test: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", llm_path)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    local_settings = settings_module.Settings()
    assert local_settings.agent_model == "shared-model"
    assert local_settings.agent_base_url == "https://child.example"
    assert local_settings.agent_max_tokens == 321
    assert local_settings.agent_temperature == 0.9


def test_get_openai_api_key_follows_shared_biz_chain(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        agent_extra="    api_key_env: DEFAULT_KEY\n",
    )
    llm_path = tmp_path / "llm.yaml"
    llm_path.write_text(
        """
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
    agent.shared:
      kind: chat
      provider: openai
      openai:
        model: shared-model
        api_key: shared-key
    agent.main:
      kind: chat
      provider: shared
      shared_from: agent.shared
profiles:
  local: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", llm_path)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    assert settings_module.Settings().get_openai_api_key() == "shared-key"


def test_agent_llm_model_empty_raises(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    llm_path = tmp_path / "llm.yaml"
    llm_path.write_text(
        llm_path.read_text(encoding="utf-8").replace("model: test-model", "model: ''"),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", llm_path)
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match="agent.main.openai.model is required"):
        settings_module.Settings()


def test_openai_provider_uses_settings_api_key(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    class DummyClient:
        def __init__(self, *, api_key=None, base_url=None, http_client=None) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client

    monkeypatch.setattr("rpg_world.rpg_core.llm.openai_provider.AsyncOpenAI", DummyClient)
    monkeypatch.setattr(
        "rpg_world.rpg_core.llm.openai_provider.settings.get_openai_api_key",
        lambda explicit=None: explicit or "resolved-from-settings",
    )

    OpenAIProvider(model="test-model")
    assert captured["api_key"] == "resolved-from-settings"

    OpenAIProvider(model="test-model", api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"


def test_openai_provider_stores_resolved_settings_when_client_injected(monkeypatch) -> None:
    dummy_client = object()
    monkeypatch.setattr(
        "rpg_world.rpg_core.llm.openai_provider.settings.get_openai_api_key",
        lambda explicit=None: explicit or "resolved-from-settings",
    )

    provider = OpenAIProvider(
        model="test-model",
        base_url="https://example.test/v1",
        http_client=object(),
        client=dummy_client,  # type: ignore[arg-type]
    )

    assert provider._client is dummy_client
    assert provider._api_key == "resolved-from-settings"
    assert provider._base_url == "https://example.test/v1"
