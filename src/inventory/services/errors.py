"""Typed service-layer exceptions that map to HTTP status codes."""


class InventoryError(Exception):
    """Base class for service-layer errors.

    Each subclass carries a ``status_code`` describing the HTTP response
    the error should translate to at the API boundary.
    """

    status_code: int = 500


class NotFoundError(InventoryError):
    """A referenced resource does not exist."""

    status_code = 404


class ConflictError(InventoryError):
    """The request conflicts with the current state of a resource."""

    status_code = 409


class ValidationError(InventoryError):
    """The request is semantically invalid."""

    status_code = 400
