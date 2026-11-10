"""Typed service-layer exceptions that map onto HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors surfaced as HTTP error responses."""

    status_code: int = 400

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(InventoryError):
    """A referenced resource does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with current state (e.g. insufficient stock)."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
