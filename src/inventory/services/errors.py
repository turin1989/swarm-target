"""Typed service-layer exceptions.

Each exception carries a ``status_code`` so the HTTP layer can map errors to
responses in a single place without inspecting messages.
"""


class InventoryError(Exception):
    """Base class for service-layer errors."""

    status_code: int = 400


class NotFoundError(InventoryError):
    """A referenced entity does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state of the system."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
