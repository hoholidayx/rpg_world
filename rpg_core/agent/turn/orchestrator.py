"""Shared synchronous and streaming orchestration for one Agent turn."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind, TurnStats
from rpg_core.agent.sub_agents import StatusSubAgentPreflightOutcome
from rpg_core.agent.turn.models import TurnRequest, TurnResult
from rpg_core.agent.turn.resolver import PlayerCharacterRequiredError
from rpg_core.context.usage import aggregate_usage_records
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_core.agent.loop import ToolCallRecord
    from rpg_core.agent.turn.factory import TurnRuntimeFactory
    from rpg_core.agent.turn.hooks import PostCommitHooks, TurnDiagnostics
    from rpg_core.agent.turn.planning import TurnPlanResolver
    from rpg_core.agent.turn.preparation import TurnPreparation
    from rpg_core.agent.turn.runtime import TurnRuntime

_TAG = "[TurnOrchestrator]"

SyncRunner = Callable[..., Awaitable[tuple[str, list["ToolCallRecord"]]]]
StreamRunner = Callable[..., AsyncIterator[AgentStreamEvent]]
EventEmitter = Callable[[AgentStreamEvent], Awaitable[None]]
ErrorEmitter = Callable[[BaseException], Awaitable[None]]
EndEmitter = Callable[[], Awaitable[None]]


class TurnOrchestrator:
    """Execute the invariant turn template through explicit collaborators."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        plan_resolver: "TurnPlanResolver",
        runtime_factory: "TurnRuntimeFactory",
        preparation: "TurnPreparation",
        post_commit_hooks: "PostCommitHooks",
        diagnostics: "TurnDiagnostics",
        sync_runner: SyncRunner,
        stream_runner: StreamRunner,
    ) -> None:
        self._session_id = session_id
        self._plan_resolver = plan_resolver
        self._runtime_factory = runtime_factory
        self._preparation = preparation
        self._post_commit_hooks = post_commit_hooks
        self._diagnostics = diagnostics
        self._sync_runner = sync_runner
        self._stream_runner = stream_runner
        self._last_tool_records: list[ToolCallRecord] | None = None

    @property
    def last_tool_records(self) -> list["ToolCallRecord"] | None:
        return self._last_tool_records

    async def execute_sync(self, request: TurnRequest) -> TurnResult:
        runtime: TurnRuntime | None = None
        try:
            runtime = await self._begin_runtime(request)
            prepared = self._preparation.build(runtime)
            reply_text, records = await self._sync_runner(
                provider=runtime.provider,
                tool_registry=prepared.tool_registry,
                messages=prepared.messages,
                schemas=prepared.schemas,
                turn_stats=runtime.stats,
            )
            self._last_tool_records = records
            self._log_diagnostics(
                runtime,
                self._diagnostics.tool_names(records),
            )
            self._finish_stats(runtime.stats, log_calls=True)
            committed_turn_id = runtime.commit(reply_text)
            result = TurnResult(
                text=reply_text,
                tool_records=records,
                status_sub_agent_records=self._status_record_payloads(runtime),
                stats=runtime.stats,
                committed_turn_id=committed_turn_id,
            )
            await self._post_commit_hooks.run()
            return result
        except asyncio.CancelledError as exc:
            logger.opt(exception=exc).warning(
                _TAG + " sync turn cancelled: session_id={}",
                self._session_id(),
            )
            if runtime is not None:
                runtime.discard()
            raise
        except PlayerCharacterRequiredError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).error(
                _TAG + " sync turn failed: session_id={}",
                self._session_id(),
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
            prepared = self._preparation.build(runtime)

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
            self._finish_stats(runtime.stats, log_calls=settings.verbose_logging)
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
            await self._post_commit_hooks.run()
            return result
        except asyncio.CancelledError:
            logger.info(
                _TAG + " stream turn cancelled: session_id={}",
                self._session_id(),
            )
            if runtime is not None:
                runtime.discard()
            raise
        except PlayerCharacterRequiredError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).error(
                _TAG + " stream turn failed: session_id={}",
                self._session_id(),
            )
            if runtime is not None:
                runtime.discard()
            raise
        finally:
            if runtime is not None:
                if not runtime.committed:
                    runtime.discard()
                runtime.close()

    async def _begin_runtime(self, request: TurnRequest) -> "TurnRuntime":
        return await self._runtime_factory.create(
            self._plan_resolver.resolve(request)
        )

    @staticmethod
    async def _emit_preflight_events(
        runtime: "TurnRuntime",
        emit_event: EventEmitter,
    ) -> None:
        result = runtime.preflight_result
        if result is None or not result.records:
            return
        for record in result.records:
            if not record.status.emits_tool_event:
                continue
            await emit_event(
                AgentStreamEvent(
                    kind=StreamEventKind.TOOL_CALL,
                    tool_name=record.tool_name,
                    tool_arguments=record.arguments,
                    content="",
                )
            )
            await emit_event(
                AgentStreamEvent(
                    kind=StreamEventKind.TOOL_RESULT,
                    tool_name=record.tool_name,
                    tool_result=record.result,
                    tool_result_preview=record.result[:200],
                )
            )

    def _log_diagnostics(
        self,
        runtime: "TurnRuntime",
        main_tool_names: list[str],
    ) -> None:
        result = runtime.preflight_result
        self._diagnostics.log_preflight(
            turn_scratch=runtime.scratch,
            preflight_outcome=(
                runtime.preflight_outcome
                or StatusSubAgentPreflightOutcome.NONE
            ),
            state_prewrites_skipped=(
                result.state_prewrites_skipped if result is not None else 0
            ),
            main_tool_names=main_tool_names,
        )

    @staticmethod
    def _status_record_payloads(
        runtime: "TurnRuntime",
    ) -> list[dict[str, object]] | None:
        result = runtime.preflight_result
        if result is None or not result.records:
            return None
        return result.record_payloads()

    @staticmethod
    def _finish_stats(stats: TurnStats, *, log_calls: bool) -> None:
        stats.finished_at = time.monotonic()
        if log_calls and stats.calls:
            logger.info(_TAG + " turn stats: {}", stats.summary())
