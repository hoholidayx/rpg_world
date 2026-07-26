from __future__ import annotations

from channels.session_reference import (
    CommittedTurnAnnotations,
    NarrativeOutcomeAnnotation,
    PlotInjectionAnnotation,
)
from channels.telegram.turn_annotation_flow import (
    TelegramTurnAnnotationFlow,
    render_turn_annotation_cards,
)


class _Reader:
    def __init__(
        self,
        annotations: CommittedTurnAnnotations | None = None,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.annotations = annotations or CommittedTurnAnnotations(turn_id=1)
        self.failure = failure
        self.calls = []

    async def get_turn_annotations(self, locator, turn_id):  # noqa: ANN001, ANN201
        self.calls.append((locator, turn_id))
        if self.failure is not None:
            raise self.failure
        return self.annotations


class _Presenter:
    def __init__(
        self,
        *,
        failed_attempts: set[int] | None = None,
        raised_attempts: set[int] | None = None,
    ) -> None:
        self.failed_attempts = failed_attempts or set()
        self.raised_attempts = raised_attempts or set()
        self.attempts: list[tuple[str, str, bool]] = []

    async def send_html(
        self,
        chat_id,
        text,
        *,
        reply_markup=None,
        terminal=False,
    ):  # noqa: ANN001, ANN201
        del reply_markup
        self.attempts.append((chat_id, text, terminal))
        if len(self.attempts) in self.raised_attempts:
            raise RuntimeError("Telegram send failed")
        if len(self.attempts) in self.failed_attempts:
            return None
        return len(self.attempts)


def _annotations() -> CommittedTurnAnnotations:
    return CommittedTurnAnnotations(
        turn_id=9,
        outcome=NarrativeOutcomeAnnotation(
            outcome_code="success_with_cost",
            label="成功但有代价",
            reason="穿过霜藤，但惊动了守卫。",
            actor="Bob",
        ),
        plot_injections=(
            PlotInjectionAnnotation(
                event_title="封印异动",
                directive="描写祭坛封印出现第一次明确异动。",
            ),
            PlotInjectionAnnotation(
                event_title="林间钟声",
                directive="让远处的钟声打断当前对话。",
            ),
        ),
    )


def test_annotation_renderer_escapes_all_dynamic_fields_without_markdown() -> None:
    cards = render_turn_annotation_cards(
        CommittedTurnAnnotations(
            turn_id=9,
            outcome=NarrativeOutcomeAnnotation(
                outcome_code="success",
                label="[成功",
                reason="](tg://user?id=1) <i>reason</i>",
                actor="<b>Alice</b>",
            ),
            plot_injections=(
                PlotInjectionAnnotation(
                    event_title="**[事件**",
                    directive="](https://example.com) <a href='x'>link</a>",
                ),
            ),
        )
    )

    rendered = "\n".join(cards.outcome_chunks + cards.plot_chunks)
    assert "<a " not in rendered
    assert "<i>" not in rendered
    assert "tg://user?id=1" in rendered
    assert "&lt;i&gt;reason&lt;/i&gt;" in rendered
    assert "&lt;b&gt;Alice&lt;/b&gt;" in rendered
    assert "&lt;a href='x'&gt;link&lt;/a&gt;" in rendered
    assert "**[事件**" in rendered
    assert all(len(chunk) <= 4096 for chunk in cards.outcome_chunks)
    assert all(len(chunk) <= 4096 for chunk in cards.plot_chunks)


def test_annotation_renderer_chunks_long_cards_without_truncation() -> None:
    reason = "裁定正文" * 1400
    directive = "剧情指令" * 1400
    cards = render_turn_annotation_cards(
        CommittedTurnAnnotations(
            turn_id=9,
            outcome=NarrativeOutcomeAnnotation(
                outcome_code="success",
                label="成功",
                reason=reason,
            ),
            plot_injections=(
                PlotInjectionAnnotation(
                    event_title="超长事件",
                    directive=directive,
                ),
            ),
        )
    )

    assert len(cards.outcome_chunks) > 1
    assert len(cards.plot_chunks) > 1
    assert all(
        len(chunk) <= 4096
        for chunk in cards.outcome_chunks + cards.plot_chunks
    )
    assert reason in "".join(cards.outcome_chunks)
    assert directive in "".join(cards.plot_chunks)


async def test_annotation_flow_sends_outcome_then_aggregated_plot() -> None:
    reader = _Reader(_annotations())
    presenter = _Presenter()
    flow = TelegramTurnAnnotationFlow(
        reader=reader,  # type: ignore[arg-type]
        presenter=presenter,
        workspace_id="workspace",
        story_id=7,
    )

    await flow.present(chat_id="42", session_id="s_committed", turn_id=9)

    assert len(reader.calls) == 1
    locator, turn_id = reader.calls[0]
    assert (
        locator.session_id,
        locator.workspace_id,
        locator.story_id,
        turn_id,
    ) == ("s_committed", "workspace", 7, 9)
    assert len(presenter.attempts) == 2
    assert "🎲 剧情裁定" in presenter.attempts[0][1]
    assert "🧭 剧情注入" in presenter.attempts[1][1]
    assert "封印异动" in presenter.attempts[1][1]
    assert "林间钟声" in presenter.attempts[1][1]
    assert all(item[2] is True for item in presenter.attempts)


async def test_outcome_delivery_failure_does_not_suppress_plot() -> None:
    presenter = _Presenter(failed_attempts={1})
    flow = TelegramTurnAnnotationFlow(
        reader=_Reader(_annotations()),  # type: ignore[arg-type]
        presenter=presenter,
        workspace_id="workspace",
        story_id=7,
    )

    await flow.present(chat_id="42", session_id="s_committed", turn_id=9)

    assert len(presenter.attempts) == 2
    assert "🎲 剧情裁定" in presenter.attempts[0][1]
    assert "🧭 剧情注入" in presenter.attempts[1][1]


async def test_outcome_delivery_exception_does_not_suppress_plot() -> None:
    presenter = _Presenter(raised_attempts={1})
    flow = TelegramTurnAnnotationFlow(
        reader=_Reader(_annotations()),  # type: ignore[arg-type]
        presenter=presenter,
        workspace_id="workspace",
        story_id=7,
    )

    await flow.present(chat_id="42", session_id="s_committed", turn_id=9)

    assert len(presenter.attempts) == 2
    assert "🎲 剧情裁定" in presenter.attempts[0][1]
    assert "🧭 剧情注入" in presenter.attempts[1][1]


async def test_annotation_read_failure_is_silent_to_chat() -> None:
    presenter = _Presenter()
    flow = TelegramTurnAnnotationFlow(
        reader=_Reader(failure=RuntimeError("database unavailable")),  # type: ignore[arg-type]
        presenter=presenter,
        workspace_id="workspace",
        story_id=7,
    )

    await flow.present(chat_id="42", session_id="s_committed", turn_id=9)

    assert presenter.attempts == []
