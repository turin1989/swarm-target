"""Typed service-layer exceptions mapped to HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors.

    Each subclass carries a ``status_code`` describing the HTTP status the
    error should be rendered as by the API layer.
    """

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(InventoryError):
    """A referenced resource does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with existing state."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
