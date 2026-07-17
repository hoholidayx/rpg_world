"""Independent Dream memory HTTP service and client."""

from dream_service.client import (
    DreamClient,
    DreamClientError,
    DreamServiceUnavailable,
)

__all__ = ["DreamClient", "DreamClientError", "DreamServiceUnavailable"]
