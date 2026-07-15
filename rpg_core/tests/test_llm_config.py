from __future__ import annotations

from pathlib import Path

import pytest

from llm_service.config import (
    list_provider_options,
    reload_llm_settings,
    resolve_agent_defaults,
    resolve_biz_config,
    resolve_context_window,
    resolve_llm_config,
)
from llm_service.keys import (
    AGENT_MAIN_BIZ_KEY,
    LLMConfigKey,
    MEMORY_RERANK_BIZ_KEY,
    RERANK_MODEL_TYPE_QWEN3_LOGIT,
)


def _write_llm_config(
    path: Path,
    *,
    providers: str,
    biz: str,
) -> None:
    path.write_text(
        f"""
base:
  providers:
{providers}
  biz:
{biz}
profiles:
  local: {{}}
  test: {{}}
""",
        encoding="utf-8",
    )


def _use_llm(path: Path, monkeypatch: pytest.MonkeyPatch, profile: str = "local") -> None:
    monkeypatch.setattr("llm_service.config._LLM_SETTINGS_PATH", path)
    monkeypatch.setenv("RPG_WORLD_PROFILE", profile)
    reload_llm_settings()


def test_resolve_biz_config_uses_provider_pool_for_multiple_biz(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    shared_chat:
      provider: openai
      openai:
        model: base-model
        api_key: base-key
        context_window: 64000
        max_tokens: 777
        temperature: 0.1
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: shared_chat
    agent.status_sub_agent:
      kind: chat
      provider_key: shared_chat
""",
    )
    _use_llm(path, monkeypatch)

    main = resolve_biz_config(AGENT_MAIN_BIZ_KEY)
    status = resolve_biz_config("agent.status_sub_agent")

    assert main.provider_key == status.provider_key == "shared_chat"
    assert main.provider == status.provider == "openai"
    assert main.openai_model == status.openai_model == "base-model"
    assert main.openai_api_key == status.openai_api_key == "base-key"
    assert resolve_context_window(AGENT_MAIN_BIZ_KEY) == 64000


def test_biz_overrides_openai_effective_parameters(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
        context_window: 64000
        max_tokens: 256
        temperature: 0.1
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
      context_window: 128000
      max_tokens: 1024
      temperature: 0.7
""",
    )
    _use_llm(path, monkeypatch)

    cfg = resolve_biz_config(AGENT_MAIN_BIZ_KEY)
    assert cfg.openai_context_window == 128000
    assert cfg.openai_max_tokens == 1024
    assert cfg.openai_temperature == 0.7
    assert cfg.openai_cfg[LLMConfigKey.CONTEXT_WINDOW] == 128000


def test_biz_context_window_maps_to_llama_n_ctx(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    local_chat:
      provider: llama
      llama:
        model_path: data/models/chat.gguf
        n_ctx: 32768
        max_tokens: 256
        temperature: 0.1
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: local_chat
      context_window: 65536
      max_tokens: 768
      temperature: 0.4
""",
    )
    _use_llm(path, monkeypatch)

    cfg = resolve_biz_config(AGENT_MAIN_BIZ_KEY)
    assert cfg.llama_n_ctx == 65536
    assert cfg.llama_max_tokens == 768
    assert cfg.llama_temperature == 0.4
    assert cfg.llama_cfg[LLMConfigKey.N_CTX] == 65536
    assert resolve_context_window(AGENT_MAIN_BIZ_KEY) == 65536


def test_resolve_context_window_returns_none_when_unconfigured(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
""",
    )
    _use_llm(path, monkeypatch)

    assert resolve_context_window(AGENT_MAIN_BIZ_KEY) is None


def test_profile_override_updates_provider_pool(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
        api_key: base-key
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
""",
    )
    (tmp_path / "llm.local.yaml").write_text(
        """
providers:
  chat:
    openai:
      api_key: local-key
""",
        encoding="utf-8",
    )
    _use_llm(path, monkeypatch)

    assert resolve_biz_config(AGENT_MAIN_BIZ_KEY).openai_api_key == "local-key"


@pytest.mark.parametrize("provider_key_line", ["", '      provider_key: ""\n'])
def test_resolve_biz_config_requires_provider_key(
    tmp_path: Path,
    monkeypatch,
    provider_key_line: str,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz=f"""
    agent.main:
      kind: chat
{provider_key_line}""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="agent.main.provider_key"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_rejects_unknown_provider_key(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: missing
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="provider config not found: missing"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_rejects_non_mapping_biz_section(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    path.write_text(
        """
base:
  providers: {}
  biz: invalid
profiles:
  local: {}
""",
        encoding="utf-8",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="llm biz must be a mapping"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


@pytest.mark.parametrize("provider_line", ["", '      provider: ""\n', "      provider: unknown\n"])
def test_resolve_biz_config_requires_supported_provider(
    tmp_path: Path,
    monkeypatch,
    provider_line: str,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers=f"""
    chat:
{provider_line}      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match=r"providers\.chat\.provider"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


@pytest.mark.parametrize("openai_config", ["", "      openai: invalid\n"])
def test_resolve_biz_config_requires_provider_backend_mapping(
    tmp_path: Path,
    monkeypatch,
    openai_config: str,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers=f"""
    chat:
      provider: openai
{openai_config}""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match=r"providers\.chat\.openai must be a mapping"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_rejects_unsupported_biz_fields(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
      provider: openai
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="unsupported fields: provider"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


@pytest.mark.parametrize("kind", ["", "chaty"])
def test_resolve_biz_config_rejects_invalid_kind(tmp_path: Path, monkeypatch, kind: str) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz=f"""
    agent.main:
      kind: {kind!r}
      provider_key: chat
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="agent.main.kind"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_rejects_invalid_override_value(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
      temperature: abc
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="temperature"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).openai_temperature


def test_resolve_biz_config_requires_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    rerank:
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
""",
        biz="""
    memory.rerank:
      kind: rerank
      provider_key: rerank
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="memory.rerank.rerank_model_type"):
        resolve_biz_config(MEMORY_RERANK_BIZ_KEY)


def test_resolve_biz_config_accepts_explicit_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    rerank:
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
""",
        biz="""
    memory.rerank:
      kind: rerank
      provider_key: rerank
      rerank_model_type: qwen3_logit
""",
    )
    _use_llm(path, monkeypatch)

    cfg = resolve_biz_config(MEMORY_RERANK_BIZ_KEY)
    assert cfg.rerank_model_type == RERANK_MODEL_TYPE_QWEN3_LOGIT


def test_resolve_biz_config_rejects_unknown_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    rerank:
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
""",
        biz="""
    memory.rerank:
      kind: rerank
      provider_key: rerank
      rerank_model_type: unknown
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="memory.rerank.rerank_model_type"):
        resolve_biz_config(MEMORY_RERANK_BIZ_KEY)


def test_resolved_models_include_provider_key(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    chat:
      provider: openai
      openai:
        model: test-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: chat
""",
    )
    _use_llm(path, monkeypatch)

    assert resolve_llm_config(AGENT_MAIN_BIZ_KEY).provider_key == "chat"
    assert resolve_agent_defaults(AGENT_MAIN_BIZ_KEY).provider_key == "chat"


def test_provider_options_are_ordered_selectable_and_safe_to_expose(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    remote_chat:
      provider: openai
      openai:
        model: remote-model
        api_key: secret-key
        api_key_env: SECRET_ENV
        base_url: https://llm.example
        context_window: 64000
    local_chat:
      provider: llama
      llama:
        model_path: C:\\private\\models\\local-chat.gguf
        n_ctx: 8192
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: remote_chat
      provider_option_keys:
        - local_chat
        - remote_chat
""",
    )
    _use_llm(path, monkeypatch)

    selected = resolve_biz_config(AGENT_MAIN_BIZ_KEY, provider_key="local_chat")
    options = list_provider_options(AGENT_MAIN_BIZ_KEY)

    assert selected.provider_key == "local_chat"
    assert selected.provider == "llama"
    assert resolve_context_window(AGENT_MAIN_BIZ_KEY, provider_key="local_chat") == 8192
    assert resolve_llm_config(
        AGENT_MAIN_BIZ_KEY,
        provider_key="local_chat",
    ).provider_key == "local_chat"
    assert resolve_agent_defaults(
        AGENT_MAIN_BIZ_KEY,
        provider_key="local_chat",
    ).provider_key == "local_chat"
    assert [option.provider_key for option in options] == ["local_chat", "remote_chat"]
    assert options[0].model == "local-chat.gguf"
    assert options[0].context_window == 8192
    assert options[1].model == "remote-model"
    assert options[1].context_window == 64000
    assert not hasattr(options[1], "api_key")
    assert not hasattr(options[1], "base_url")


@pytest.mark.parametrize(
    ("options_yaml", "error"),
    [
        ("      provider_option_keys: remote_chat\n", "must be a list"),
        ("      provider_option_keys: []\n", "must not be empty"),
        (
            "      provider_option_keys:\n"
            "        - remote_chat\n"
            "        - remote_chat\n",
            "must not contain duplicates",
        ),
        (
            "      provider_option_keys:\n"
            "        - remote_chat\n"
            "        - ' '\n",
            "must be a non-empty string",
        ),
        (
            "      provider_option_keys:\n"
            "        - other_chat\n",
            "must include default provider_key",
        ),
    ],
)
def test_provider_options_reject_invalid_whitelists(
    tmp_path: Path,
    monkeypatch,
    options_yaml: str,
    error: str,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    remote_chat:
      provider: openai
      openai:
        model: remote-model
    other_chat:
      provider: openai
      openai:
        model: other-model
""",
        biz=(
            "\n    agent.main:\n"
            "      kind: chat\n"
            "      provider_key: remote_chat\n"
            f"{options_yaml}"
        ),
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match=error):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_provider_options_reject_unknown_pool_key(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    remote_chat:
      provider: openai
      openai:
        model: remote-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: remote_chat
      provider_option_keys:
        - remote_chat
        - removed_chat
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="provider config not found: removed_chat"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_explicit_provider_selection_must_be_whitelisted(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "llm.yaml"
    _write_llm_config(
        path,
        providers="""
    remote_chat:
      provider: openai
      openai:
        model: remote-model
    hidden_chat:
      provider: openai
      openai:
        model: hidden-model
""",
        biz="""
    agent.main:
      kind: chat
      provider_key: remote_chat
      provider_option_keys:
        - remote_chat
""",
    )
    _use_llm(path, monkeypatch)

    with pytest.raises(ValueError, match="not in provider_option_keys"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY, provider_key="hidden_chat")

    with pytest.raises(ValueError, match="not in provider_option_keys"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY, provider_key="")
