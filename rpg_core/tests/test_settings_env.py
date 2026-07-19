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


def test_core_settings_do_not_read_llm_service_config(tmp_path: Path, monkeypatch) -> None:
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
    (tmp_path / "llm.yaml").write_text("this is not valid: [", encoding="utf-8")
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    local_settings = settings_module.Settings()
    mem = local_settings.memory_settings

    assert mem.enabled is True
    assert mem.top_k == 5
    assert not hasattr(mem, "embedding_provider")


@pytest.mark.parametrize("profile", ["local", "test", "prod"])
def test_repo_profiles_disable_online_memory_rag(monkeypatch, profile: str) -> None:
    monkeypatch.setenv("RPG_WORLD_PROFILE", profile)

    memory = settings_module.Settings().memory_settings

    assert memory.enabled is False
    assert memory.query_planner_enabled is False
    assert memory.rerank_enabled is False


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


def test_story_memory_batch_turns_is_typed_and_defaults_to_ten(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(cfg)
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    defaults = settings_module.Settings().memory_story_settings
    assert defaults.batch_turns == 10
    assert defaults.max_batch_chars == 32_000

    _write_settings(
        cfg,
        agent_extra=(
            "    memory_sub_agent:\n"
            "      story:\n"
            "        trigger_rounds: 0\n"
            "        max_items: 8\n"
            "        batch_turns: 7\n"
            "        max_batch_chars: 12345\n"
        ),
    )
    configured = settings_module.Settings()
    assert configured.memory_story_settings.batch_turns == 7
    assert configured.memory_story_batch_turns == 7
    assert configured.memory_story_max_batch_chars == 12_345


@pytest.mark.parametrize("value", [0, -1, True, "10"])
def test_story_memory_batch_turns_rejects_invalid_values(
    tmp_path: Path,
    monkeypatch,
    value: object,
) -> None:
    cfg = tmp_path / "settings.yaml"
    rendered = str(value).lower() if isinstance(value, bool) else repr(value)
    _write_settings(
        cfg,
        agent_extra=(
            "    memory_sub_agent:\n"
            "      story:\n"
            f"        batch_turns: {rendered}\n"
        ),
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match="story.batch_turns must be a positive integer"):
        settings_module.Settings()


def test_summary_memory_settings_are_typed(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        agent_extra=(
            "    memory_sub_agent:\n"
            "      summary:\n"
            "        compress_batch_size: 7\n"
            "        keep_rounds: 0\n"
            "        compression_enabled: false\n"
            "        max_batch_chars: 12345\n"
        ),
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    configured = settings_module.Settings()

    assert configured.memory_compress_batch_size == 7
    assert configured.memory_keep_rounds == 0
    assert configured.memory_compression_enabled is False
    assert configured.memory_summary_max_batch_chars == 12_345


@pytest.mark.parametrize(
    ("key", "rendered", "message"),
    [
        ("compress_batch_size", "0", "compress_batch_size must be a positive integer"),
        ("keep_rounds", "true", "keep_rounds must be a non-negative integer"),
        ("compression_enabled", "1", "compression_enabled must be a boolean"),
        ("max_batch_chars", "'32000'", "max_batch_chars must be a positive integer"),
    ],
)
def test_summary_memory_settings_reject_invalid_values(
    tmp_path: Path,
    monkeypatch,
    key: str,
    rendered: str,
    message: str,
) -> None:
    cfg = tmp_path / "settings.yaml"
    _write_settings(
        cfg,
        agent_extra=(
            "    memory_sub_agent:\n"
            "      summary:\n"
            f"        {key}: {rendered}\n"
        ),
    )
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(llm_config_module, "_LLM_SETTINGS_PATH", tmp_path / "llm.yaml")
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")

    with pytest.raises(ValueError, match=message):
        settings_module.Settings()
