"""RPG World agent hook — a concrete AgentHook subclass.

Hooks implemented:
  1. ``before_iteration`` — receives the actual ``messages_for_model``
     (the filtered/processed messages that will be sent to the LLM),
     allowing per-turn inspection or modification.
  2. ``after_iteration`` — logs all LLM responses, distinguishing
     reasoning/thinking from tool calls.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from nanobot.agent import AgentHook, AgentHookContext
from nanobot.utils.helpers import strip_think


class RpgWorldHook(AgentHook):
    """Appends an RPG framing to the system prompt and logs model-bound messages."""

    def __init__(self, world_name: str = "Nanobot Realm") -> None:
        super().__init__()
        self.world_name = world_name
        self.system_prompt: str | None = None
        # 累积本轮所有迭代的 LLM 回复，turn 结束后清空
        self._turn_responses: list[dict] = []

    async def before_iteration(self, context: AgentHookContext) -> None:
        """Remove system messages from context and inject RPG World context."""
        context.messages = [msg for msg in context.messages if msg.get("role") != "system"]
        for msg in reversed(context.messages):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content")
            if isinstance(content, str) and "[Runtime Context" in content:
                new_content = self._update_runtime_context(content)
                if new_content is not None:
                    msg["content"] = new_content
                break

    def _update_runtime_context(self, content: str) -> str | None:
        """Override to customize the runtime context block in a message.

        The default implementation appends the RPG world tag after the runtime
        context block. Return ``None`` to leave the message unchanged.

        Args:
            content: The full message text containing the runtime context block.

        Returns:
            Modified message content, or ``None`` if no modification is needed.
        """
        rpg_tag = "[RPG World: {}]".format(self.world_name)
        if rpg_tag in content:
            return None
        end_marker = "[/Runtime Context]"
        end_pos = content.find(end_marker)
        if end_pos < 0:
            return None
        split = end_pos + len(end_marker)
        return content[:split] + "\n" + rpg_tag + content[split:]

    async def after_iteration(self, context: AgentHookContext) -> None:
        """记录本轮每次 LLM 回复，在最后一轮迭代时统一处理。

        通过 ``context.final_content is not None`` 判断是否为本轮最后一次
        迭代（即 LLM 已完全输出，本轮即将结束）。
        """
        if context.response is None:
            return

        # 累积本轮 LLM 回复
        self._turn_responses.append({
            "iteration": context.iteration,
            "reasoning": context.response.reasoning_content,
            "thinking_blocks": context.response.thinking_blocks,
            "tool_calls": [
                {"name": tc.name, "args": tc.arguments}
                for tc in context.response.tool_calls
            ],
            "content": context.response.content,
            "stop_reason": context.stop_reason,
        })

        # 本轮尚未结束，只做常规日志输出
        if context.final_content is None:
            await self._log_iteration_response(context)
            return

        # ── 本轮已结束，统一处理最终结果 ──────────────────────
        logger.info("[RPG World] 本轮结束 —— stop_reason={}, 总迭代次数={}",
                     context.stop_reason, len(self._turn_responses))
        await self._process_turn_end(context)
        self._turn_responses.clear()

    async def _log_iteration_response(self, context: AgentHookContext) -> None:
        """按类型输出单次 LLM 回复的日志。"""
        # 推理/思考内容（DeepSeek, Kimi 等）
        if context.response.reasoning_content:
            logger.info("[RPG World] 思考（推理）:\n{}", context.response.reasoning_content)

        # 扩展思考块（Anthropic）
        if context.response.thinking_blocks:
            for block in context.response.thinking_blocks:
                logger.info("[RPG World] 思考（扩展）:\n{}", block)

        # 工具调用
        if context.response.tool_calls:
            for tc in context.response.tool_calls:
                args_str = json.dumps(tc.arguments, ensure_ascii=False)
                logger.info("[RPG World] 工具调用: {}({})", tc.name, args_str[:500])

        # 常规回复（剔除 think 标签，避免与 reasoning_content 重复输出）
        if context.response.content:
            clean = strip_think(context.response.content)
            if clean:
                logger.info("[RPG World] 回复:\n{}", clean)

    async def _process_turn_end(self, context: AgentHookContext) -> None:
        """本轮所有迭代结束后统一处理。

        子类可覆盖此方法实现自定义的收尾逻辑。
        此时 ``self._turn_responses`` 包含本轮所有迭代的 LLM 回复记录。
        """
        logger.info("[RPG World] 最终内容:\n{}", context.final_content)

        if context.error:
            logger.warning("[RPG World] 本轮异常: {}", context.error)
