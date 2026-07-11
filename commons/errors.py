"""Shared business exceptions used across process boundaries."""

from __future__ import annotations

TURN_METADATA_INVALID_ERROR_CODE = "TURN_METADATA_INVALID"
TURN_METADATA_INVALID_STATUS_CODE = 409

MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE = (
    "MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED"
)
MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE = 409


class InvalidTurnMetadataError(ValueError):
    """Raised when explicit ``turn_id`` / ``seq_in_turn`` metadata is invalid."""


class MainContextWindowThresholdExceededError(RuntimeError):
    """Raised when normal input reaches the configured main-context threshold."""

    def __init__(
        self,
        *,
        used_tokens: int,
        context_limit: int,
        threshold_ratio: float,
    ) -> None:
        self.used_tokens = int(used_tokens)
        self.context_limit = int(context_limit)
        self.threshold_ratio = float(threshold_ratio)
        self.usage_ratio = self.used_tokens / self.context_limit
        super().__init__(
            "主 Agent Context 当前占用 "
            f"{self.used_tokens}/{self.context_limit} tokens（{self.usage_ratio:.1%}），"
            f"已达到 {self.threshold_ratio:.0%} 输入阈值；普通正文已拒绝。"
            "请先执行 /compact 手动压缩，或切换到更大上下文窗口的 LLM。"
        )


def format_turn_metadata_error_message(error: BaseException) -> str:
    """Return the raw error message; stable code is carried separately."""
    return str(error)
