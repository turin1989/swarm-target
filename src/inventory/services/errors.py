"""Typed service-layer exceptions."""


class InventoryError(Exception):
    """Base class for service-layer errors carrying an HTTP status code."""

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(InventoryError):
    """Raised when a referenced entity does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """Raised when a request conflicts with the current state."""

    status_code = 409


class ValidationError(InventoryError):
    """Raised when a request is semantically invalid."""

    status_code = 400
