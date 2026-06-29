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
from llm_service.manager import LLMManager
from llm_service.keys import AGENT_MAIN_BIZ_KEY

if TYPE_CHECKING:
    pass


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
        if key not in cls._instances:
            manager = LLMManager.get()
            provider = manager.get_provider(AGENT_MAIN_BIZ_KEY)
            cls._instances[key] = RPGGameAgent(
                session_id=session_id,
                model=provider.get_default_model(),
            )
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
        await agent._ensure_initialized()
        cls._initialized_targets.add(session_id)
        cls._initialized = True

    @classmethod
    def reset(cls) -> None:
        """重置所有 agent 实例和初始化状态（主要用于测试）。"""
        cls._instances.clear()
        cls._initialized = False
        cls._initialized_targets.clear()

    @classmethod
    def drop_session(cls, session_id: str) -> None:
        """Remove cached agent runtime for one globally unique session."""
        cls._instances.pop(session_id, None)
        cls._initialized_targets.discard(session_id)
        cls._initialized = bool(cls._initialized_targets)
