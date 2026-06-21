from __future__ import annotations

from pathlib import Path

import pytest

from rpg_world.rpg_core.llm.config import reload_llm_settings, resolve_biz_config
from rpg_world.rpg_core.llm.keys import (
    AGENT_MAIN_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
    RERANK_MODEL_TYPE_QWEN3_LOGIT,
)


def _write_llm_config(path: Path, body: str) -> None:
    path.write_text(
        f"""
base:
  runtime:
    llama_process_enabled: true
    llama_request_timeout_ms: 60000
    llama_startup_timeout_ms: 120000
    llama_max_parallel_models: 2
  biz:
{body}
profiles:
  local: {{}}
""",
        encoding="utf-8",
    )


def _use_llm(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rpg_world.rpg_core.llm.config._LLM_SETTINGS_PATH",
        path,
    )
    monkeypatch.setenv("RPG_WORLD_PROFILE", "local")
    reload_llm_settings()


def test_resolve_biz_config_deep_merges_shared_chain(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.shared:
      kind: chat
      provider: openai
      openai:
        model: base-model
        api_key: base-key
        max_tokens: 777
        temperature: 0.1
    agent.main:
      kind: chat
      provider: shared
      shared_from: agent.shared
      openai:
        api_key: child-key
        temperature: 0.5
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    cfg = resolve_biz_config(AGENT_MAIN_BIZ_KEY)
    assert cfg.provider == "openai"
    assert cfg.openai_model == "base-model"
    assert cfg.openai_api_key == "child-key"
    assert cfg.openai_max_tokens == 777
    assert cfg.openai_temperature == 0.5


def test_resolve_biz_config_raises_when_shared_source_missing(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: chat
      provider: shared
      shared_from: missing.source
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="not found"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_detects_shared_cycles(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    a:
      kind: chat
      provider: shared
      shared_from: b
    b:
      kind: chat
      provider: shared
      shared_from: a
    agent.main:
      kind: chat
      provider: shared
      shared_from: b
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="cycle"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY)


def test_resolve_biz_config_rejects_invalid_provider(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: chat
      provider: unknown
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="agent.main.provider"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).provider


def test_resolve_biz_config_rejects_invalid_kind(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: chaty
      provider: openai
      openai:
        model: test-model
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="agent.main.kind"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).kind


def test_resolve_biz_config_rejects_empty_provider(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: chat
      provider: ""
      openai:
        model: test-model
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="agent.main.provider"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).provider


def test_resolve_biz_config_rejects_empty_kind(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: ""
      provider: openai
      openai:
        model: test-model
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="agent.main.kind"):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).kind


def test_resolve_biz_config_rejects_invalid_float_value(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    agent.main:
      kind: chat
      provider: openai
      openai:
        model: test-model
        temperature: abc
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError):
        resolve_biz_config(AGENT_MAIN_BIZ_KEY).openai_temperature


def test_resolve_biz_config_requires_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    memory.rerank:
      kind: rerank
      provider: llama
      llama:
        model_path: data/models/rerank.gguf
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="memory.rerank.rerank_model_type"):
        resolve_biz_config(MEMORY_RERANK_BIZ_KEY).rerank_model_type


def test_resolve_biz_config_accepts_explicit_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    memory.rerank:
      kind: rerank
      provider: llama
      rerank_model_type: qwen3_logit
      llama:
        model_path: data/models/rerank.gguf
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    assert resolve_biz_config(MEMORY_RERANK_BIZ_KEY).rerank_model_type == RERANK_MODEL_TYPE_QWEN3_LOGIT


def test_resolve_biz_config_rejects_unknown_rerank_model_type(tmp_path: Path, monkeypatch) -> None:
    _write_llm_config(
        tmp_path / "llm.yaml",
        """
    memory.rerank:
      kind: rerank
      provider: llama
      rerank_model_type: unknown
      llama:
        model_path: data/models/rerank.gguf
""",
    )
    _use_llm(tmp_path / "llm.yaml", monkeypatch)

    with pytest.raises(ValueError, match="memory.rerank.rerank_model_type"):
        resolve_biz_config(MEMORY_RERANK_BIZ_KEY).rerank_model_type
