"""Typed service-layer exceptions mapped to HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors carrying an HTTP status code."""

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(InventoryError):
    """Raised when a referenced resource does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """Raised when a request conflicts with existing state."""

    status_code = 409


class ValidationError(InventoryError):
    """Raised when a request is semantically invalid."""

    status_code = 400
