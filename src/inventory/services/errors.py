"""Typed service-layer exceptions with associated HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors.

    Carries an HTTP ``status_code`` so the API layer can translate errors
    into responses in a single place.
    """

    status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(InventoryError):
    """A referenced entity does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state of a resource."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
