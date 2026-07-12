"""Shared synchronous and streaming orchestration for one Agent turn."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.transaction import AgentTurnTransaction
from rpg_core.agent.turn.models import TurnExecutionPlan, TurnRequest, TurnResult
from rpg_core.agent.turn.preparation import TurnPreparation
from rpg_core.agent.turn.runtime import TurnRuntime
from rpg_core.context.usage import aggregate_usage_records
from rpg_core.settings import settings

if TYPE_CHECKING:
    from llm_service.base_provider import LLMProvider
    from rpg_core.agent.loop import ToolCallRecord
    from rpg_core.agent.sub_agents import (
        StatusSubAgentPreflightOutcome,
        StatusSubAgentResult,
    )
    from rpg_core.agent.tools import ToolRegistry
    from rpg_core.agent.turn.models import TurnExecutionSnapshot
    from rpg_core.context.rpg_context import Message
    from rpg_core.main_llm import MainLLMSelection
    from rpg_core.rp_modules import (
        RPModuleRegistry,
        RPModuleSelectionSnapshot,
        RPModuleTurnRuntime,
    )
    from rpg_core.scene import SceneTracker
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager
    from rp_memory.memory_manager import MemoryManager

_TAG = "[TurnOrchestrator]"

SyncRunner = Callable[..., Awaitable[tuple[str, list["ToolCallRecord"]]]]
StreamRunner = Callable[..., AsyncIterator[AgentStreamEvent]]
EventEmitter = Callable[[AgentStreamEvent], Awaitable[None]]
ErrorEmitter = Callable[[BaseException], Awaitable[None]]
EndEmitter = Callable[[], Awaitable[None]]


class TurnHost(Protocol):
    """Narrow host surface used by the turn pipeline.

    The protocol intentionally contains existing Agent collaborators.  It lets
    the orchestration move out without moving session initialization or the
    context subsystem into the same module.
    """

    _session_id: str
    _session: "SessionManager"
    _status_mgr: "StatusManager | None"
    _scene_tracker: "SceneTracker | None"
    _rp_module_registry: "RPModuleRegistry | None"
    _memory_manager: "MemoryManager | None"
    _last_tool_records: list["ToolCallRecord"] | None

    def _resolve_turn_execution_snapshot(
        self,
        request: TurnRequest,
    ) -> "TurnExecutionSnapshot": ...
    def _resolve_main_llm_selection(self) -> "MainLLMSelection": ...
    def _resolve_rp_module_snapshot(self) -> "RPModuleSelectionSnapshot": ...
    def _enforce_main_context_window_threshold(
        self,
        selection: "MainLLMSelection",
        **kwargs,
    ) -> None: ...
    def _refresh_main_provider(
        self,
        *,
        selection: "MainLLMSelection",
    ) -> "LLMProvider": ...
    def _compose_stored_user_input(self, scene_ctx: str | None, user_input: str) -> str: ...
    def _build_transformed_context(self, **kwargs) -> list["Message"]: ...
    def _tool_registry_for_turn(self, *args, **kwargs) -> "ToolRegistry | None": ...
    def _main_tool_schemas(self, registry, **kwargs) -> list[dict] | None: ...
    async def _run_status_preflight(self, **kwargs) -> "StatusSubAgentResult | None": ...
    def _preflight_outcome_state(
        self,
        *args,
    ) -> "StatusSubAgentPreflightOutcome": ...
    def _log_turn_preflight_diagnostics(self, **kwargs) -> None: ...
    def _tool_names_from_records(self, records) -> list[str]: ...
    async def _run_post_commit_side_effects(self) -> None: ...


class TurnOrchestrator:
    """Execute the invariant turn template for both output protocols."""

    def __init__(
        self,
        host: TurnHost,
        *,
        sync_runner: SyncRunner,
        stream_runner: StreamRunner,
    ) -> None:
        self._host = host
        self._sync_runner = sync_runner
        self._stream_runner = stream_runner

    async def execute_sync(self, request: TurnRequest) -> TurnResult:
        runtime: TurnRuntime | None = None
        try:
            runtime = await self._begin_runtime(request)
            prepared = TurnPreparation(self._host).build(runtime)
            reply_text, records = await self._sync_runner(
                provider=runtime.provider,
                tool_registry=prepared.tool_registry,
                messages=prepared.messages,
                schemas=prepared.schemas,
                turn_stats=runtime.stats,
            )
            self._host._last_tool_records = records
            self._log_diagnostics(runtime, self._host._tool_names_from_records(records))
            self._finish_stats(runtime.stats, log_calls=True)
            committed_turn_id = runtime.commit(reply_text)
            result = TurnResult(
                text=reply_text,
                tool_records=records,
                status_sub_agent_records=self._status_record_payloads(runtime),
                stats=runtime.stats,
                committed_turn_id=committed_turn_id,
            )
            await self._host._run_post_commit_side_effects()
            return result
        except asyncio.CancelledError as exc:
            logger.opt(exception=exc).warning(
                _TAG + " sync turn cancelled: session_id={}",
                self._host._session_id,
            )
            if runtime is not None:
                runtime.discard()
            raise
        except Exception as exc:
            logger.opt(exception=exc).error(
                _TAG + " sync turn failed: session_id={}",
                self._host._session_id,
            )
            if runtime is not None:
                runtime.discard()
            raise
        finally:
            if runtime is not None:
                runtime.close()

    async def execute_stream(
        self,
        request: TurnRequest,
        *,
        emit_event: EventEmitter,
        emit_error: ErrorEmitter,
        emit_end: EndEmitter,
    ) -> TurnResult | None:
        runtime: TurnRuntime | None = None
        try:
            runtime = await self._begin_runtime(request)
            await self._emit_preflight_events(runtime, emit_event)
            prepared = TurnPreparation(self._host).build(runtime)

            final_event: AgentStreamEvent | None = None
            stream_failed = False
            main_tool_names: list[str] = []
            try:
                async for event in self._stream_runner(
                    provider=runtime.provider,
                    tool_registry=prepared.tool_registry,
                    messages=prepared.messages,
                    schemas=prepared.schemas,
                    turn_stats=runtime.stats,
                ):
                    if event.kind == StreamEventKind.DONE:
                        final_event = event
                        continue
                    if event.kind == StreamEventKind.TOOL_CALL and event.tool_name:
                        main_tool_names.append(event.tool_name)
                    if event.kind == StreamEventKind.ERROR:
                        stream_failed = True
                    await emit_event(event)
            except Exception as exc:
                logger.opt(exception=exc).error(_TAG + " stream runner failed")
                await emit_error(exc)
                return None

            if stream_failed:
                await emit_end()
                return None
            if final_event is None:
                await emit_error(RuntimeError("LLM stream ended without a DONE event"))
                return None

            self._log_diagnostics(runtime, main_tool_names)
            self._finish_stats(
                runtime.stats,
                log_calls=settings.verbose_logging,
            )
            try:
                committed_turn_id = runtime.commit(final_event.content)
            except Exception as exc:
                logger.opt(exception=exc).error(_TAG + " stream commit failed")
                await emit_error(exc)
                return None

            final_event.duration_ms = runtime.stats.total_duration_ms
            final_event.usage = aggregate_usage_records(runtime.stats.calls)
            final_event.stats = runtime.stats
            final_event.committed_turn_id = committed_turn_id
            result = TurnResult(
                text=final_event.content,
                tool_records=[],
                status_sub_agent_records=self._status_record_payloads(runtime),
                stats=runtime.stats,
                committed_turn_id=committed_turn_id,
            )
            await emit_event(final_event)
            await emit_end()
            await self._host._run_post_commit_side_effects()
            return result
        except asyncio.CancelledError:
            logger.info(
                _TAG + " stream turn cancelled: session_id={}",
                self._host._session_id,
            )
            if runtime is not None:
                runtime.discard()
            raise
        except Exception as exc:
            logger.opt(exception=exc).error(
                _TAG + " stream turn failed: session_id={}",
                self._host._session_id,
            )
            if runtime is not None:
                runtime.discard()
            raise
        finally:
            if runtime is not None:
                if not runtime.committed:
                    runtime.discard()
                runtime.close()

    async def _begin_runtime(self, request: TurnRequest) -> TurnRuntime:
        execution = self._host._resolve_turn_execution_snapshot(request)
        main_llm = self._host._resolve_main_llm_selection()
        rp_modules = self._host._resolve_rp_module_snapshot()
        plan = TurnExecutionPlan(
            execution=execution,
            main_llm=main_llm,
            rp_modules=rp_modules,
        )
        self._host._enforce_main_context_window_threshold(
            main_llm,
            rp_module_snapshot=rp_modules,
            turn_execution=execution,
        )
        provider: LLMProvider = self._host._refresh_main_provider(selection=main_llm)
        stats = TurnStats(started_at=time.monotonic())
        transaction = AgentTurnTransaction(
            session=self._host._session,
            status_mgr=self._host._status_mgr,
            scene_tracker=self._host._scene_tracker,
        )
        scratch = transaction.begin(stats, mode=request.mode)
        runtime = TurnRuntime(
            plan=plan,
            transaction=transaction,
            scratch=scratch,
            stats=stats,
            provider=provider,
        )
        try:
            registry = self._host._rp_module_registry
            if registry is not None:
                rp_runtime: RPModuleTurnRuntime = registry.create_runtime(rp_modules)
                runtime.rp_module_runtime = rp_runtime
                rp_runtime.bind_turn(scratch)
            if execution.policy.run_status_preflight:
                runtime.preflight_result = await self._host._run_status_preflight(
                    turn_scratch=scratch,
                    user_input=request.text,
                    turn_stats=stats,
                    rp_module_runtime=runtime.rp_module_runtime,
                )
            runtime.preflight_outcome = self._host._preflight_outcome_state(
                scratch,
                runtime.preflight_result,
            )
            return runtime
        except BaseException:
            runtime.discard()
            runtime.close()
            raise

    async def _emit_preflight_events(
        self,
        runtime: TurnRuntime,
        emit_event: EventEmitter,
    ) -> None:
        result = runtime.preflight_result
        if result is None or not result.records:
            return
        for record in result.records:
            if not record.status.emits_tool_event:
                continue
            await emit_event(AgentStreamEvent(
                kind=StreamEventKind.TOOL_CALL,
                tool_name=record.tool_name,
                tool_arguments=record.arguments,
                content="",
            ))
            await emit_event(AgentStreamEvent(
                kind=StreamEventKind.TOOL_RESULT,
                tool_name=record.tool_name,
                tool_result=record.result,
                tool_result_preview=record.result[:200],
            ))

    def _log_diagnostics(self, runtime: TurnRuntime, main_tool_names: list[str]) -> None:
        result = runtime.preflight_result
        self._host._log_turn_preflight_diagnostics(
            turn_scratch=runtime.scratch,
            preflight_outcome=runtime.preflight_outcome,
            state_prewrites_skipped=(
                result.state_prewrites_skipped if result is not None else 0
            ),
            main_tool_names=main_tool_names,
        )

    @staticmethod
    def _status_record_payloads(runtime: TurnRuntime) -> list[dict[str, object]] | None:
        result = runtime.preflight_result
        if result is None or not result.records:
            return None
        return result.record_payloads()

    @staticmethod
    def _finish_stats(stats: TurnStats, *, log_calls: bool) -> None:
        stats.finished_at = time.monotonic()
        if log_calls and stats.calls:
            logger.info(_TAG + " turn stats: {}", stats.summary())
