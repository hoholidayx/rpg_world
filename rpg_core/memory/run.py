"""MemoryManager CLI 测试 — 用于手动验证向量记忆系统的各项功能。

用法::

    uv run python -m rpg_world.rpg_core.memory.test_run
    uv run python -m rpg_world.rpg_core.memory.test_run --session mygame
    uv run python -m rpg_world.rpg_core.memory.test_run --query "森林"
"""

# ruff: noqa: E402, I001

__test__ = False  # 阻止 pytest 自动收集（本文件为独立 CLI，非 pytest 用例）


import sys
import shutil
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

# ── 确保可以在项目外直接运行 ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from loguru import logger

# 配置控制台输出
logger.remove()
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - {message}",
    colorize=True,
)

from rpg_world.rpg_core.session.manager import SessionManager
from rpg_world.rpg_core.settings import settings
from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
from rpg_world.rpg_core.memory.memory_manager import MemoryManager, format_recall_item
from rpg_world.rpg_core.utils.path_utils import (
    PACKAGE_ROOT,
    ensure_workspace_dir,
    list_workspaces,
    resolve_workspace_root,
)

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.memory_manager import RecallItem


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _format_workspace_name(workspace: str) -> str:
    return workspace or "默认（根工作区）"


def _format_secret(value: str | None) -> str:
    return "set" if value else "unset"


def _print_line(label: str, value: object, indent: str = "  ") -> None:
    print(f"{indent}{label:<24} {value}")


def _print_provider_config(title: str, provider_cfg) -> None:  # noqa: ANN001
    print(f"  {title}:")
    _print_line("provider:", provider_cfg.provider, "    ")
    openai = provider_cfg.openai or {}
    llama = provider_cfg.llama or {}
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
            ("max_candidates", "llama.max_candidates"),
            ("max_tokens", "llama.max_tokens"),
            ("temperature", "llama.temperature"),
            ("llama_weight", "llama.llama_weight"),
        ]:
            if key in llama:
                _print_line(f"{label}:", llama.get(key), "    ")


def _print_available_workspaces() -> None:
    workspaces = list_workspaces(PACKAGE_ROOT)
    print("  可用 workspaces:")
    for item in workspaces:
        name = item["name"] or ""
        label = item["label"]
        print(f"    - {label}: {_format_workspace_name(name)}")


def _create_temp_workspace() -> str:
    workspace = f"data/memory_cli_{uuid.uuid4().hex[:8]}"
    ensure_workspace_dir(PACKAGE_ROOT, workspace)
    return workspace


def _ensure_session(workspace: str, session: str) -> bool:
    sessions = SessionManager.list_sessions(workspace)
    if session in sessions:
        return False
    SessionManager.create(workspace, session)
    return True


def show_config(workspace: str, session: str) -> None:
    """1. 检查配置是否正确加载。"""
    _print_separator("1. MemorySettings 配置检查")

    mem = settings.memory_settings
    _print_available_workspaces()
    _print_line("选中 workspace:", workspace)
    _print_line("选中 session:", session)
    _print_line("enabled:", mem.enabled)
    _print_provider_config("embedding", mem.embedding_provider)
    _print_line("hybrid_enabled:", mem.hybrid_enabled)
    _print_line("vector_k:", mem.vector_k)
    _print_line("bigram_k:", mem.bigram_k)
    _print_line("hybrid_vector_weight:", mem.hybrid_vector_weight)
    _print_line("hybrid_bigram_weight:", mem.hybrid_bigram_weight)
    _print_line("hybrid_exact_weight:", mem.hybrid_exact_weight)
    _print_line("hybrid_recency_weight:", mem.hybrid_recency_weight)
    _print_line("top_k:", mem.top_k)
    _print_line("chunk_size:", mem.chunk_size)
    _print_line("chunk_overlap:", mem.chunk_overlap)
    _print_line("llama_process_enabled:", mem.llama_process_enabled)
    _print_line("llama_request_timeout_ms:", mem.llama_request_timeout_ms)
    _print_line("llama_startup_timeout_ms:", mem.llama_startup_timeout_ms)
    _print_line("llama_max_parallel_models:", mem.llama_max_parallel_models)
    _print_line("query_planner_enabled:", mem.query_planner_enabled)
    _print_provider_config("query_planner", mem.query_planner_provider)
    _print_line("rerank_enabled:", mem.rerank_enabled)
    _print_provider_config("rerank", mem.rerank_provider)
    _print_line("DB path:", settings.get_vector_db_path(workspace, session))
    _print_line("session dir:", settings.session_dir(workspace, session))


def create_manager(workspace: str, session: str) -> MemoryManager | None:
    """2. 同步创建 MemoryManager（加载模型 + 建 DB）。"""
    _print_separator("2. MemoryManager.create() 同步创建")

    recalled = RecalledMemoryStore()
    mm = MemoryManager.create(
        recalled_store=recalled,
        session_dir=str(settings.session_dir(workspace, session)),
        get_vector_db_path=str(settings.get_vector_db_path(workspace, session)),
        mem_cfg=settings.memory_settings,
    )

    if mm is None:
        print("  ❌ MemoryManager.create() 返回 None")
        return None

    print("  ✅ MemoryManager 创建成功")
    print(f"  类型: {type(mm).__name__}")
    print(f"  index_manager: {mm._index_manager is not None}")
    print(f"  retriever: {mm._retriever is not None}")
    print(f"  DB 文件: {settings.get_vector_db_path(workspace, session)}")
    print(f"  DB 存在: {settings.get_vector_db_path(workspace, session).exists()}")
    return mm


def initialize_manager(mm: MemoryManager, session: str) -> None:
    """3. 初始化（仅注册 FileWatcher，不执行全量重建）。"""
    _print_separator(f"3. init() 初始化（session={session}）")

    t0 = time.monotonic()
    mm.init()
    elapsed = time.monotonic() - t0

    print(f"  耗时: {elapsed:.2f}s")
    print(f"  inited: {mm._inited}")


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

    db_path = settings.get_vector_db_path(workspace, session)

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

    try:
        SessionManager.delete(workspace, session)
        print(f"  🗑️  删除 session: {session}")
    except Exception as exc:
        print(f"  ⚠️  删除 session 失败: {exc}")

    db = settings.get_vector_db_path(workspace, session)
    if db.exists():
        db.unlink()
        print(f"  🗑️  删除 DB: {db}")

    if remove_workspace:
        ws_root = resolve_workspace_root(PACKAGE_ROOT, workspace)
        if ws_root.exists():
            shutil.rmtree(ws_root, ignore_errors=True)
            print(f"  🗑️  删除 workspace: {ws_root}")


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
            print(f"  DB:                {settings.get_vector_db_path(workspace, session)}")
            print(f"  DB 存在:            {settings.get_vector_db_path(workspace, session).exists()}")
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
    parser.add_argument("--workspace", default="", help="测试用 workspace（默认: 自动创建临时 workspace）")
    parser.add_argument("--session", default="test_mm", help="测试用的 session ID（默认: test_mm）")
    parser.add_argument("--query", default="记忆", help="启动后首次 recall 的查询文本（默认: 记忆）")
    parser.add_argument("--skip-cleanup", action="store_true", help="保留测试数据不清理")
    parser.add_argument("--list-workspaces", action="store_true", help="仅打印可用 workspaces 并退出")
    args = parser.parse_args()

    if args.list_workspaces:
        _print_available_workspaces()
        return

    workspace = args.workspace.strip() or _create_temp_workspace()
    temporary_workspace = not bool(args.workspace.strip())

    print(f"\n🔧 MemoryManager 测试 — workspace={workspace!r} session={args.session!r}\n")

    # 前置检查
    show_config(workspace, args.session)
    try:
        if not settings.memory_settings.enabled:
            print("\n  ⚠️  memory 未启用（settings.yaml memory.enabled = false）")
            return

        _ensure_session(workspace, args.session)
        mm = create_manager(workspace, args.session)
        if mm is not None:
            # 同步初始化（仅注册 FileWatcher）
            initialize_manager(mm, args.session)

            # 启动前的自动 recall
            preview_recall(mm, args.query)

            # 进入交互循环
            _loop(mm, workspace, args.session)
    finally:
        # 清理
        if not args.skip_cleanup and temporary_workspace:
            cleanup_workspace(workspace, args.session, remove_workspace=temporary_workspace)
        elif args.skip_cleanup and temporary_workspace:
            print("  ℹ️  保留临时 workspace（skip-cleanup）")
    print("👋 再见")


if __name__ == "__main__":
    main()
