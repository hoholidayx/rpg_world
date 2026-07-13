from __future__ import annotations

from pathlib import Path

import pytest

from llm_service.openai_provider import OpenAIProvider
from rpg_core import settings as settings_module
from llm_service import config as llm_config_module


def _write_settings(
    path: Path,
    *,
    agent_extra: str = "",
    profiles: str = "  local: {}\n",
    llm_extra: str = "",
    llm_profiles: str = "  local: {}\n  test: {}\n  prod: {}\n",
) -> None:
    path.write_text(
        f"""
base:
  agent:
    api_key_env: TEST_OPENAI_KEY
{agent_extra}
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
  providers:
    agent_chat:
      provider: openai
      openai:
        model: test-model
        api_key: null
        api_key_env: TEST_OPENAI_KEY
        base_url: null
        max_tokens: null
        temperature: null
    memory_embedding:
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
    memory_query_planner:
      provider: llama
      llama:
        model_path: data/models/planner.gguf
        n_ctx: 2048
        n_gpu_layers: 0
        temperature: 0.0
        max_tokens: 512
        request_timeout_ms: 60000
    memory_rerank:
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
        n_ctx: 4096
        n_gpu_layers: 0
        temperature: 0.0
        request_timeout_ms: 60000
        verbose: false
  biz:
    agent.main:
      kind: chat
      provider_key: agent_chat
    memory.embed:
      kind: embedding
      provider_key: memory_embedding
    memory.query_planner:
      kind: planner
      provider_key: memory_query_planner
    memory.rerank:
      kind: rerank
      provider_key: memory_rerank
      rerank_model_type: qwen3_logit
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
  providers:
    agent_chat:
      provider: openai
      openai:
        model: base-model
        api_key: null
        api_key_env: BASE_KEY
        base_url: null
        max_tokens: null
        temperature: null
  biz:
    agent.main:
      kind: chat
      provider_key: agent_chat
profiles:
  local: {}
  test: {}
  prod: {}
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.local.yaml").write_text(
        """
providers:
  agent_chat:
    openai:
      api_key: local-key
""",
        encoding="utf-8",
    )
    (tmp_path / "llm.test.yaml").write_text(
        """
providers:
  agent_chat:
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


def test_rp_module_settings_defaults(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    rp_modules = settings_module.Settings().rp_module_settings

    assert rp_modules.enabled is True
    assert rp_modules.dice.enabled is True
    assert rp_modules.dice.default_dc == 12
    assert rp_modules.narrative_outcome.enabled is True
    assert rp_modules.narrative_outcome.auto_adjudication_enabled is True
    assert rp_modules.narrative_outcome.default_weights.to_dict() == {
        "critical_success": 5,
        "success": 25,
        "success_with_cost": 40,
        "setback": 25,
        "critical_failure": 5,
    }


def test_rp_module_settings_read_yaml_values(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        agent_extra="",
    )
    original = cfg.read_text(encoding="utf-8")
    cfg.write_text(
        original.replace(
            "  memory:\n",
            """  rp_modules:
    enabled: false
    modules:
      dice:
        enabled: false
        default_dc: 15
        max_dice_count: 8
        max_die_sides: 100
      narrative_outcome:
        auto_adjudication_enabled: false
  memory:\n""",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    rp_modules = settings_module.Settings().rp_module_settings

    assert rp_modules.enabled is False
    assert rp_modules.dice.enabled is False
    assert rp_modules.dice.default_dc == 15
    assert rp_modules.dice.max_dice_count == 8
    assert rp_modules.dice.max_die_sides == 100
    assert rp_modules.narrative_outcome.auto_adjudication_enabled is False


def test_narrative_outcome_settings_read_canonical_weights(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    original = cfg.read_text(encoding="utf-8")
    cfg.write_text(
        original.replace(
            "  memory:\n",
            """  rp_modules:
    modules:
      narrative_outcome:
        enabled: true
        auto_adjudication_enabled: false
        default_weights:
          critical_success: 0
          success: 20
          success_with_cost: 50
          setback: 25
          critical_failure: 5
      dice:
        enabled: true
  memory:
""",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    outcome = settings_module.Settings().rp_module_settings.narrative_outcome

    assert outcome.auto_adjudication_enabled is False
    assert outcome.default_weights.to_dict() == {
        "critical_success": 0,
        "success": 20,
        "success_with_cost": 50,
        "setback": 25,
        "critical_failure": 5,
    }


def test_legacy_dice_auto_checks_key_is_rejected(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace(
            "  memory:\n",
            """  rp_modules:
    modules:
      dice:
        allow_auto_checks: true
  memory:
""",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match="allow_auto_checks is no longer supported"):
        settings_module.Settings()


def test_memory_settings_resolve_provider_pool_entries(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        """
base:
  agent:
    memory_sub_agent:
      enabled: true
  memory:
    enabled: true
    top_k: 5
  modules:
    telegram:
      enabled: false
      bots: []
profiles:
  local: {}
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
  providers:
    agent_chat:
      provider: openai
      openai:
        model: test-model
        api_key: null
        api_key_env: TEST_OPENAI_KEY
        base_url: null
        max_tokens: null
        temperature: null
    memory_embedding:
      provider: openai
      openai:
        model: embed-model
        api_key: null
        api_key_env: MEMORY_OPENAI_KEY
        base_url: https://memory.example
        max_tokens: null
        temperature: null
    memory_query_planner:
      provider: llama
      llama:
        model_path: data/models/planner.gguf
        n_ctx: 2048
        n_gpu_layers: 0
        temperature: 0.0
        max_tokens: 512
        request_timeout_ms: 60000
  biz:
    agent.main:
      kind: chat
      provider_key: agent_chat
    memory.embed:
      kind: embedding
      provider_key: memory_embedding
    memory.query_planner:
      kind: planner
      provider_key: memory_query_planner
profiles:
  local: {}
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


def test_context_window_reject_threshold_defaults_and_accepts_valid_ratio(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, agent_extra="    context_window_reject_threshold_ratio: 0.75\n")
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    assert settings_module.Settings().context_window_reject_threshold_ratio == 0.75

    _write_settings(cfg)
    assert settings_module.Settings().context_window_reject_threshold_ratio == 0.9


@pytest.mark.parametrize("value", ["0", "1.01", "true", "not-a-number"])
def test_context_window_reject_threshold_rejects_invalid_values(
    tmp_path: Path,
    monkeypatch,
    value: str,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        agent_extra=f"    context_window_reject_threshold_ratio: {value}\n",
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match="context_window_reject_threshold_ratio"):
        settings_module.Settings()


def test_scene_runtime_key_changes_default_off_and_accepts_boolean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    assert settings_module.Settings().scene_settings.allow_runtime_key_changes is False

    _write_settings(
        cfg,
        agent_extra=(
            "    scene:\n"
            "      allow_runtime_key_changes: true\n"
        ),
    )
    assert settings_module.Settings().scene_settings.allow_runtime_key_changes is True


@pytest.mark.parametrize(
    ("agent_extra", "message"),
    [
        ("    scene: []\n", "agent.scene must be a mapping"),
        (
            "    scene:\n      allow_runtime_key_changes: 'false'\n",
            "allow_runtime_key_changes must be a boolean",
        ),
        (
            "    scene:\n      allow_runtime_key_changes: 1\n",
            "allow_runtime_key_changes must be a boolean",
        ),
    ],
)
def test_scene_runtime_key_changes_rejects_malformed_config(
    tmp_path: Path,
    monkeypatch,
    agent_extra: str,
    message: str,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg, agent_extra=agent_extra)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match=message):
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
  providers:
    llama_chat:
      provider: llama
      llama:
        model_path: data/models/llama-main.gguf
    memory_embedding:
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
  biz:
    agent.main:
      kind: chat
      provider_key: llama_chat
    memory.embed:
      kind: embedding
      provider_key: memory_embedding
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


def test_agent_model_and_biz_output_overrides_use_provider_pool(tmp_path: Path, monkeypatch) -> None:
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
  providers:
    shared_chat:
      provider: openai
      openai:
        model: shared-model
        api_key: shared-key
        base_url: https://shared.example
        max_tokens: 321
        temperature: 0.2
    memory_embedding:
      provider: llama
      llama:
        model_path: data/models/Qwen3-Embedding-0.6B-f16.gguf
        n_ctx: 32768
        n_gpu_layers: 0
        n_threads: 4
        verbose: false
        request_timeout_ms: 60000
  biz:
    agent.main:
      kind: chat
      provider_key: shared_chat
      max_tokens: 654
      temperature: 0.9
    memory.embed:
      kind: embedding
      provider_key: memory_embedding
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
    assert local_settings.agent_base_url == "https://shared.example"
    assert local_settings.agent_max_tokens == 654
    assert local_settings.agent_temperature == 0.9


def test_get_openai_api_key_uses_selected_provider(tmp_path: Path, monkeypatch) -> None:
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
  providers:
    shared_chat:
      provider: openai
      openai:
        model: shared-model
        api_key: shared-key
  biz:
    agent.main:
      kind: chat
      provider_key: shared_chat
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


def test_openai_provider_uses_constructor_api_key(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    class DummyClient:
        def __init__(self, *, api_key=None, base_url=None, http_client=None) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client

    monkeypatch.setattr("llm_service.openai_provider.AsyncOpenAI", DummyClient)

    OpenAIProvider(model="test-model")
    assert captured["api_key"] is None

    OpenAIProvider(model="test-model", api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"


def test_openai_provider_stores_constructor_values_when_client_injected() -> None:
    dummy_client = object()

    provider = OpenAIProvider(
        model="test-model",
        api_key="explicit-key",
        base_url="https://example.test/v1",
        http_client=object(),
        client=dummy_client,  # type: ignore[arg-type]
    )

    assert provider._client is dummy_client
    assert provider._api_key == "explicit-key"
    assert provider._base_url == "https://example.test/v1"
