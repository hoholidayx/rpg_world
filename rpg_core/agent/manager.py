"""AgentManager — 单例，统一管理 RPGGameAgent 的创建与缓存。

确保同一进程内只有一个 agent 实例池、一个 FileWatcher、一套 Manager 缓存。

用法::

    from rpg_world.rpg_core.agent.manager import AgentManager

    agent = AgentManager.get_or_create(session_id="mygame")
    await AgentManager.ensure_initialized()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.settings import settings

if TYPE_CHECKING:
    pass


class AgentManager:
    """Agent 管理器单例。

    统一管理 ``RPGGameAgent`` 的创建与缓存，确保同一进程内：
    - 相同 ``(session_id, api_key)`` 复用同一 agent 实例
    - ``FileWatcher``、``BaseManager`` 等全局资源只初始化一次
    - 所有模块（FastAPI / Telegram / CLI）共享同一 agent 池
    """

    _instances: dict[str, RPGGameAgent] = {}
    _initialized: bool = False

    @classmethod
    def _cache_key(cls, session_id: str, api_key: str | None) -> str:
        return f"{session_id}::{api_key or ''}"

    @classmethod
    def get_or_create(
        cls,
        session_id: str = "default",
        api_key: str | None = None,
    ) -> RPGGameAgent:
        """获取或创建一个 ``RPGGameAgent`` 实例。

        Parameters
        ----------
        session_id:
            会话 ID，同一会话复用同一 agent。
        api_key:
            LLM API key，用于 agent 内部的 provider。为 ``None`` 时使用
            环境变量 ``OPENAI_API_KEY``。
        """
        key = cls._cache_key(session_id, api_key)
        if key not in cls._instances:
            cls._instances[key] = RPGGameAgent(
                session_id=session_id,
                model=settings.agent_model,
                api_key=api_key,
                base_url=settings.agent_base_url or None,
                max_tokens=settings.agent_max_tokens,
                temperature=settings.agent_temperature,
            )
        return cls._instances[key]

    @classmethod
    async def ensure_initialized(cls) -> None:
        """确保至少有一个 agent 完成初始化。

        触发 ``FileWatcher`` 的启动和 ``BaseManager`` 缓存加载。
        在所有模块启动前调用一次即可。
        """
        if not cls._initialized:
            agent = cls.get_or_create()
            await agent._ensure_initialized()
            cls._initialized = True

    @classmethod
    def reset(cls) -> None:
        """重置所有 agent 实例和初始化状态（主要用于测试）。"""
        cls._instances.clear()
        cls._initialized = False
