"""
Skill manifest model for the OmniClaw installable skills system (v1).

A skill manifest is the machine-readable descriptor stored in skill.json
inside each skill folder.  Pydantic v2 is already a project dependency,
so we use it here for free validation and clear error messages.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from omniclaw.skills.exceptions import SkillValidationError

# Allowed characters in a skill id: lowercase letters, digits, hyphens, underscores.
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class InputField(BaseModel):
    """Describes a single named input accepted by a skill."""

    name: str = Field(..., description="Input field name")
    type: str = Field("string", description="Value type hint (string, number, boolean)")
    description: str = Field("", description="Human-readable description")
    required: bool = Field(False, description="Whether this input is required")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("InputField.name must not be empty")
        return v


class SkillManifest(BaseModel):
    """
    Machine-readable descriptor for an installable OmniClaw skill.

    Stored as ``skill.json`` inside a skill folder under ``.agents/skills/``.

    Required fields
    ---------------
    id              Unique identifier, e.g. ``"hello-world"``.
                    Allowed characters: lowercase letters, digits, hyphens, underscores.
                    Must start with a letter or digit.
    name            Human-readable display name.
    version         Version string following SemVer conventions, e.g. ``"1.0.0"``.
    description     Short description shown when listing skills.
    entry_prompt    Relative path to the prompt/instruction file inside the skill folder,
                    e.g. ``"prompt.md"``.

    Optional fields
    ---------------
    inputs              List of named input descriptors (declarative; not enforced in v1).
    permissions         List of permission hints (declarative; not enforced in v1).
    install_scope       Hint for where this skill is meaningful: ``"agent"`` or ``"workspace"``.
                        Informational only in v1.
    enabled_by_default  Whether the registry should mark this skill enabled on load.
                        Defaults to ``True``.
    """

    # --- required ---
    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Human-readable display name")
    version: str = Field(..., description="Version string (e.g. '1.0.0')")
    description: str = Field(..., description="Short description")
    entry_prompt: str = Field(..., description="Relative path to the prompt file")

    # --- optional ---
    inputs: list[InputField] = Field(default_factory=list, description="Declared input schema")
    permissions: list[str] = Field(
        default_factory=list, description="Declared permission hints (informational)"
    )
    install_scope: str | None = Field(
        None, description="Scope hint: 'agent' or 'workspace'"
    )
    enabled_by_default: bool = Field(True, description="Start enabled when registered")

    # Allow unknown extra fields in the JSON to be silently ignored so that
    # future manifest versions don't break older loaders.
    model_config = {"extra": "ignore"}

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v:
            raise ValueError("Skill id must not be empty")
        if not _ID_PATTERN.match(v):
            raise ValueError(
                f"Skill id {v!r} is invalid. "
                "Use only lowercase letters, digits, hyphens, and underscores. "
                "Must start with a letter or digit."
            )
        return v

    @field_validator("name", "version", "description", "entry_prompt")
    @classmethod
    def not_empty(cls, v: str, info: Any) -> str:
        if not v.strip():
            raise ValueError(f"Skill field '{info.field_name}' must not be empty")
        return v

    @field_validator("install_scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        if v is not None and v not in {"agent", "workspace"}:
            raise ValueError(
                f"install_scope must be 'agent' or 'workspace', got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _wrap_pydantic_errors(self) -> "SkillManifest":
        # This validator runs after all field validators.  It exists so that
        # callers who catch SkillValidationError don't also need to catch
        # pydantic.ValidationError.  The loader does the wrapping itself, but
        # having a single exception type is friendlier.
        return self

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SkillManifest id={self.id!r} version={self.version!r}>"
