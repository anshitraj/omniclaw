"""
In-memory skill registry for the OmniClaw installable skills system (v1).

The registry is intentionally simple: a thin dict-backed store with
enable/disable support.  There is no persistence layer in v1 — state is
reset each time the process starts, which keeps the implementation
reviewable and the diff minimal.

Module-level singleton
----------------------
A process-wide singleton is exposed via ``get_registry()``, following
the same pattern as ``omniclaw.core.logging.get_logger``.  Callers that
need an isolated registry (e.g. tests) can instantiate ``SkillRegistry``
directly.
"""

from __future__ import annotations

import logging

from omniclaw.skills.manifest import SkillManifest

logger = logging.getLogger("omniclaw.skills")


class SkillRegistry:
    """In-memory registry of installable skills.

    All operations are O(1) keyed by skill id.

    Example usage::

        registry = SkillRegistry()
        registry.register(manifest)
        skill = registry.get("hello-world")
        registry.disable("hello-world")
        active = registry.list_enabled()
    """

    def __init__(self) -> None:
        # _skills: id -> SkillManifest
        self._skills: dict[str, SkillManifest] = {}
        # _enabled: id -> bool   (defaults from manifest.enabled_by_default)
        self._enabled: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, manifest: SkillManifest) -> None:
        """Register a skill.

        If a skill with the same id is already registered it is silently
        replaced and its enabled state is reset to ``manifest.enabled_by_default``.

        Args:
            manifest: A valid :class:`SkillManifest` instance.
        """
        if manifest.id in self._skills:
            logger.debug("Replacing already-registered skill %r", manifest.id)
        self._skills[manifest.id] = manifest
        self._enabled[manifest.id] = manifest.enabled_by_default
        logger.debug(
            "Registered skill %r (enabled=%s)", manifest.id, manifest.enabled_by_default
        )

    def enable(self, skill_id: str) -> bool:
        """Enable a skill by id.

        Returns:
            ``True`` if the skill was found and enabled, ``False`` if not found.
        """
        if skill_id not in self._skills:
            logger.warning("enable: skill %r not found in registry", skill_id)
            return False
        self._enabled[skill_id] = True
        logger.debug("Enabled skill %r", skill_id)
        return True

    def disable(self, skill_id: str) -> bool:
        """Disable a skill by id.

        Returns:
            ``True`` if the skill was found and disabled, ``False`` if not found.
        """
        if skill_id not in self._skills:
            logger.warning("disable: skill %r not found in registry", skill_id)
            return False
        self._enabled[skill_id] = False
        logger.debug("Disabled skill %r", skill_id)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, skill_id: str) -> SkillManifest | None:
        """Return the manifest for *skill_id*, or ``None`` if not registered."""
        return self._skills.get(skill_id)

    def is_enabled(self, skill_id: str) -> bool:
        """Return ``True`` if the skill is registered and enabled."""
        return self._enabled.get(skill_id, False)

    def list_all(self) -> list[SkillManifest]:
        """Return all registered skills (enabled and disabled)."""
        return list(self._skills.values())

    def list_enabled(self) -> list[SkillManifest]:
        """Return only the currently-enabled skills."""
        return [m for m in self._skills.values() if self._enabled.get(m.id, False)]

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SkillRegistry skills={list(self._skills.keys())!r}>"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """Return the process-wide :class:`SkillRegistry` singleton.

    The instance is created lazily on the first call.  Tests that need
    an isolated registry should instantiate ``SkillRegistry()`` directly
    rather than using this function.
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
