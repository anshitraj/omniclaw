"""
OmniClaw Installable Skills — v1

Public surface for the skills sub-package.  Import from here rather than
from the individual modules::

    from omniclaw.skills import (
        SkillManifest,
        SkillRegistry,
        SkillValidationError,
        get_registry,
        load_skills_from_directory,
    )

v1 scope
--------
Discovery, validation, in-memory registry, enable/disable.
No execution-path integration, no remote registry, no persistence.
"""

from omniclaw.skills.exceptions import SkillValidationError
from omniclaw.skills.loader import load_skills_from_directory
from omniclaw.skills.manifest import InputField, SkillManifest
from omniclaw.skills.registry import SkillRegistry, get_registry

__all__ = [
    "InputField",
    "SkillManifest",
    "SkillRegistry",
    "SkillValidationError",
    "get_registry",
    "load_skills_from_directory",
]
