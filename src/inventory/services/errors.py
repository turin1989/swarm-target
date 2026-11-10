"""Typed service-layer exceptions.

Each exception carries a ``status_code`` so the HTTP layer can map it onto a
response without inspecting error messages.
"""


class InventoryError(Exception):
    """Base class for service-layer errors."""

    status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(InventoryError):
    """A referenced entity does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state (e.g. insufficient stock)."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
