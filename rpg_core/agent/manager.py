"""AgentManager — 单例，统一管理 RPGGameAgent 的创建与缓存。

确保同一进程内只有一个 agent 实例池和一个 FileWatcher。

用法::

    from rpg_core.agent.manager import AgentManager

    agent = AgentManager.get_or_create(session_id="mygame")
    await AgentManager.ensure_initialized()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.agent import RPGGameAgent

if TYPE_CHECKING:
    pass


class SessionDeletionInProgressError(RuntimeError):
    """Raised when a request targets a session currently being deleted."""


class AgentManager:
    """Agent 管理器单例。

    统一管理 ``RPGGameAgent`` 的创建与缓存，确保同一进程内：
    - 相同全局 ``session_id`` 复用同一 agent 实例
    - ``FileWatcher`` 等全局资源只初始化一次
    - 所有模块（FastAPI / Telegram / CLI）共享同一 agent 池
    """

    _instances: dict[str, RPGGameAgent] = {}
    _initialized: bool = False
    _initialized_targets: set[str] = set()
    _deleting_sessions: set[str] = set()

    @classmethod
    def _cache_key(cls, session_id: str) -> str:
        return session_id

    @classmethod
    def get_or_create(
        cls,
        session_id: str = "default",
    ) -> RPGGameAgent:
        """获取或创建一个 ``RPGGameAgent`` 实例。

        Parameters
        ----------
        session_id:
            会话 ID，同一会话复用同一 agent。
        Session IDs are globally unique in rpg_data, so the runtime cache is
        intentionally keyed by ``session_id`` only.
        """
        key = cls._cache_key(session_id)
        if key in cls._deleting_sessions:
            raise SessionDeletionInProgressError(
                f"Session {session_id!r} is being deleted"
            )
        if key not in cls._instances:
            cls._instances[key] = RPGGameAgent(session_id=session_id)
        return cls._instances[key]

    @classmethod
    async def ensure_initialized(cls, session_id: str = "default") -> None:
        """确保至少有一个 agent 完成初始化。

        触发 ``FileWatcher`` 的启动和 session-scoped runtime 初始化。
        在所有模块启动前调用一次即可。

        Parameters
        ----------
        session_id:
            初始化时使用的 session ID。默认为 ``"default"``，
            调用方应根据实际使用的 session 传入。
        """
        if session_id in cls._initialized_targets:
            return
        agent = cls.get_or_create(session_id=session_id)
        await agent.initialize()
        cls._initialized_targets.add(session_id)
        cls._initialized = True

    @classmethod
    async def areset(cls) -> None:
        """Close and reset every cached agent runtime."""
        first_error: BaseException | None = None
        for session_id, agent in tuple(cls._instances.items()):
            try:
                await agent.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
                continue
            if cls._instances.get(session_id) is agent:
                cls._instances.pop(session_id, None)
                cls._initialized_targets.discard(session_id)
        cls._initialized = bool(cls._initialized_targets)
        cls._deleting_sessions.clear()
        if first_error is not None:
            raise first_error

    @classmethod
    async def drop_session(cls, session_id: str) -> None:
        """Remove cached agent runtime for one globally unique session."""
        agent = cls._instances.get(session_id)
        if agent is not None:
            await agent.close()
            if cls._instances.get(session_id) is agent:
                cls._instances.pop(session_id, None)
                cls._initialized_targets.discard(session_id)
                cls._initialized = bool(cls._initialized_targets)
        else:
            cls._initialized_targets.discard(session_id)
            cls._initialized = bool(cls._initialized_targets)

    @classmethod
    async def begin_session_deletion(cls, session_id: str) -> None:
        """Block new work, evict the cached agent, and close its resources."""

        key = cls._cache_key(session_id)
        if key in cls._deleting_sessions:
            raise SessionDeletionInProgressError(
                f"Session {session_id!r} is already being deleted"
            )
        cls._deleting_sessions.add(key)
        agent = cls._instances.get(key)
        try:
            if agent is not None:
                await agent.close()
                if cls._instances.get(key) is agent:
                    cls._instances.pop(key, None)
                    cls._initialized_targets.discard(key)
                    cls._initialized = bool(cls._initialized_targets)
            else:
                cls._initialized_targets.discard(key)
                cls._initialized = bool(cls._initialized_targets)
        except BaseException:
            cls._deleting_sessions.discard(key)
            raise

    @classmethod
    def finish_session_deletion(cls, session_id: str) -> None:
        """Release the transient deletion guard after persistence completes."""

        cls._deleting_sessions.discard(cls._cache_key(session_id))
