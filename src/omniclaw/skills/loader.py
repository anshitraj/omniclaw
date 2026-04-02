"""
Local skill loader for the OmniClaw installable skills system (v1).

Discovery contract
------------------
``load_skills_from_directory`` scans a directory for skill folders.
Each skill folder must contain a ``skill.json`` file at its root.
Sub-directories without ``skill.json`` are silently ignored.

Error handling
--------------
Malformed JSON, missing required fields, or constraint violations cause
the offending skill to be skipped with a WARNING log entry.  A bad
manifest never raises an exception to the caller — it just doesn't
appear in the returned list.

This keeps skill discovery safe to run at startup without worrying that
a third-party skill folder can crash the control plane.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from omniclaw.skills.exceptions import SkillValidationError
from omniclaw.skills.manifest import SkillManifest

logger = logging.getLogger("omniclaw.skills")

# The well-known manifest filename inside every skill folder.
MANIFEST_FILENAME = "skill.json"


def load_skills_from_directory(skills_dir: Path | str) -> list[SkillManifest]:
    """Discover and load all valid skills under *skills_dir*.

    Scans ``<skills_dir>/*/skill.json`` (one level deep).  Sub-directories
    that do not contain ``skill.json`` are silently skipped.  Invalid
    manifests are logged at WARNING level and skipped.

    Args:
        skills_dir: Path to the directory that contains skill sub-folders.
                    Accepts both :class:`pathlib.Path` and ``str``.

    Returns:
        List of valid :class:`SkillManifest` instances, in filesystem order.
        Returns an empty list if the directory does not exist or is empty.

    Example::

        from pathlib import Path
        from omniclaw.skills.loader import load_skills_from_directory
        from omniclaw.skills.registry import get_registry

        manifests = load_skills_from_directory(Path(".agents/skills"))
        registry = get_registry()
        for manifest in manifests:
            registry.register(manifest)
    """
    skills_dir = Path(skills_dir)

    if not skills_dir.exists():
        logger.debug("Skills directory %s does not exist — no skills loaded", skills_dir)
        return []

    if not skills_dir.is_dir():
        logger.warning(
            "Skills path %s is not a directory — no skills loaded", skills_dir
        )
        return []

    loaded: list[SkillManifest] = []

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue

        manifest_path = entry / MANIFEST_FILENAME
        if not manifest_path.exists():
            logger.debug(
                "Skipping %s — no %s found", entry.name, MANIFEST_FILENAME
            )
            continue

        manifest = _load_manifest(manifest_path)
        if manifest is not None:
            loaded.append(manifest)

    logger.info(
        "Skill discovery complete: %d valid skill(s) loaded from %s",
        len(loaded),
        skills_dir,
    )
    return loaded


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_manifest(manifest_path: Path) -> SkillManifest | None:
    """Read, parse and validate a single manifest file.

    Returns the :class:`SkillManifest` on success, or ``None`` on any error.
    All errors are logged at WARNING level — never re-raised.
    """
    skill_dir_name = manifest_path.parent.name

    # 1. Read raw JSON
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Could not read manifest %s: %s — skipping", manifest_path, exc
        )
        return None

    # 2. Parse JSON
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid JSON in %s: %s — skipping skill in folder %r",
            manifest_path,
            exc,
            skill_dir_name,
        )
        return None

    if not isinstance(data, dict):
        logger.warning(
            "Manifest %s must be a JSON object, got %s — skipping",
            manifest_path,
            type(data).__name__,
        )
        return None

    # 3. Validate with Pydantic
    try:
        manifest = SkillManifest.model_validate(data)
    except (ValidationError, SkillValidationError) as exc:
        logger.warning(
            "Manifest validation failed for skill in folder %r (%s): %s — skipping",
            skill_dir_name,
            manifest_path,
            exc,
        )
        return None

    logger.debug(
        "Loaded skill %r (version=%s) from %s",
        manifest.id,
        manifest.version,
        manifest_path,
    )
    return manifest
