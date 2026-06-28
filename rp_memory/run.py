"""MemoryManager CLI 测试 — 用于手动验证向量记忆系统的各项功能。

用法::

    uv run python -m rp_memory.run
    uv run python -m rp_memory.run --session mygame
    uv run python -m rp_memory.run --query "森林"
"""

# ruff: noqa: E402, I001

__test__ = False  # 阻止 pytest 自动收集（本文件为独立 CLI，非 pytest 用例）


import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

# ── 确保可以在项目外直接运行 ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from rpg_core.settings import settings

# 配置控制台输出
logger.remove()
logger.add(
    sys.stderr,
    level=settings.logging.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - {message}",
    colorize=True,
)

from llm_service.config import resolve_llm_config
from llm_service.keys import MEMORY_EMBED_BIZ_KEY, MEMORY_QUERY_PLANNER_BIZ_KEY, MEMORY_RERANK_BIZ_KEY
from rp_memory.recalled_memory import RecalledMemoryStore
from rp_memory.memory_manager import MemoryManager, format_recall_item
from rpg_core.utils.watcher import get_watcher
from rpg_data.services import get_data_service_gateway

if TYPE_CHECKING:
    from rp_memory.memory_manager import RecallItem


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _format_secret(value: str | None) -> str:
    return "set" if value else "unset"


def _print_line(label: str, value: object, indent: str = "  ") -> None:
    print(f"{indent}{label:<24} {value}")


def _print_provider_config(title: str, provider_cfg, biz_key: str) -> None:  # noqa: ANN001
    print(f"  {title}:")
    _print_line("provider:", provider_cfg.provider, "    ")
    try:
        llm_cfg = resolve_llm_config(biz_key)
    except ValueError as exc:
        _print_line("llm.yaml:", f"invalid ({exc})", "    ")
        return
    openai = llm_cfg.openai
    llama = llm_cfg.llama
    _print_line("openai.model:", openai.get("model") or "unset", "    ")
    _print_line("openai.api_key:", _format_secret(openai.get("api_key")), "    ")
    _print_line("openai.api_key_env:", openai.get("api_key_env") or "unset", "    ")
    _print_line("openai.base_url:", openai.get("base_url") or "unset", "    ")
    _print_line("openai.max_tokens:", openai.get("max_tokens") if openai.get("max_tokens") is not None else "unset", "    ")
    _print_line("openai.temperature:", openai.get("temperature") if openai.get("temperature") is not None else "unset", "    ")
    if llama:
        for key, label in [
            ("model_path", "llama.model_path"),
            ("n_ctx", "llama.n_ctx"),
            ("n_gpu_layers", "llama.n_gpu_layers"),
            ("n_threads", "llama.n_threads"),
            ("verbose", "llama.verbose"),
            ("request_timeout_ms", "llama.request_timeout_ms"),
            ("max_tokens", "llama.max_tokens"),
            ("temperature", "llama.temperature"),
        ]:
            if key in llama:
                _print_line(f"{label}:", llama.get(key), "    ")


def _print_available_workspaces() -> None:
    workspaces = get_data_service_gateway().catalog.list_workspaces()
    print("  可用 workspaces:")
    for item in workspaces:
        print(f"    - {item.name}: {item.id}")


def _session_root(session: str) -> Path:
    return get_data_service_gateway().catalog.get_session_runtime_dir(session)


def _vector_db_path(session: str) -> Path:
    return _session_root(session) / "memory_vectors.db"


def _ensure_session(session: str) -> None:
    if get_data_service_gateway().catalog.get_session(session) is None:
        raise FileNotFoundError(
            f"Session {session!r} not found in rpg_data. Create it through catalog/Agent service first."
        )


def show_config(workspace: str, session: str) -> None:
    """1. 检查配置是否正确加载。"""
    _print_separator("1. MemorySettings 配置检查")

    mem = settings.memory_settings
    _print_available_workspaces()
    _print_line("选中 workspace:", workspace)
    _print_line("选中 session:", session)
    _print_line("enabled:", mem.enabled)
    _print_provider_config("embedding", mem.embedding_provider, MEMORY_EMBED_BIZ_KEY)
    _print_line("hybrid_enabled:", mem.hybrid_enabled)
    _print_line("vector_k:", mem.vector_k)
    _print_line("keyword_tokenizer:", mem.keyword_tokenizer)
    _print_line("keyword_k:", mem.keyword_k)
    _print_line("raw_md_mode:", mem.raw_md_mode)
    _print_line("raw_md_min_results:", mem.raw_md_min_results)
    _print_line("hybrid_vector_weight:", mem.hybrid_vector_weight)
    _print_line("hybrid_keyword_weight:", mem.hybrid_keyword_weight)
    _print_line("hybrid_raw_md_weight:", mem.hybrid_raw_md_weight)
    _print_line("hybrid_exact_weight:", mem.hybrid_exact_weight)
    _print_line("hybrid_expanded_weight:", mem.hybrid_expanded_weight)
    _print_line("hybrid_recency_weight:", mem.hybrid_recency_weight)
    _print_line("hybrid_granularity_weight:", mem.hybrid_granularity_weight)
    _print_line("top_k:", mem.top_k)
    _print_line("chunk_size:", mem.chunk_size)
    _print_line("chunk_overlap:", mem.chunk_overlap)
    _print_line("llama_process_enabled:", mem.llama_process_enabled)
    _print_line("llama_request_timeout_ms:", mem.llama_request_timeout_ms)
    _print_line("llama_startup_timeout_ms:", mem.llama_startup_timeout_ms)
    _print_line("llama_max_parallel_models:", mem.llama_max_parallel_models)
    _print_line("query_planner_enabled:", mem.query_planner_enabled)
    _print_provider_config("query_planner", mem.query_planner_provider, MEMORY_QUERY_PLANNER_BIZ_KEY)
    _print_line("rerank_enabled:", mem.rerank_enabled)
    _print_line("rerank_candidate_k:", mem.rerank_candidate_k)
    _print_line("rerank_score_weight:", mem.rerank_score_weight)
    _print_provider_config("rerank", mem.rerank_provider, MEMORY_RERANK_BIZ_KEY)
    _print_line("DB path:", _vector_db_path(session))
    _print_line("session dir:", _session_root(session))


def create_manager(workspace: str, session: str) -> MemoryManager | None:
    """2. 同步创建 MemoryManager（加载模型 + 建 DB）。"""
    _print_separator("2. MemoryManager.create() 同步创建")

    recalled = RecalledMemoryStore()
    session_root = _session_root(session)
    mm = MemoryManager.create(
        recalled_store=recalled,
        session_dir=str(session_root),
        get_vector_db_path=str(session_root / "memory_vectors.db"),
        mem_cfg=settings.memory_settings,
    )

    if mm is None:
        print("  ❌ MemoryManager.create() 返回 None")
        return None

    print("  ✅ MemoryManager 创建成功")
    print(f"  类型: {type(mm).__name__}")
    print(f"  index_manager: {mm._index_manager is not None}")
    print(f"  retriever: {mm._retriever is not None}")
    print(f"  DB 文件: {_vector_db_path(session)}")
    print(f"  DB 存在: {_vector_db_path(session).exists()}")
    return mm


def initialize_manager(mm: MemoryManager, session: str) -> None:
    """3. 初始化并启动 FileWatcher。"""
    _print_separator(f"3. init() 初始化（session={session}）")

    t0 = time.monotonic()
    mm.init()
    watcher_started = get_watcher().start()
    elapsed = time.monotonic() - t0

    print(f"  耗时: {elapsed:.2f}s")
    print(f"  inited: {mm._inited}")
    print(f"  FileWatcher: {'running' if watcher_started else 'disabled'}")


def stop_file_watcher() -> None:
    """Stop and clear FileWatcher callbacks for this standalone CLI."""
    watcher = get_watcher()
    watcher.stop()
    watcher.clear_all()
    print("  FileWatcher: stopped")


def _print_recall_item(idx: int, item: "RecallItem") -> None:
    """打印一条 RecallItem 的完整信息（委托到 format_recall_item）。"""
    print(format_recall_item(idx, item))
    print()


def preview_recall(mm: MemoryManager, query: str) -> None:
    """4. 执行召回测试。"""
    _print_separator(f"4. recall(query='{query}')")

    items = mm.recall(query)
    print(f"  返回条目: {len(items)}")
    for i, item in enumerate(items):
        _print_recall_item(i, item)

    print(f"  RecalledMemoryStore: {len(mm._recalled_store.get_items())} 条")


def inspect_vector_store(workspace: str, session: str) -> None:
    """5. 直接检查 VectorStore 中的数据。"""
    _print_separator("5. VectorStore 内容检查")

    db_path = _vector_db_path(session)

    if not db_path.exists():
        print("  ⚠️  DB 不存在，跳过")
        return

    # 检查 chunk 数量
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    backend = "unknown"
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"  总 chunk 数: {count}")
    try:
        fts_count = conn.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0]
        print(f"  FTS row 数: {fts_count}")
    except Exception as exc:
        print(f"  ⚠️  FTS 不可用: {exc}")

    try:
        has_vec0 = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
        ).fetchone() is not None
        if has_vec0:
            try:
                import sqlite_vec

                sqlite_vec.load(conn)
                backend = "sqlite_vec"
                vec_count = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
                print(f"  向量 row 数: {vec_count}")
            except Exception as exc:
                print(f"  ⚠️  向量虚表加载失败: {exc}")
        if backend != "sqlite_vec":
            has_python_vec = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_embeddings'"
            ).fetchone() is not None
            if has_python_vec:
                backend = "python"
                vec_count = conn.execute("SELECT COUNT(*) FROM vec_embeddings").fetchone()[0]
                print(f"  向量 row 数: {vec_count}")
            elif not has_vec0:
                print("  ⚠️  向量表不可用: vec_chunks / vec_embeddings 均不存在")
        print(f"  向量后端: {backend}")
    except Exception as exc:
        print(f"  ⚠️  向量表不可用: {exc}")

    if count > 0:
        # 显示前 3 条
        rows = conn.execute(
            "SELECT id, source, file, chunk_idx, substr(text, 1, 80) FROM chunks LIMIT 3"
        ).fetchall()
        for r in rows:
            print(f"  #{r[0]} source={r[1]} file={r[2]}[{r[3]}] → {r[4]}...")
    conn.close()


def cleanup_workspace(workspace: str, session: str, remove_workspace: bool = False) -> None:
    """6. 清理测试数据。"""
    _print_separator("6. 清理")

    db = _vector_db_path(session)
    if db.exists():
        db.unlink()
        print(f"  🗑️  删除 DB: {db}")

    if remove_workspace:
        print("  ⚠️  catalog workspace/session 不由 memory CLI 删除")


def _loop(mm: MemoryManager, workspace: str, session: str) -> None:
    """交互式命令循环（全部同步，无事件循环依赖）。"""

    commands = {
        "recall": "recall <query>    — 向量召回测试",
        "reindex": "reindex            — 触发全量重索引",
        "db": "db                 — 查看 VectorStore 状态",
        "info": "info               — MemoryManager 状态",
        "help": "help               — 显示帮助",
        "quit": "quit               — 退出",
    }

    print(f"\n{'=' * 60}")
    print("  命令列表（输入 help 查看）")
    for _, desc in commands.items():
        print(f"    {desc}")
    print(f"{'=' * 60}\n")

    while True:
        try:
            line = input("🛸 ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        cmd, *args = line.split(maxsplit=1)
        arg = args[0] if args else ""

        if cmd == "quit":
            break

        elif cmd == "help":
            print()
            for _, desc in commands.items():
                print(f"  {desc}")
            print()

        elif cmd == "info":
            _print_separator("MemoryManager 状态")
            print(f"  workspace:          {workspace}")
            print(f"  session:           {session}")
            print(f"  DB:                {_vector_db_path(session)}")
            print(f"  DB 存在:            {_vector_db_path(session).exists()}")
            print(f"  inited:             {mm._inited}")
            print(f"  index_manager:      {mm._index_manager is not None}")
            print(f"  retriever:          {mm._retriever is not None}")
            print(f"  top_k:              {mm._top_k}")
            print(f"  RecalledStore 条数: {len(mm._recalled_store.get_items())}")

        elif cmd == "db":
            inspect_vector_store(workspace, session)

        elif cmd == "reindex":
            _print_separator("重索引")
            mm.reindex()
            print("  ✅ 重索引完成")

        elif cmd == "recall":
            if not arg:
                print("  ⚠️  用法: recall <查询文本>")
                continue
            items = mm.recall(arg)
            print(f"  返回条目: {len(items)} (top_k={mm._top_k})")
            for i, item in enumerate(items):
                _print_recall_item(i, item)

        else:
            print(f"  ⚠️  未知命令: {cmd}（输入 help 查看命令列表）")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MemoryManager CLI 测试")
    parser.add_argument("--workspace", default="", help="仅用于显示；session 路径始终由 rpg_data catalog 解析")
    parser.add_argument("--session", default="test_mm", help="测试用的 session ID（默认: test_mm）")
    parser.add_argument("--query", default="记忆", help="启动后首次 recall 的查询文本（默认: 记忆）")
    parser.add_argument("--skip-cleanup", action="store_true", help="保留测试数据不清理")
    parser.add_argument("--list-workspaces", action="store_true", help="仅打印可用 workspaces 并退出")
    args = parser.parse_args()

    if args.list_workspaces:
        _print_available_workspaces()
        return

    workspace = args.workspace.strip()
    temporary_workspace = False

    print(f"\n🔧 MemoryManager 测试 — workspace={workspace!r} session={args.session!r}\n")

    # 前置检查
    show_config(workspace, args.session)
    try:
        if not settings.memory_settings.enabled:
            print("\n  ⚠️  memory 未启用（settings.yaml memory.enabled = false）")
            return

        _ensure_session(args.session)
        mm = create_manager(workspace, args.session)
        if mm is not None:
            # 同步初始化并启动 FileWatcher
            initialize_manager(mm, args.session)

            # 启动前的自动 recall
            preview_recall(mm, args.query)

            # 进入交互循环
            _loop(mm, workspace, args.session)
    finally:
        if "mm" in locals() and mm is not None:
            stop_file_watcher()
        # 清理
        if not args.skip_cleanup and temporary_workspace:
            cleanup_workspace(workspace, args.session, remove_workspace=temporary_workspace)
        elif args.skip_cleanup and temporary_workspace:
            print("  ℹ️  保留临时 workspace（skip-cleanup）")
    print("👋 再见")


if __name__ == "__main__":
    main()
