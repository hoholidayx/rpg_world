"""Stable errors returned by the lightweight-channel reference boundary."""

from __future__ import annotations


class SessionReferenceError(RuntimeError):
    """Base class for expected reference-reader failures."""


class SessionReferenceUnavailableError(SessionReferenceError):
    """The requested Session is missing, unready, or outside the locator scope."""


class SessionReferenceNotFoundError(SessionReferenceError):
    """A scoped item disappeared or is no longer visible."""


class SessionReferenceResourceDisabledError(SessionReferenceError):
    """The selected immutable policy does not expose this resource."""


class SessionReferenceReaderClosedError(SessionReferenceError):
    """The async reader is already closing or closed."""


__all__ = [
    "SessionReferenceError",
    "SessionReferenceNotFoundError",
    "SessionReferenceReaderClosedError",
    "SessionReferenceResourceDisabledError",
    "SessionReferenceUnavailableError",
]
