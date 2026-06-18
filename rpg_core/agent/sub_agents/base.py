"""BaseSubAgent — 子 Agent 抽象基类。

提供子 Agent 共用的基础设施：

- LLM Provider 管理（通过显式 provider_config 选择 shared/openai/llama）
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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from loguru import logger

from rpg_world.rpg_core.agent.agent_types import (
    LLM_PROVIDER_LLAMA,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_SHARED,
    SubAgentProviderMode,
)
from rpg_world.rpg_core.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from rpg_world.rpg_core.agent.agent import RPGGameAgent
    from rpg_world.rpg_core.agent.base_provider import LLMProvider
    from rpg_world.rpg_core.agent.command import CommandDef
    from rpg_world.rpg_core.agent.sub_agents.context import SubAgentContext


@dataclass(frozen=True)
class SubAgentProviderConfig:
    """Resolved provider configuration for a sub-agent."""

    mode: SubAgentProviderMode = LLM_PROVIDER_SHARED
    openai: dict[str, Any] = field(default_factory=dict)
    llama: dict[str, Any] = field(default_factory=dict)


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
        共享主 Agent 的 LLM provider，仅 ``provider_config.mode == "shared"`` 时传入。
    provider_config:
        解析后的 provider 配置，显式选择 ``shared``、``openai`` 或 ``llama``。
    enabled:
        总开关。
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        provider_config: SubAgentProviderConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        if provider_config is None:
            if provider is None:
                raise ValueError("sub-agent provider_config is required when no shared provider is supplied")
            provider_config = SubAgentProviderConfig(mode=LLM_PROVIDER_SHARED)
        if provider is not None and provider_config.mode != LLM_PROVIDER_SHARED:
            raise ValueError("sub-agent independent provider mode must not receive a shared provider")
        if provider_config.mode == LLM_PROVIDER_SHARED and provider is None and enabled:
            raise ValueError("sub-agent shared provider mode requires a shared provider")
        self._shared_provider = provider
        self._provider_config = provider_config
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

    def get_command_def(self) -> list[CommandDef] | None:
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
        if self._provider_config.mode == LLM_PROVIDER_SHARED:
            if self._shared_provider is None:
                raise RuntimeError("shared provider is not configured")
            return self._shared_provider

        if self._own_provider is None:
            if self._provider_config.mode == LLM_PROVIDER_OPENAI:
                from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider

                cfg = self._provider_config.openai
                self._own_provider = OpenAIProvider(
                    model=str(cfg.get("model") or self._model or "gpt-4o"),
                    api_key=cfg.get("api_key") or self._api_key,
                    base_url=cfg.get("base_url") or self._base_url,
                    max_tokens=cfg.get("max_tokens"),
                    temperature=cfg.get("temperature"),
                )
            elif self._provider_config.mode == LLM_PROVIDER_LLAMA:
                from rpg_world.rpg_core.agent.sub_agents.llama_provider import LlamaCompletionProvider

                cfg = self._provider_config.llama
                self._own_provider = LlamaCompletionProvider(
                    model_path=str(cfg["model_path"]),
                    n_ctx=int(cfg.get("n_ctx", 2048)),
                    n_gpu_layers=int(cfg.get("n_gpu_layers", 0)),
                    request_timeout_ms=int(cfg.get("request_timeout_ms", 60000)),
                    max_tokens=int(cfg.get("max_tokens", 512)),
                    temperature=float(cfg.get("temperature", 0.0)),
                )
            else:
                raise RuntimeError(f"unsupported sub-agent provider mode: {self._provider_config.mode}")
        return self._own_provider

    @property
    def enabled(self) -> bool:
        """Whether this sub-agent is active for provider calls and commands."""
        return self._enabled

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
