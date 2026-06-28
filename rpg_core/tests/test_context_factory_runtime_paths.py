from __future__ import annotations


def test_context_factory_uses_catalog_session_runtime_dir(
    make_data_session,
    rpg_data_gateway,
    monkeypatch,
) -> None:
    make_data_session("s_runtime")
    session_root = rpg_data_gateway.catalog.get_session_runtime_dir("s_runtime")
    captured: dict[str, object] = {}

    from rp_memory.memory_manager import MemoryManager
    from rpg_core.context.factory import build_rpg_context

    def fake_create(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(MemoryManager, "create", fake_create)

    context = build_rpg_context(workspace="ignored_workspace_id", session_id="s_runtime")
    builder = context["builder"]

    assert builder._summary_store._file == session_root / "rpg_summaries.json"
    assert builder._batch_summary_store._dir == session_root / "summaries"
    assert builder._persist_memory._memory_file == session_root / "persistent_memory.json"
    assert captured["session_dir"] == str(session_root)
    assert captured["get_vector_db_path"] == str(session_root / "memory_vectors.db")
