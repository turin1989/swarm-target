"""Typed service-layer exceptions carrying HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors.

    Each instance carries a ``status_code`` describing the HTTP status the
    error maps onto. Subclasses provide sensible defaults, which can be
    overridden per-instance when needed.
    """

    status_code: int = 400

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(InventoryError):
    """A referenced resource does not exist (404)."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state (409)."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid (400)."""

    status_code = 400
