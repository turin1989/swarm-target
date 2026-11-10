"""Typed domain exceptions shared by the service layer.

Each exception carries a ``status_code`` so the HTTP layer can translate
domain failures into responses in a single place.
"""


class InventoryError(Exception):
    """Base class for domain errors raised by the service layer."""

    status_code: int = 500

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(InventoryError):
    """A referenced entity does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state (e.g. insufficient stock)."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
