from __future__ import annotations


class ComAutomationUnavailable(RuntimeError):
    """Raised when a Windows COM integration is unavailable in the current runtime."""
