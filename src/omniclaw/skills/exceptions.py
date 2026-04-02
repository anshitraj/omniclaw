"""
Exceptions for the OmniClaw installable skills system (v1).
"""

from __future__ import annotations


class SkillValidationError(ValueError):
    """Raised when a skill manifest fails validation.

    The loader catches this error and skips the offending skill so that
    a single bad manifest never crashes the application.
    """
