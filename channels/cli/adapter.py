"""CLIAdapter — 基于 Rich + prompt_toolkit 的命令行渠道适配器。

输出用 Rich 做颜色/表格/Panel 格式化，输入用 prompt_toolkit 做非阻塞异步读入。

用法::

    from channels.cli import CLIAdapter

    adapter = CLIAdapter(agent_client=client)
    await adapter.start()
"""

from __future__ import annotations

from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel

from channels.base import ChannelAdapter
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.sub_agents import StatusSubAgentRecordStatus
from rpg_core.utils.stats_formatter import format_event_stats

_HISTORY_PATH = Path.home() / ".rpg_world_cli_history"


class CLIAdapter(ChannelAdapter):
    """基于终端的标准 I/O 渠道。

    非流式模式（``_streaming=False``）用 ``send_text`` 整体输出，
    流式模式（``_streaming=True``）用 ``send_delta`` 逐段输出并实时渲染。

    Parameters
    ----------
    agent_client:
        Agent service client used by this channel.
    streaming:
        是否启用流式输出。
    """

    name = "cli"
    direct_chat_id = "direct"

    def __init__(
        self,
        agent_client=None,
        *,
        streaming: bool = True,
        session_id: str | None = None,
        workspace: str | None = None,
        session_title: str | None = None,
    ) -> None:
        super().__init__()
        self._streaming = streaming
        self._session_id_override = (session_id or "").strip() or None
        self._workspace_override = (workspace or "").strip() or None
        self._session_title = (session_title or "").strip() or None
        self._session = PromptSession(
            history=FileHistory(str(_HISTORY_PATH)),
            enable_history_search=True,
        )
        self._console = Console()
        self._running = False
        if agent_client:
            self.bind_agent_client(agent_client)

    def get_session_id(self, chat_id: str) -> str:
        if self._session_id_override is not None:
            return self._session_id_override
        raise RuntimeError("CLI session is not resolved")

    def get_workspace(self) -> str:
        if self._workspace_override is not None:
            return self._workspace_override
        raise RuntimeError("CLI workspace is not resolved")

    def get_initial_session_id(self) -> str:
        """Return the session used by this single-chat CLI adapter."""
        return self.get_session_id(self.direct_chat_id)

    # ── 生命周期 ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 CLI 交互循环。"""
        self._running = True
        self._console.print(
            "[bold green]RPG World CLI[/bold green]\n"
            f"  Session: {self.get_initial_session_id()}"
            f"{f' ({self._session_title})' if self._session_title else ''}\n"
            "  命令: /help  /clear  /reload  /context  /compact  /extract_story_memory\n"
            "  /sessions  /session_create  /session_switch  /memory_reindex  /quit\n"
            "  输入 /help 查看完整命令列表",
        )
        if self._streaming:
            self._console.print("流式模式：文本将逐段输出")
        self._console.print("")

        while self._running:
            try:
                text = await self._session.prompt_async("> ")
            except (EOFError, KeyboardInterrupt):
                break

            text = text.strip()
            if not text:
                continue
            if text == "/quit":
                await self.stop()
                break

            await self._handle_message(self.direct_chat_id, "user", text)

    async def stop(self) -> None:
        """停止 CLI 交互循环。"""
        self._running = False

    # ── 消息发送 ────────────────────────────────────────────────────────

    async def send_text(self, chat_id: str, text: str) -> None:
        """以 Rich Panel 输出完整文本。"""
        self._console.print(Panel(text, title="Reply"))

    async def send_delta(self, chat_id: str, delta: str, final: bool = False) -> None:
        """实时流式输出。"""
        if final:
            self._console.print(delta)
        else:
            self._console.print(delta, end="")

    # ── 覆写基类管线 ───────────────────────────────────────────────────

    async def _stream_and_send(self, chat_id: str, text: str) -> str:
        """流式处理，在终端逐步渲染各类事件。

        等效旧 ``cli.py`` 的 ``_handle_streaming_chat()``。
        """
        if not self._agent_client:
            return ""
        full_text = ""
        try:
            event_source = self._agent_client.stream(self.get_session_id(chat_id), text)
            async for event in event_source:
                if event.kind == StreamEventKind.TEXT:
                    full_text += event.content
                    await self.send_delta(chat_id, event.content, final=False)
                elif event.kind == StreamEventKind.THINKING:
                    self._console.print(
                        f"[dim]{event.content}[/dim]", end="",
                    )
                elif event.kind == StreamEventKind.TOOL_CALL:
                    self._console.print(
                        f"\n[cyan]── [{event.tool_name}]({event.tool_arguments})[/cyan]",
                    )
                elif event.kind == StreamEventKind.TOOL_RESULT:
                    preview = event.tool_result_preview or (
                        event.tool_result or ""
                    )[:200]
                    self._console.print(f"[green]   → {preview}[/green]")
                elif event.kind == StreamEventKind.ROUND_START:
                    if event.round_index > 0:
                        self._console.print(
                            f"\n[yellow]── round {event.round_index} ──[/yellow]",
                        )
                elif event.kind == StreamEventKind.DONE:
                    self._apply_active_session(event.active_session)
                    if event.content:
                        self._console.print(event.content)
                    self._console.print("")
                    if event.usage:
                        self._console.print(format_event_stats(event), markup=False)
                elif event.kind == StreamEventKind.ERROR:
                    self._console.print(
                        f"\n[red][stream error] {event.content}[/red]",
                    )
        except Exception as exc:
            self._console.print(f"\n[red][error] {exc}[/red]")
        return full_text

    async def _handle_buffered(self, chat_id: str, text: str) -> str:
        """缓冲模式处理：完整回复一次性输出，含 Status/Tool/Stats 信息。

        等效旧 ``cli.py`` 的 ``_handle_buffered_chat()``。
        """
        if not self._agent_client:
            return ""
        try:
            reply = await self._agent_client.send(self.get_session_id(chat_id), text)
        except Exception as exc:
            self._console.print(f"[red][error] {exc}[/red]")
            return ""

        self._apply_active_session(reply.get("active_session"))

        # ── StatusSubAgent records ──────────────────────────
        status_records = reply.get("status_sub_agent_records") or []
        if status_records:
            tools_str = ", ".join(
                f"{r['tool_name']}({r['arguments']})"
                for r in status_records
            )
            self._console.print(f"[cyan]  ── StatusSubAgent: {tools_str}[/cyan]")
            for r in status_records:
                preview = str(r.get("result", ""))[:120]
                raw_status = str(r.get("status", ""))
                try:
                    status = StatusSubAgentRecordStatus(raw_status)
                except ValueError:
                    status = None
                if status is not None and status.is_diagnostic_only:
                    self._console.print(
                        f"[yellow]     ↷ [{status.value}] {preview}[/yellow]"
                    )
                elif r.get("success") is False:
                    self._console.print(f"[red]     × {preview}[/red]")
                else:
                    self._console.print(f"[green]     → {preview}[/green]")
            self._console.print("")

        # ── Tool call records ───────────────────────────────
        tool_records = reply.get("tool_records") or []
        if tool_records:
            for i, rec in enumerate(tool_records):
                tool_names = [
                    tc["function"]["name"]
                    for tc in rec.get("tool_calls", [])
                ]
                self._console.print(
                    f"[cyan]  ── tool call [{i + 1}]: {', '.join(tool_names)}[/cyan]",
                )
                if rec.get("reasoning_content"):
                    self._console.print(
                        f"[dim]     [thinking] {rec['reasoning_content'][:200]}[/dim]",
                    )
                for tr in rec.get("tool_results", []):
                    self._console.print(f"[green]     → {tr['content']}[/green]")
            self._console.print("")

        # ── Reply text ──────────────────────────────────────
        reply_text = str(reply.get("reply", ""))
        self._console.print(f"\n{reply_text}\n")
        return reply_text

    def _apply_active_session(self, value: object) -> None:
        active_session = str(value or "").strip()
        if active_session:
            self._session_id_override = active_session

    async def _handle_message(
        self, chat_id: str, user_id: str, text: str,
    ) -> str | None:
        """覆写基类：命令走 agent 统一路径（不走 LLM，不入历史），
        非命令根据 _streaming 分流到流式或缓冲渲染。

        命令分发由 agent 的 ``_send_impl()`` / ``_send_stream_impl()``
        统一处理，所有 channel 共享同一逻辑。"""
        if not self._agent_client:
            return None

        if self._streaming:
            reply_text = await self._stream_and_send(chat_id, text)
        else:
            reply_text = await self._handle_buffered(chat_id, text)
        return reply_text
