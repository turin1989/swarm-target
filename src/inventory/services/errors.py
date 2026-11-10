"""Typed service-layer exceptions.

Each exception carries an HTTP-ish ``status_code`` so the API layer can map
them to responses in a single place.
"""


class InventoryError(Exception):
    """Base class for service-layer errors."""

    status_code: int = 400

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(InventoryError):
    """A referenced entity does not exist (404)."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state (409)."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid (400)."""

    status_code = 400
