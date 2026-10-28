"""Shared exception identity for strict source and trace contracts."""


class TraceContractError(ValueError):
    """Raised when a trace object violates the frozen schema contract."""
