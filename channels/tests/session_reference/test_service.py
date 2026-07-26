from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

import pytest

from channels.session_reference import (
    PlotInjectionAnnotation,
    SessionReferenceApplicationService,
    SessionReferenceLocator,
    SessionReferenceNotFoundError,
    SessionReferencePolicy,
    SessionReferenceResource,
    SessionReferenceResourceDisabledError,
    SessionReferenceUnavailableError,
)
from rpg_core.summary.reference import ResolvedSummaryDocument
from rpg_data.model.memory import (
    MemoryEvidence,
    SessionStoryMemory,
    SessionStoryMemoryPage,
    SessionStoryMemoryStats,
)
from rpg_data.model.session_reference import (
    ReferenceDataPage,
    SessionReferenceCharacter,
    SessionReferenceCharacterDetail,
    SessionReferenceCharacterDetailItem,
    SessionReferenceNarrativeOutcomeFact,
    SessionReferencePlotDecisionFact,
    SessionReferenceScope,
    SessionReferenceStatusOrder,
    SessionReferenceStatusTableDetail,
    SessionReferenceStatusTableItem,
    SessionReferenceTurnAnnotationFacts,
)
from rpg_data.model.status import StatusTableDocument, StatusTableRow
from rpg_memory.persistent.reference import (
    PersistentMemoryEvidenceReference,
    PersistentMemoryReferenceItem,
)


LOCATOR = SessionReferenceLocator(
    session_id="s_reference",
    workspace_id="workspace",
    story_id=7,
)


def _page(items, *, page: int, page_size: int):  # noqa: ANN001, ANN202
    start = (page - 1) * page_size
    return ReferenceDataPage(
        items=tuple(items[start : start + page_size]),
        page=page,
        page_size=page_size,
        total=len(items),
    )


class FakeData:
    def __init__(self, *, lifecycle: str = "ready") -> None:
        self.transaction_depth = 0
        self.transaction_entries = 0
        self.scope = SessionReferenceScope(
            locator=LOCATOR,
            lifecycle=lifecycle,
            title="雾港",
            player_character_id=2,
            session_version=4,
            updated_at="scope-updated",
        )
        self.characters = (
            SessionReferenceCharacter(
                id=2,
                name="林晚",
                description="调查员",
                sort_order=0,
                details_count=2,
                metadata_json='{"internal":true}',
                version=3,
                updated_at="character-updated",
            ),
            SessionReferenceCharacter(
                id=3,
                name="伊凡",
                description="守钟人",
                sort_order=1,
            ),
        )
        self.detail_items = (
            SessionReferenceCharacterDetailItem(
                id=20,
                character_id=2,
                name="性格",
            ),
            SessionReferenceCharacterDetailItem(
                id=21,
                character_id=2,
                name="背景",
            ),
        )
        self.details = {
            20: SessionReferenceCharacterDetail(
                id=20,
                character_id=2,
                name="性格",
                content="谨慎但坚定。",
                tags_json='["kind:personality","scope:npc_portrayal"]',
            ),
            21: SessionReferenceCharacterDetail(
                id=21,
                character_id=2,
                name="背景",
                content="来自北境。",
                tags_json='["kind:background"]',
            ),
        }
        self.statuses = (
            SessionReferenceStatusTableItem(
                id=30,
                name="当前场景",
                status_kind="scene",
                associated_character_id=None,
            ),
            SessionReferenceStatusTableItem(
                id=31,
                name="林晚状态",
                status_kind="normal",
                associated_character_id=2,
                associated_character_name="林晚",
            ),
        )
        self.status_detail = SessionReferenceStatusTableDetail(
            **self.statuses[1].__dict__,
            document=StatusTableDocument.from_rows(
                rows=(
                    StatusTableRow(
                        key="信任",
                        value="上升",
                        runtime_key_locked=True,
                        metadata={"internal": True},
                        update_rule="不得展示",
                    ),
                ),
                metadata={"internal": True},
            ),
        )
        self.last_status_order: SessionReferenceStatusOrder | None = None
        self.turn_annotations = SessionReferenceTurnAnnotationFacts(
            turn_id=9,
            outcome=SessionReferenceNarrativeOutcomeFact(
                outcome_code="success_with_cost",
                reason="穿过吊桥",
                actor="林晚",
            ),
            plot_decisions=(
                SessionReferencePlotDecisionFact(
                    decision_id=1,
                    source_kind="outline",
                    decision_status="triggered",
                    event_title="封印异动",
                    directive="描写封印首次异动。",
                ),
                SessionReferencePlotDecisionFact(
                    decision_id=2,
                    source_kind="pool",
                    decision_status="deferred",
                    event_title="暂缓事件",
                    directive="不得展示。",
                ),
                SessionReferencePlotDecisionFact(
                    decision_id=3,
                    source_kind="pool",
                    decision_status="triggered",
                    event_title=None,
                    directive="畸形快照不得展示。",
                ),
            ),
        )

    @contextmanager
    def transaction(self):  # noqa: ANN201
        self.transaction_entries += 1
        self.transaction_depth += 1
        try:
            yield
        finally:
            self.transaction_depth -= 1

    def require_scope(self, locator):  # noqa: ANN001, ANN201
        assert self.transaction_depth > 0
        if locator != LOCATOR:
            raise FileNotFoundError
        return self.scope

    def list_characters(self, locator, *, page, page_size):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        return _page(self.characters, page=page, page_size=page_size)

    def list_character_order_ids(self, locator):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        return tuple(item.id for item in self.characters)

    def get_character(self, locator, character_id):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        return next(
            (item for item in self.characters if item.id == character_id),
            None,
        )

    def list_character_details(
        self,
        locator,
        character_id,
        *,
        page,
        page_size,
    ):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        items = tuple(
            item
            for item in self.detail_items
            if item.character_id == character_id
        )
        return _page(items, page=page, page_size=page_size)

    def get_character_detail(
        self,
        locator,
        character_id,
        detail_id,
    ):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        item = self.details.get(detail_id)
        return (
            item
            if item is not None and item.character_id == character_id
            else None
        )

    def list_status_tables(
        self,
        locator,
        *,
        page,
        page_size,
        character_id=None,
        order=None,
    ):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        self.last_status_order = order
        items = self.statuses
        if character_id is not None:
            items = tuple(
                item
                for item in items
                if item.associated_character_id == character_id
            )
        return _page(items, page=page, page_size=page_size)

    def get_status_table(self, locator, table_id):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        return self.status_detail if table_id == self.status_detail.id else None

    def get_turn_annotation_facts(
        self,
        locator,
        turn_id,
    ):  # noqa: ANN001, ANN201
        self.require_scope(locator)
        if turn_id == self.turn_annotations.turn_id:
            return self.turn_annotations
        return SessionReferenceTurnAnnotationFacts(turn_id=turn_id)


class FakeSummaries:
    documents = (
        ResolvedSummaryDocument(
            summary_id="overall",
            kind="overall",
            title="故事归纳",
            excerpt="整体摘要",
            text="整体正文",
            turn_start=1,
            turn_end=8,
            time="",
            location="雾港",
            characters=("林晚",),
            updated_at="summary-updated",
        ),
        ResolvedSummaryDocument(
            summary_id="2",
            kind="batch",
            title="第二幕",
            excerpt="批次摘要",
            text="批次正文",
            turn_start=5,
            turn_end=8,
            time="雨夜",
            location="钟楼",
            characters=("林晚", "伊凡"),
            updated_at="batch-updated",
        ),
    )

    def list_summaries(self, _locator):  # noqa: ANN001, ANN201
        return self.documents

    def get_summary(self, _locator, summary_id):  # noqa: ANN001, ANN201
        return next(
            (item for item in self.documents if item.summary_id == summary_id),
            None,
        )


class FakeStoryMemories:
    memory = SessionStoryMemory(
        id=40,
        session_id=LOCATOR.session_id,
        turn_id=6,
        text="林晚取得了盐霜钥匙。",
        memory_kind="clue",
        epistemic_status="confirmed",
        salience=0.9,
        source_turn_start=5,
        source_turn_end=6,
        evidence=(
            MemoryEvidence(
                message_id=402,
                turn_id=6,
                message_version=1,
                content_hash="a" * 64,
            ),
        ),
        version=2,
        updated_at="story-memory-updated",
    )

    def list_reference_page(
        self,
        locator,
        *,
        page,
        page_size,
        memory_kind=None,
        dream_processed=None,
    ):  # noqa: ANN001, ANN201
        assert locator == LOCATOR
        del memory_kind, dream_processed
        items = (self.memory,) if page == 1 else ()
        return SessionStoryMemoryPage(
            items=items,
            page=page,
            page_size=page_size,
            total=1,
            stats=SessionStoryMemoryStats(1, 0, 1),
        )

    def get_reference(self, locator, memory_id):  # noqa: ANN001, ANN201
        if locator == LOCATOR and memory_id == self.memory.id:
            return self.memory
        return None


class FakePersistentMemories:
    memory = PersistentMemoryReferenceItem(
        memory_id="persistent-1",
        revision_number=3,
        text="钟楼下方仍封印着潮汐门。",
        memory_kind="world_fact",
        epistemic_status="confirmed",
        salience=0.8,
        evidence=(
            PersistentMemoryEvidenceReference(turn_id=8, message_id=801),
        ),
        updated_at="persistent-updated",
    )

    def list_memories(self, locator):  # noqa: ANN001, ANN201
        return (self.memory,) if locator == LOCATOR else ()

    def get_memory(self, locator, memory_id):  # noqa: ANN001, ANN201
        if locator == LOCATOR and memory_id == self.memory.memory_id:
            return self.memory
        return None


def _service(
    data: FakeData | None = None,
    *,
    policy: SessionReferencePolicy | None = None,
    summaries=None,  # noqa: ANN001
    story_memories=None,  # noqa: ANN001
    persistent_memories=None,  # noqa: ANN001
) -> SessionReferenceApplicationService:
    return SessionReferenceApplicationService(
        data or FakeData(),
        summaries=summaries or FakeSummaries(),
        story_memories=story_memories or FakeStoryMemories(),
        persistent_memories=persistent_memories or FakePersistentMemories(),
        **({} if policy is None else {"policy": policy}),
    )


def test_scope_and_all_five_player_projections() -> None:
    data = FakeData()
    service = _service(data)

    scope = service.get_scope(LOCATOR)
    assert scope.title == "雾港"
    assert scope.player_character_id == 2

    characters = service.list_characters(LOCATOR)
    assert characters.total_pages == 1
    assert characters.items[0].is_player is True
    card = service.get_character(LOCATOR, 2)
    assert card.details_count == 2
    detail = service.get_character_detail(LOCATOR, 2, 20)
    assert detail.content == "谨慎但坚定。"
    assert not hasattr(detail, "tags")
    assert not hasattr(detail, "metadata")

    detail_page = service.list_character_details(
        LOCATOR,
        2,
        page=2,
        page_size=1,
    )
    assert [item.title for item in detail_page.items] == ["背景"]

    status_page = service.list_status_tables(LOCATOR)
    assert [item.id for item in status_page.items] == [30, 31]
    assert data.last_status_order == SessionReferenceStatusOrder(
        status_kind_order=("scene", "normal"),
        ordered_character_ids=(2, 3),
        associated_first=True,
    )
    status = service.get_status_table(LOCATOR, 31)
    assert status.rows[0].key == "信任"
    assert status.rows[0].value == "上升"
    assert not hasattr(status.rows[0], "update_rule")
    assert not hasattr(status.rows[0], "metadata")

    summaries = service.list_summaries(LOCATOR, page_size=1)
    assert summaries.items[0].id == "overall"
    assert service.get_summary(LOCATOR, "2").text == "批次正文"

    story_memories = service.list_story_memories(LOCATOR)
    assert story_memories.items[0].evidence[0].message_id == 402
    story_detail = service.get_story_memory(LOCATOR, 40)
    assert story_detail.text == "林晚取得了盐霜钥匙。"
    assert not hasattr(story_detail.evidence[0], "content_hash")

    persistent = service.list_persistent_memories(LOCATOR)
    assert persistent.items[0].revision_number == 3
    assert persistent.items[0].evidence[0].turn_id == 8
    assert service.get_persistent_memory(
        LOCATOR,
        "persistent-1",
    ).text.startswith("钟楼")


def test_turn_annotations_project_only_player_visible_committed_facts() -> None:
    data = FakeData()
    service = _service(data)

    annotations = service.get_turn_annotations(LOCATOR, 9)

    assert annotations.turn_id == 9
    assert annotations.outcome is not None
    assert annotations.outcome.outcome_code == "success_with_cost"
    assert annotations.outcome.label == "成功但有代价"
    assert annotations.outcome.reason == "穿过吊桥"
    assert annotations.outcome.actor == "林晚"
    assert annotations.plot_injections == (
        PlotInjectionAnnotation(
            event_title="封印异动",
            directive="描写封印首次异动。",
        ),
    )
    assert not hasattr(annotations.outcome, "sample_value")
    assert not hasattr(annotations.outcome, "effective_weights")
    assert not hasattr(annotations.plot_injections[0], "decision_id")
    assert data.transaction_entries == 1
    assert data.transaction_depth == 0


def test_turn_annotations_obey_ready_gate_and_resource_policy() -> None:
    with pytest.raises(SessionReferenceUnavailableError):
        _service(FakeData(lifecycle="deleting")).get_turn_annotations(
            LOCATOR,
            9,
        )

    service = _service(
        policy=SessionReferencePolicy(
            enabled_resources=frozenset({
                SessionReferenceResource.CHARACTERS,
            }),
        )
    )
    with pytest.raises(SessionReferenceResourceDisabledError):
        service.get_turn_annotations(LOCATOR, 9)
    with pytest.raises(ValueError, match="turn_id"):
        _service().get_turn_annotations(LOCATOR, 0)


def test_every_read_rejects_unready_or_wrong_scope() -> None:
    unready = _service(FakeData(lifecycle="provisioning"))
    with pytest.raises(SessionReferenceUnavailableError):
        unready.list_characters(LOCATOR)
    with pytest.raises(SessionReferenceUnavailableError):
        unready.list_persistent_memories(LOCATOR)

    wrong_locator = replace(LOCATOR, workspace_id="other")
    with pytest.raises(SessionReferenceUnavailableError):
        _service().get_scope(wrong_locator)


def test_scoped_missing_items_have_stable_not_found_error() -> None:
    service = _service()

    with pytest.raises(SessionReferenceNotFoundError):
        service.get_character_detail(LOCATOR, 2, 999)
    with pytest.raises(SessionReferenceNotFoundError):
        service.get_status_table(LOCATOR, 999)
    with pytest.raises(SessionReferenceNotFoundError):
        service.get_summary(LOCATOR, "999")
    with pytest.raises(SessionReferenceNotFoundError):
        service.get_story_memory(LOCATOR, 999)
    with pytest.raises(SessionReferenceNotFoundError):
        service.get_persistent_memory(LOCATOR, "missing")


def test_list_pages_distinguish_empty_first_page_from_deleted_later_page() -> None:
    empty_data = FakeData()
    empty_data.characters = ()
    first_page = _service(empty_data).list_characters(
        LOCATOR,
        page=1,
        page_size=1,
    )
    assert first_page.items == ()
    assert first_page.total_pages == 0

    service = _service()
    stale_reads = (
        lambda: service.list_characters(LOCATOR, page=3, page_size=1),
        lambda: service.list_status_tables(LOCATOR, page=3, page_size=1),
        lambda: service.list_summaries(LOCATOR, page=3, page_size=1),
        lambda: service.list_story_memories(LOCATOR, page=2, page_size=1),
        lambda: service.list_persistent_memories(
            LOCATOR,
            page=2,
            page_size=1,
        ),
        lambda: service.list_character_details(
            LOCATOR,
            2,
            page=3,
            page_size=1,
        ),
    )
    for read in stale_reads:
        with pytest.raises(SessionReferenceNotFoundError):
            read()


def test_empty_resources_are_normal_first_pages() -> None:
    data = FakeData()
    data.characters = ()
    data.statuses = ()

    class EmptySummaries(FakeSummaries):
        documents = ()

    class EmptyStoryMemories(FakeStoryMemories):
        def list_reference_page(
            self,
            locator,
            *,
            page,
            page_size,
            memory_kind=None,
            dream_processed=None,
        ):  # noqa: ANN001, ANN201
            del locator, memory_kind, dream_processed
            return SessionStoryMemoryPage(
                items=(),
                page=page,
                page_size=page_size,
                total=0,
                stats=SessionStoryMemoryStats(0, 0, 0),
            )

    class EmptyPersistentMemories(FakePersistentMemories):
        def list_memories(self, locator):  # noqa: ANN001, ANN201
            del locator
            return ()

    service = _service(
        data,
        summaries=EmptySummaries(),
        story_memories=EmptyStoryMemories(),
        persistent_memories=EmptyPersistentMemories(),
    )

    pages = (
        service.list_characters(LOCATOR),
        service.list_status_tables(LOCATOR),
        service.list_summaries(LOCATOR),
        service.list_story_memories(LOCATOR),
        service.list_persistent_memories(LOCATOR),
    )
    assert all(page.items == () and page.total_pages == 0 for page in pages)


def test_provider_failure_does_not_poison_other_resource_reads() -> None:
    class FailingSummaries(FakeSummaries):
        def list_summaries(self, _locator):  # noqa: ANN001, ANN201
            raise RuntimeError("summary unavailable")

    class FailingStoryMemories(FakeStoryMemories):
        def list_reference_page(
            self,
            *args,
            **kwargs,
        ):  # noqa: ANN002, ANN003, ANN201
            raise RuntimeError("story memory unavailable")

    class FailingPersistentMemories(FakePersistentMemories):
        def list_memories(self, _locator):  # noqa: ANN001, ANN201
            raise RuntimeError("persistent memory unavailable")

    summary_data = FakeData()
    summary_failure = _service(summary_data, summaries=FailingSummaries())
    with pytest.raises(RuntimeError, match="summary unavailable"):
        summary_failure.list_summaries(LOCATOR)
    assert summary_data.transaction_depth == 0
    assert summary_failure.list_characters(LOCATOR).total == 2
    assert summary_failure.list_story_memories(LOCATOR).total == 1

    story_data = FakeData()
    story_failure = _service(
        story_data,
        story_memories=FailingStoryMemories(),
    )
    with pytest.raises(RuntimeError, match="story memory unavailable"):
        story_failure.list_story_memories(LOCATOR)
    assert story_data.transaction_depth == 0
    assert story_failure.list_summaries(LOCATOR).total == 2
    assert story_failure.list_persistent_memories(LOCATOR).total == 1

    persistent_data = FakeData()
    persistent_failure = _service(
        persistent_data,
        persistent_memories=FailingPersistentMemories()
    )
    with pytest.raises(RuntimeError, match="persistent memory unavailable"):
        persistent_failure.list_persistent_memories(LOCATOR)
    assert persistent_data.transaction_depth == 0
    assert persistent_failure.list_status_tables(LOCATOR).total == 2
    assert persistent_failure.list_summaries(LOCATOR).total == 2


def test_ready_state_is_fixed_at_snapshot_start() -> None:
    class SnapshotData(FakeData):
        def __init__(self) -> None:
            super().__init__()
            self._snapshot_scope = None

        @contextmanager
        def transaction(self):  # noqa: ANN201
            self.transaction_entries += 1
            self.transaction_depth += 1
            self._snapshot_scope = self.scope
            try:
                yield
            finally:
                self._snapshot_scope = None
                self.transaction_depth -= 1

        def require_scope(self, locator):  # noqa: ANN001, ANN201
            assert self.transaction_depth > 0
            if locator != LOCATOR:
                raise FileNotFoundError
            return self._snapshot_scope

        def list_characters(
            self,
            locator,
            *,
            page,
            page_size,
        ):  # noqa: ANN001, ANN201
            self.scope = replace(self.scope, lifecycle="deleting")
            return super().list_characters(
                locator,
                page=page,
                page_size=page_size,
            )

    data = SnapshotData()
    service = _service(data)

    current = service.list_characters(LOCATOR)

    assert current.total == 2
    assert data.transaction_depth == 0
    with pytest.raises(SessionReferenceUnavailableError):
        service.list_characters(LOCATOR)


def test_turn_annotations_use_ready_state_from_snapshot_start() -> None:
    class SnapshotAnnotationData(FakeData):
        def __init__(self) -> None:
            super().__init__()
            self._snapshot_scope = None

        @contextmanager
        def transaction(self):  # noqa: ANN201
            self.transaction_entries += 1
            self.transaction_depth += 1
            self._snapshot_scope = self.scope
            try:
                yield
            finally:
                self._snapshot_scope = None
                self.transaction_depth -= 1

        def require_scope(self, locator):  # noqa: ANN001, ANN201
            assert self.transaction_depth > 0
            if locator != LOCATOR:
                raise FileNotFoundError
            return self._snapshot_scope

        def get_turn_annotation_facts(
            self,
            locator,
            turn_id,
        ):  # noqa: ANN001, ANN201
            assert locator == LOCATOR
            assert self.transaction_depth == 1
            self.scope = replace(self.scope, lifecycle="deleting")
            return replace(self.turn_annotations, turn_id=turn_id)

    data = SnapshotAnnotationData()
    service = _service(data)

    assert service.get_turn_annotations(LOCATOR, 9).outcome is not None
    assert data.transaction_depth == 0
    with pytest.raises(SessionReferenceUnavailableError):
        service.get_turn_annotations(LOCATOR, 9)


def test_turn_annotation_failure_exits_snapshot_without_poisoning_reads() -> None:
    class FailingAnnotationData(FakeData):
        def get_turn_annotation_facts(
            self,
            locator,
            turn_id,
        ):  # noqa: ANN001, ANN201
            self.require_scope(locator)
            del turn_id
            raise RuntimeError("annotation unavailable")

    data = FailingAnnotationData()
    service = _service(data)

    with pytest.raises(RuntimeError, match="annotation unavailable"):
        service.get_turn_annotations(LOCATOR, 9)
    assert data.transaction_depth == 0
    assert service.list_characters(LOCATOR).total == 2


def test_external_providers_execute_inside_the_reference_snapshot() -> None:
    data = FakeData()

    class TransactionAwareSummaries(FakeSummaries):
        def list_summaries(self, locator):  # noqa: ANN001, ANN201
            assert data.transaction_depth == 1
            return super().list_summaries(locator)

        def get_summary(self, locator, summary_id):  # noqa: ANN001, ANN201
            assert data.transaction_depth == 1
            return super().get_summary(locator, summary_id)

    class TransactionAwareStoryMemories(FakeStoryMemories):
        def list_reference_page(  # noqa: ANN002, ANN003, ANN201
            self,
            *args,
            **kwargs,
        ):
            assert data.transaction_depth == 1
            return super().list_reference_page(*args, **kwargs)

        def get_reference(  # noqa: ANN002, ANN003, ANN201
            self,
            *args,
            **kwargs,
        ):
            assert data.transaction_depth == 1
            return super().get_reference(*args, **kwargs)

    class TransactionAwarePersistentMemories(FakePersistentMemories):
        def list_memories(self, locator):  # noqa: ANN001, ANN201
            assert data.transaction_depth == 1
            return super().list_memories(locator)

        def get_memory(self, locator, memory_id):  # noqa: ANN001, ANN201
            assert data.transaction_depth == 1
            return super().get_memory(locator, memory_id)

    service = _service(
        data,
        summaries=TransactionAwareSummaries(),
        story_memories=TransactionAwareStoryMemories(),
        persistent_memories=TransactionAwarePersistentMemories(),
    )

    service.list_summaries(LOCATOR)
    service.get_summary(LOCATOR, "overall")
    service.list_story_memories(LOCATOR)
    service.get_story_memory(LOCATOR, 40)
    service.list_persistent_memories(LOCATOR)
    service.get_persistent_memory(LOCATOR, "persistent-1")

    assert data.transaction_depth == 0
    assert data.transaction_entries == 6


def test_immutable_policy_can_replace_resource_profile() -> None:
    policy = SessionReferencePolicy(
        enabled_resources=frozenset({SessionReferenceResource.CHARACTERS}),
        max_page_size=4,
    )
    data = FakeData()
    service = _service(data, policy=policy)

    assert service.list_characters(LOCATOR, page_size=4).total == 2
    assert service.get_character(LOCATOR, 2).name == "林晚"
    with pytest.raises(SessionReferenceResourceDisabledError):
        service.list_summaries(LOCATOR, page_size=4)
    with pytest.raises(ValueError, match="page_size"):
        service.list_characters(LOCATOR, page_size=5)
