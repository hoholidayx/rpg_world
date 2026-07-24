"""Narrow collaborators injected into the RPG World MCP runtime adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from commons.types import JsonValue
from rpg_data.model.story_pack import StoryPackBinding, StoryPackOperation


class CatalogPort(Protocol):
    def list_workspaces(self) -> list[Any]: ...
    def get_workspace(self, workspace_id: str) -> Any | None: ...
    def create_workspace(
        self,
        workspace_id: str,
        *,
        name: str,
        root_path: str,
        description: str = "",
        enabled: bool = True,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Any: ...
    def list_stories(self, workspace_id: str) -> list[Any] | None: ...
    def get_story(self, workspace_id: str, story_id: int) -> Any | None: ...


class StoryCatalogPort(Protocol):
    def create_story(self, workspace_id: str, **values: Any) -> Any | None: ...
    def update_story(
        self,
        workspace_id: str,
        story_id: int,
        **values: Any,
    ) -> Any | None: ...


class CharacterPort(Protocol):
    def list_characters(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[Any] | None: ...
    def create_character(
        self,
        workspace_id: str,
        story_id: int,
        **values: Any,
    ) -> Any | None: ...
    def update_character(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        **values: Any,
    ) -> Any | None: ...
    def list_details(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
    ) -> list[Any] | None: ...
    def create_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        **values: Any,
    ) -> Any | None: ...
    def update_detail(
        self,
        workspace_id: str,
        story_id: int,
        character_id: int,
        detail_id: int,
        **values: Any,
    ) -> Any | None: ...


class LorebookPort(Protocol):
    def list_entries(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[Any] | None: ...
    def create_entry(
        self,
        workspace_id: str,
        story_id: int,
        **values: Any,
    ) -> Any | None: ...
    def update_entry(
        self,
        workspace_id: str,
        story_id: int,
        entry_id: int,
        **values: Any,
    ) -> Any | None: ...


class StatusPort(Protocol):
    def list_story_tables(
        self,
        workspace_id: str,
        story_id: int,
        *,
        status_kind: str | None = None,
    ) -> list[Any]: ...
    def create_story_table(
        self,
        workspace_id: str,
        story_id: int,
        name: str,
        **values: Any,
    ) -> Any: ...
    def update_story_table(
        self,
        workspace_id: str,
        story_id: int,
        story_status_table_id: int,
        **values: Any,
    ) -> Any: ...


class ComposerPort(Protocol):
    def list_styles(self, workspace_id: str) -> list[Any] | None: ...
    def create_style(self, workspace_id: str, **values: Any) -> Any | None: ...
    def update_style(
        self,
        workspace_id: str,
        style_id: int,
        **values: Any,
    ) -> Any | None: ...
    def list_story_styles(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[Any] | None: ...
    def mount_story_style(
        self,
        workspace_id: str,
        story_id: int,
        style_id: int,
    ) -> Any | None: ...
    def set_story_base_style(
        self,
        workspace_id: str,
        story_id: int,
        mount_id: int | None,
    ) -> Any | None: ...
    def list_quick_replies(
        self,
        workspace_id: str,
        story_id: int,
        *,
        enabled_only: bool = False,
    ) -> list[Any] | None: ...
    def create_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        **values: Any,
    ) -> Any | None: ...
    def update_quick_reply(
        self,
        workspace_id: str,
        story_id: int,
        reply_id: int,
        **values: Any,
    ) -> Any | None: ...


class RPModuleApplicationPort(Protocol):
    def patch_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
        *,
        enabled: bool | None,
        config: Mapping[str, JsonValue] | None,
    ) -> Any | None: ...


class RPModuleDataPort(Protocol):
    def list_catalog(self) -> list[Any]: ...
    def list_story_modules(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[Any] | None: ...
    def get_story_module(
        self,
        workspace_id: str,
        story_id: int,
        module_name: str,
    ) -> Any | None: ...


class PlotPort(Protocol):
    def get_story_schedule(
        self,
        workspace_id: str,
        story_id: int,
    ) -> Any | None: ...
    def create_pool(self, command: Any) -> Any: ...
    def update_pool(self, command: Any) -> Any: ...
    def create_event(self, command: Any) -> Any: ...
    def update_event(self, command: Any) -> Any: ...
    def create_outline(self, command: Any) -> Any: ...
    def update_outline(self, command: Any) -> Any: ...
    def create_node(self, command: Any) -> Any: ...
    def update_node(self, command: Any) -> Any: ...


class StoryPackLedgerPort(Protocol):
    def get_binding(
        self,
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        source_id: str,
    ) -> StoryPackBinding | None: ...
    def list_bindings(
        self,
        workspace_id: str,
        story_id: int,
        *,
        resource_kind: str | None = None,
    ) -> list[StoryPackBinding]: ...
    def find_bindings(
        self,
        workspace_id: str,
        resource_kind: str,
        source_id: str,
    ) -> list[StoryPackBinding]: ...
    def upsert_binding(
        self,
        workspace_id: str,
        story_id: int,
        resource_kind: str,
        source_id: str,
        **values: Any,
    ) -> StoryPackBinding: ...
    def create_operation(self, operation_id: str, **values: Any) -> StoryPackOperation: ...
    def get_operation(self, operation_id: str) -> StoryPackOperation | None: ...
    def find_completed_operation(
        self,
        workspace_id: str,
        story_stable_id: str,
        pack_digest: str,
        *,
        operation_kind: str,
    ) -> StoryPackOperation | None: ...
    def claim_operation(self, operation_id: str) -> StoryPackOperation | None: ...
    def complete_operation(
        self,
        operation_id: str,
        *,
        story_id: int,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None: ...
    def update_applied_result(
        self,
        operation_id: str,
        *,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None: ...
    def mark_local_sync_pending(
        self,
        operation_id: str,
        *,
        error_message: str,
    ) -> StoryPackOperation | None: ...
    def mark_local_sync_complete(
        self,
        operation_id: str,
        *,
        result: Mapping[str, JsonValue],
    ) -> StoryPackOperation | None: ...
    def fail_operation(
        self,
        operation_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> StoryPackOperation | None: ...


@dataclass(frozen=True)
class RuntimeServices:
    transaction: Callable[[], AbstractContextManager[None]]
    catalog: CatalogPort
    stories: StoryCatalogPort
    characters: CharacterPort
    lorebook: LorebookPort
    status: StatusPort
    composer: ComposerPort
    rp_modules: RPModuleApplicationPort
    rp_module_data: RPModuleDataPort
    plot: PlotPort
    story_packs: StoryPackLedgerPort


__all__ = ["RuntimeServices"]
