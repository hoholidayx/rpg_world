"""BaseSubAgent — 子 Agent 抽象基类。

提供子 Agent 共用的基础设施：

- LLM Provider 管理（共享主 Agent 的 provider 或自建独立 LLM）
- 重入守卫（防止并发执行）
- ``SubAgentContext`` 绑定（世界书 + 角色卡 + 系统提示）
- ``ToolProvider`` 接口 + 工具提供者管理（注册、去重、刷新）
- ``_build_system_context()`` 渲染完整上下文

所有子 Agent 应继承此类，避免重复实现上述逻辑。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rpg_world.rpg_core.agent.tools.base import BaseTool

if TYPE_CHECKING:
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
        """绑定 SubAgentContext（世界书 + 角色卡 + 系统提示）。

        在构建子 Agent 之后调用，或在 ``reload_rpg_context()`` 时重新绑定。
        """
        self._context = context

    def _build_system_context(self, pipeline_prompt: str) -> str:
        """渲染子系统提示：*pipeline_prompt* 后追加 SubAgentContext（如果已绑定）。

        允许子 Agent 的每个 pipeline 保留自己的专用提示，同时注入
        世界书 + 角色卡作为系统级上下文。
        """
        if self._context is None:
            return pipeline_prompt
        rendered = self._context.render()
        if not rendered:
            return pipeline_prompt
        return f"{pipeline_prompt}\n\n{rendered}"

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

