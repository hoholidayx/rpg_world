"""Committed-turn annotation projection and Telegram delivery."""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from typing import Protocol

from loguru import logger

from channels.session_reference import (
    CommittedTurnAnnotations,
    SessionReferenceLocator,
    SessionReferenceReader,
)
from channels.telegram.render import chunk_rendered_text

_TELEGRAM_MAX_MESSAGE_LENGTH = 4096


class TelegramTurnAnnotationPresenter(Protocol):
    async def send_html(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: object | None = None,
        terminal: bool = False,
    ) -> int | None: ...


@dataclass(frozen=True)
class RenderedTurnAnnotationCards:
    outcome_chunks: tuple[str, ...] = ()
    plot_chunks: tuple[str, ...] = ()


class TelegramTurnAnnotationFlow:
    """Read one committed turn and deliver optional supplemental cards."""

    def __init__(
        self,
        *,
        reader: SessionReferenceReader,
        presenter: TelegramTurnAnnotationPresenter,
        workspace_id: str,
        story_id: int,
    ) -> None:
        self._reader = reader
        self._presenter = presenter
        self._workspace_id = str(workspace_id)
        self._story_id = int(story_id)

    async def present(
        self,
        *,
        chat_id: str,
        session_id: str,
        turn_id: int,
    ) -> None:
        locator = SessionReferenceLocator(
            session_id=str(session_id),
            workspace_id=self._workspace_id,
            story_id=self._story_id,
        )
        try:
            annotations = await self._reader.get_turn_annotations(
                locator,
                int(turn_id),
            )
        except Exception:
            logger.exception(
                "telegram: committed turn annotations unavailable "
                "chat_id={} session_id={} turn_id={}",
                chat_id,
                session_id,
                turn_id,
            )
            return

        cards = render_turn_annotation_cards(annotations)
        await self._send_card_chunks(
            chat_id,
            session_id=session_id,
            turn_id=turn_id,
            kind="outcome",
            chunks=cards.outcome_chunks,
        )
        await self._send_card_chunks(
            chat_id,
            session_id=session_id,
            turn_id=turn_id,
            kind="plot",
            chunks=cards.plot_chunks,
        )

    async def _send_card_chunks(
        self,
        chat_id: str,
        *,
        session_id: str,
        turn_id: int,
        kind: str,
        chunks: tuple[str, ...],
    ) -> None:
        for index, chunk in enumerate(chunks):
            try:
                sent_id = await self._presenter.send_html(
                    chat_id,
                    chunk,
                    terminal=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "telegram: committed turn annotation delivery raised "
                    "chat_id={} session_id={} turn_id={} kind={} "
                    "chunk_index={}",
                    chat_id,
                    session_id,
                    turn_id,
                    kind,
                    index,
                )
                return
            if sent_id is not None:
                continue
            logger.warning(
                "telegram: committed turn annotation delivery failed "
                "chat_id={} session_id={} turn_id={} kind={} chunk_index={}",
                chat_id,
                session_id,
                turn_id,
                kind,
                index,
            )
            return


def render_turn_annotation_cards(
    annotations: CommittedTurnAnnotations,
) -> RenderedTurnAnnotationCards:
    outcome_html = ""
    if annotations.outcome is not None:
        outcome = annotations.outcome
        lines = [
            "<b>🎲 剧情裁定 · "
            f"{_escaped_inline(outcome.label)}</b>",
        ]
        if outcome.actor:
            lines.append(f"角色：{_escaped_inline(outcome.actor)}")
        reason = _escaped_body(outcome.reason)
        if reason:
            lines.extend(("", reason))
        outcome_html = "\n".join(lines)

    plot_html = ""
    if annotations.plot_injections:
        blocks = ["<b>🧭 剧情注入 · 已注入本轮</b>"]
        for injection in annotations.plot_injections:
            title = _escaped_inline(injection.event_title)
            directive = _escaped_body(injection.directive)
            if not title or not directive:
                continue
            blocks.append(f"<b>{title}</b>\n{directive}")
        if len(blocks) > 1:
            plot_html = "\n\n".join(blocks)

    return RenderedTurnAnnotationCards(
        outcome_chunks=_safe_chunks(outcome_html),
        plot_chunks=_safe_chunks(plot_html),
    )


def _safe_chunks(rendered: str) -> tuple[str, ...]:
    if not rendered:
        return ()
    chunks = tuple(chunk_rendered_text(rendered))
    if any(len(chunk) > _TELEGRAM_MAX_MESSAGE_LENGTH for chunk in chunks):
        raise AssertionError("Telegram annotation chunk exceeds 4096 characters")
    return chunks


def _escaped_inline(value: object) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return html.escape(normalized, quote=False)


def _escaped_body(value: object) -> str:
    source = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [
        re.sub(r"[^\S\n]+", " ", line).strip()
        for line in source.split("\n")
    ]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            normalized.append(line)
            previous_blank = False
        elif normalized and not previous_blank:
            normalized.append("")
            previous_blank = True
    while normalized and not normalized[-1]:
        normalized.pop()
    return html.escape("\n".join(normalized), quote=False)


__all__ = [
    "RenderedTurnAnnotationCards",
    "TelegramTurnAnnotationFlow",
    "render_turn_annotation_cards",
]
