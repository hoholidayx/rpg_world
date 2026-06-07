"""BaseSubAgent — 子 Agent 抽象基类。

提供子 Agent 共用的基础设施：

- LLM Provider 管理（共享主 Agent 的 provider 或自建独立 LLM）
- 重入守卫（防止并发执行）
- ``SubAgentContext`` 绑定（世界书 + 角色卡 + 子 Agent 系统提示）
- ``ToolProvider`` 接口 + 工具提供者管理（注册、去重、刷新）
- ``_build_system_context()`` 渲染完整系统上下文

所有子 Agent **必须**定义自己的 ``system_prompt`` 属性（类似 Java 抽象方法），
单场景子 Agent 返回主提示词，多管线子 Agent 返回空串由各管线自行提供。

子 Agent 的 ``system_prompt`` 通过 ``bind_context()`` 注入到 ``SubAgentContext``，
调用 ``_build_system_context()`` 或 ``context.render()`` 可获得完整输出：
``{system_prompt}\\n\\n## 世界书\\n\\n## 角色卡``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from loguru import logger

from rpg_world.rpg_core.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent
    from rpg_world.rpg_core.agent.base_provider import LLMProvider
    from rpg_world.rpg_core.agent.sub_agents.context import SubAgentContext


@runtime_checkable
class ToolProvider(Protocol):
    """工具提供者接口。

    任何需要向子 Agent 提供工具的类，实现此接口即可。
    例如 ``SceneTracker``、天气 Tracker、NPC Tracker 等。

    用法::

        class MyTracker:
            def get_tools(self) -> list[BaseTool]:
                return [ToolA(), ToolB()]
    """

    def get_tools(self) -> list[BaseTool]:
        """返回该提供者当前的工具列表。"""


class BaseSubAgent:
    """子 Agent 抽象基类。

    Parameters
    ----------
    provider:
        共享主 Agent 的 LLM provider。传 ``None`` 时使用 *model* / *api_key* / *base_url* 自建。
    model:
        独立 LLM 模型名（仅 *provider* 为 None 时生效）。
    api_key:
        独立 LLM API key。
    base_url:
        独立 LLM base URL。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._shared_provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._own_provider: LLMProvider | None = None
        self._enabled = enabled
        self._busy: bool = False
        self._context: SubAgentContext | None = None
        self._tool_providers: list[ToolProvider] = []

    # ── Abstract-like ────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """子 Agent 自身系统提示。

        子类必须覆盖此属性（类似 Java 抽象方法）。

        - 单场景子 Agent（如 ``StatusSubAgent``）返回主提示词。
        - 多管线子 Agent（如 ``MemorySubAgent``）返回空串，各管线自行提供。
        """
        return ""

    # ── Command interface（子 Agent 可选的命令处理） ─────────────────

    def get_command_def(self) -> Any | None:
        """返回子 Agent 处理的命令定义，或 ``None`` 表示不处理任何命令。"""
        return None

    def accept_command(self, command: str) -> bool:
        """判断此子 Agent 是否处理指定斜杠命令。"""
        return False

    async def execute_command(self, command: str, args: list[str], agent: RPGGameAgent | None = None) -> dict | None:
        """执行命令，返回 ``{"reply": str, "stats": dict | None}`` 或 ``None``。

        Parameters
        ----------
        command:
            命令名（如 ``/compact``）。
        args:
            命令参数列表。
        agent:
            主 ``RPGGameAgent`` 实例，子 Agent 可通过它访问 agent 方法。
        """
        return None

    # ── Provider ─────────────────────────────────────────────────────

    def _get_provider(self) -> LLMProvider:
        """获取有效 LLM provider——共享或自建。

        子类应通过此方法获取 provider，而非直接访问 ``_shared_provider``
        或 ``_own_provider``。
        """
        if self._shared_provider is not None:
            return self._shared_provider

        if self._own_provider is None:
            from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider

            self._own_provider = OpenAIProvider(
                model=self._model or "gpt-4o",
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._own_provider

    # ── Context 绑定 ─────────────────────────────────────────────────

    def bind_context(self, context: SubAgentContext) -> None:
        """绑定 ``SubAgentContext`` 并注入自身系统提示。

        将子 Agent 的 ``system_prompt`` 注入到上下文中，后续
        ``context.render()`` 将输出完整内容：
        ``{system_prompt}\\n\\n## 世界书\\n\\n## 角色卡``
        """
        context.set_system_prompt(self.system_prompt)
        self._context = context
        logger.debug(
            "[BaseSubAgent] {} context bound (system_prompt={} chars)",
            type(self).__name__, len(self.system_prompt),
        )

    def _build_system_context(self, pipeline_prompt: str | None = None) -> str:
        """构建完整系统上下文。

        如果提供了 ``pipeline_prompt``（多管线场景），在其后追加
        ``context.render()``，否则直接返回 ``context.render()``
        （其中已包含系统提示）。

        Parameters
        ----------
        pipeline_prompt:
            多管线子 Agent 可传入各管线的专属提示词。为 ``None`` 时
            直接使用上下文中已有的系统提示。
        """
        if self._context is None:
            return pipeline_prompt or ""
        rendered = self._context.render()
        if pipeline_prompt:
            return f"{pipeline_prompt}\n\n{rendered}" if rendered else pipeline_prompt
        return rendered

    # ── 工具提供者管理 ──────────────────────────────────────────────

    def add_tool_provider(self, provider: ToolProvider) -> None:
        """注册工具提供者。

        重复添加同一提供者（按 identity 去重）会被忽略。子类可覆盖此方法
        在注册时额外处理工具注册。

        ``bind_context()`` 时会统一刷新所有提供者的工具。
        """
        if provider not in self._tool_providers:
            self._tool_providers.append(provider)

    def _collect_provider_tools(self) -> list[BaseTool]:
        """从所有已注册的工具提供者拉取扁平化工具列表。"""
        tools: list[BaseTool] = []
        for p in self._tool_providers:
            tools.extend(p.get_tools())
        return tools
