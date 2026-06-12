"""MemoryManager CLI 测试 — 用于手动验证向量记忆系统的各项功能。

用法::

    uv run python -m rpg_world.rpg_core.memory.test_run
    uv run python -m rpg_world.rpg_core.memory.test_run --session mygame
    uv run python -m rpg_world.rpg_core.memory.test_run --query "森林"
"""

__test__ = False  # 阻止 pytest 自动收集（本文件为独立 CLI，非 pytest 用例）


import sys
import time
from pathlib import Path

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

from rpg_world.rpg_core.settings import settings, MemorySettings
from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
from rpg_world.rpg_core.memory.memory_manager import MemoryManager, format_recall_item


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def test_config() -> None:
    """1. 检查配置是否正确加载。"""
    _print_separator("1. MemorySettings 配置检查")

    mem = settings.memory_settings
    print(f"  enabled:              {mem.enabled}")
    print(f"  embedding_model_path: {mem.embedding_model_path}")
    print(f"  exists:               {Path(mem.embedding_model_path).exists()}")
    print(f"  n_ctx:                {mem.n_ctx}")
    print(f"  n_gpu_layers:         {mem.n_gpu_layers}")
    print(f"  top_k:                {mem.top_k}")
    print(f"  chunk_size:           {mem.chunk_size}")
    print(f"  chunk_overlap:        {mem.chunk_overlap}")
    print(f"  DB path:              {settings.get_vector_db_path('', 'test_mm')}")


def test_create() -> MemoryManager | None:
    """2. 同步创建 MemoryManager（加载模型 + 建 DB）。"""
    _print_separator("2. MemoryManager.create() 同步创建")

    recalled = RecalledMemoryStore()
    mm = MemoryManager.create(
        recalled_store=recalled,
        session_dir=str(settings.session_dir("", "test_mm")),
        get_vector_db_path=str(settings.get_vector_db_path("", "test_mm")),
        mem_cfg=settings.memory_settings,
    )

    if mm is None:
        print("  ❌ MemoryManager.create() 返回 None")
        return None

    print("  ✅ MemoryManager 创建成功")
    print(f"  类型: {type(mm).__name__}")
    print(f"  index_manager: {mm._index_manager is not None}")
    print(f"  retriever: {mm._retriever is not None}")
    print(f"  DB 文件: {settings.get_vector_db_path('', 'test_mm')}")
    print(f"  DB 存在: {settings.get_vector_db_path('', 'test_mm').exists()}")
    return mm


async def test_async_init(mm: MemoryManager, session: str) -> None:
    """3. 异步初始化（全量索引 + FileWatcher 注册）。"""
    _print_separator(f"3. async_init() 异步索引（session={session}）")

    t0 = time.monotonic()
    await mm.async_init()
    elapsed = time.monotonic() - t0

    print(f"  耗时: {elapsed:.2f}s")
    print(f"  async_inited: {mm._async_inited}")


def _print_recall_item(idx: int, item: "RecallItem") -> None:
    """打印一条 RecallItem 的完整信息（委托到 format_recall_item）。"""
    print(format_recall_item(idx, item))
    print()


def test_recall(mm: MemoryManager, query: str) -> None:
    """4. 执行召回测试。"""
    _print_separator(f"4. recall(query='{query}')")

    items = mm.recall(query)
    print(f"  返回条目: {len(items)}")
    for i, item in enumerate(items):
        _print_recall_item(i, item)

    print(f"  RecalledMemoryStore: {len(mm._recalled_store.get_items())} 条")


def test_vector_store(session: str) -> None:
    """5. 直接检查 VectorStore 中的数据。"""
    _print_separator("5. VectorStore 内容检查")

    from rpg_world.rpg_core.memory.vector_store import VectorStore

    mem = settings.memory_settings
    db_path = settings.get_vector_db_path("", session)

    if not db_path.exists():
        print("  ⚠️  DB 不存在，跳过")
        return

    # 需要 embedding provider 来获取 dimension
    from rpg_world.rpg_core.memory.embedding_provider import LlamaCppEmbeddingProvider

    try:
        embed = LlamaCppEmbeddingProvider(
            gguf_model_path=mem.embedding_model_path,
            n_ctx=mem.n_ctx,
            n_gpu_layers=mem.n_gpu_layers,
        )
        store = VectorStore(db_path=db_path, dimension=embed.dimension())
        embed.close()
    except Exception as exc:
        print(f"  ❌ 无法打开 VectorStore: {exc}")
        return

    # 检查 chunk 数量
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"  总 chunk 数: {count}")

    if count > 0:
        # 显示前 3 条
        rows = conn.execute(
            "SELECT id, source, file, chunk_idx, substr(text, 1, 80) FROM chunks LIMIT 3"
        ).fetchall()
        for r in rows:
            print(f"  #{r[0]} source={r[1]} file={r[2]}[{r[3]}] → {r[4]}...")
    conn.close()


def test_cleanup() -> None:
    """6. 清理测试数据。"""
    _print_separator("6. 清理")

    import shutil

    db = settings.get_vector_db_path("", "test_mm")
    if db.exists():
        db.unlink()
        print(f"  🗑️  删除 DB: {db}")


def _loop(mm: MemoryManager, session: str) -> None:
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
            print(f"  session:           {session}")
            print(f"  DB:                {settings.get_vector_db_path('', session)}")
            print(f"  DB 存在:            {settings.get_vector_db_path('', session).exists()}")
            print(f"  inited:              {mm._inited}")
            print(f"  index_manager:      {mm._index_manager is not None}")
            print(f"  retriever:          {mm._retriever is not None}")
            print(f"  top_k:              {mm._top_k}")
            print(f"  RecalledStore 条数: {len(mm._recalled_store.get_items())}")

        elif cmd == "db":
            test_vector_store(session)

        elif cmd == "reindex":
            _print_separator("重索引")
            if mm._index_manager:
                mm._index_manager.reindex_all()
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
    parser.add_argument("--session", default="test_mm", help="测试用的 session ID（默认: test_mm）")
    parser.add_argument("--query", default="记忆", help="启动后首次 recall 的查询文本（默认: 记忆）")
    parser.add_argument("--skip-cleanup", action="store_true", help="保留测试数据不清理")
    args = parser.parse_args()

    print(f"\n🔧 MemoryManager 测试 — session={args.session!r}\n")

    # 前置检查
    test_config()
    if not settings.memory_settings.enabled:
        print("\n  ⚠️  memory 未启用（settings.json memory.enabled = false）")
        return

    # 创建
    mm = test_create()
    if mm is None:
        return

    # 同步初始化（DB 有数据则跳过索引，否则全量索引 → FileWatcher 启动）
    mm.init()

    # 启动前的自动 recall
    test_recall(mm, args.query)

    # 进入交互循环
    _loop(mm, args.session)

    # 清理
    if not args.skip_cleanup:
        test_cleanup()
    print("👋 再见")


if __name__ == "__main__":
    main()
