class ConcurrencyConflictError(Exception):
    """Raised when an optimistic concurrency check fails."""


class NotFoundError(Exception):
    """Raised when an entity cannot be found."""


class ConflictError(Exception):
    """Raised when the operation conflicts with current state."""


class BadRequestError(Exception):
    """Raised when request data fails domain-level validation."""
