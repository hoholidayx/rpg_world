"""Immutable message-mode presentation and player-portrayal inputs."""

from __future__ import annotations

from dataclasses import dataclass

from commons.errors import MessageModeUnavailableError
from rpg_core.rp_modules.constants import RP_MODULE_MESSAGE_MODE_NAME
from rpg_core.rp_modules.models import RPModuleSelectionSnapshot
from rpg_core.session.modes import TurnMode


@dataclass(frozen=True)
class MessageModeOption:
    mode: TurnMode
    short_name: str
    sort_order: int


MESSAGE_MODE_OPTIONS = (
    MessageModeOption(TurnMode.NEUTRAL, "默认", 0),
    MessageModeOption(TurnMode.IC, "角色内", 10),
    MessageModeOption(TurnMode.OOC, "场外", 20),
    MessageModeOption(TurnMode.GM, "主持", 30),
)


def ensure_message_mode_available(
    snapshot: RPModuleSelectionSnapshot,
    mode: TurnMode,
) -> None:
    """Reject explicit guided modes unless the built-in module is effective."""

    if mode is TurnMode.NEUTRAL:
        return
    selected = snapshot.get(RP_MODULE_MESSAGE_MODE_NAME)
    if selected is None or not selected.effective_enabled:
        raise MessageModeUnavailableError(mode.value)
