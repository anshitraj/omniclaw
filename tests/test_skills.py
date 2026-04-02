"""
Unit tests for the OmniClaw v1 installable skills system.

Tests cover:
- valid manifest loading from a temp directory
- invalid manifests are skipped (not raised)
- registry CRUD: register, get, list_all
- enable / disable behaviour
- list_enabled filtering
- unknown skill id returns None
- loader edge cases: missing directory, non-dict JSON, bad JSON syntax

These tests are purely in-memory and filesystem-local (tmp_path).
They do not require Circle API keys, network access, or any payment infra.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from omniclaw.skills.exceptions import SkillValidationError
from omniclaw.skills.loader import load_skills_from_directory
from omniclaw.skills.manifest import InputField, SkillManifest
from omniclaw.skills.registry import SkillRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(base: Path, folder: str, data: dict) -> Path:
    """Write a skill.json under base/folder/ and return the folder path."""
    skill_dir = base / folder
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.json").write_text(json.dumps(data), encoding="utf-8")
    return skill_dir


def _minimal_manifest_data(**overrides) -> dict:
    """Return a minimal valid manifest dict, with optional overrides."""
    base = {
        "id": "test-skill",
        "name": "Test Skill",
        "version": "1.0.0",
        "description": "A test skill",
        "entry_prompt": "prompt.md",
    }
    base.update(overrides)
    return base


# ===========================================================================
# SkillManifest model
# ===========================================================================


class TestSkillManifest:
    """Tests for the SkillManifest Pydantic model."""

    def test_valid_minimal_manifest(self) -> None:
        """A manifest with all required fields parses successfully."""
        manifest = SkillManifest(**_minimal_manifest_data())

        assert manifest.id == "test-skill"
        assert manifest.name == "Test Skill"
        assert manifest.version == "1.0.0"
        assert manifest.description == "A test skill"
        assert manifest.entry_prompt == "prompt.md"
        # defaults
        assert manifest.enabled_by_default is True
        assert manifest.inputs == []
        assert manifest.permissions == []
        assert manifest.install_scope is None

    def test_valid_full_manifest(self) -> None:
        """A manifest with all optional fields parses correctly."""
        manifest = SkillManifest(
            id="full-skill",
            name="Full Skill",
            version="2.3.1",
            description="Full example",
            entry_prompt="prompt.md",
            inputs=[{"name": "query", "type": "string", "description": "Search query", "required": True}],
            permissions=["read:ledger"],
            install_scope="agent",
            enabled_by_default=False,
        )

        assert manifest.install_scope == "agent"
        assert manifest.enabled_by_default is False
        assert len(manifest.inputs) == 1
        assert manifest.inputs[0].name == "query"
        assert manifest.inputs[0].required is True

    def test_invalid_id_special_chars_raises(self) -> None:
        """Skill id with uppercase or special chars raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillManifest(**_minimal_manifest_data(id="My Skill!"))

    def test_invalid_id_empty_raises(self) -> None:
        """Empty skill id raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillManifest(**_minimal_manifest_data(id=""))

    def test_invalid_install_scope_raises(self) -> None:
        """Unrecognised install_scope raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillManifest(**_minimal_manifest_data(install_scope="global"))

    def test_valid_install_scope_values(self) -> None:
        """Both recognised scope values are accepted."""
        for scope in ("agent", "workspace"):
            m = SkillManifest(**_minimal_manifest_data(install_scope=scope))
            assert m.install_scope == scope

    def test_id_allows_underscores_and_hyphens(self) -> None:
        """Hyphens and underscores in ids are valid."""
        for skill_id in ("my-skill", "my_skill", "skill123", "a"):
            m = SkillManifest(**_minimal_manifest_data(id=skill_id))
            assert m.id == skill_id

    def test_extra_fields_are_ignored(self) -> None:
        """Unknown fields in the manifest are silently ignored (forward compat)."""
        data = _minimal_manifest_data()
        data["future_field"] = "some-value"
        data["another_unknown"] = 42

        manifest = SkillManifest(**data)
        assert not hasattr(manifest, "future_field")

    def test_input_field_model(self) -> None:
        """InputField validates its own name."""
        field = InputField(name="param", type="number", description="A number", required=True)
        assert field.name == "param"
        assert field.required is True

    def test_input_field_empty_name_raises(self) -> None:
        """Empty InputField name raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InputField(name="   ")


# ===========================================================================
# SkillRegistry
# ===========================================================================


class TestSkillRegistry:
    """Tests for the in-memory SkillRegistry."""

    def _make_manifest(self, skill_id: str = "test-skill", enabled: bool = True) -> SkillManifest:
        return SkillManifest(**_minimal_manifest_data(id=skill_id, enabled_by_default=enabled))

    def test_register_and_get(self) -> None:
        """A registered skill can be retrieved by id."""
        registry = SkillRegistry()
        manifest = self._make_manifest("my-skill")
        registry.register(manifest)

        result = registry.get("my-skill")
        assert result is manifest

    def test_get_unknown_returns_none(self) -> None:
        """Getting an unknown skill id returns None."""
        registry = SkillRegistry()
        assert registry.get("does-not-exist") is None

    def test_list_all_empty(self) -> None:
        """Empty registry returns an empty list."""
        registry = SkillRegistry()
        assert registry.list_all() == []

    def test_list_all(self) -> None:
        """list_all returns all registered skills."""
        registry = SkillRegistry()
        for skill_id in ("skill-a", "skill-b", "skill-c"):
            registry.register(self._make_manifest(skill_id))

        all_skills = registry.list_all()
        assert len(all_skills) == 3
        assert {s.id for s in all_skills} == {"skill-a", "skill-b", "skill-c"}

    def test_enabled_by_default_true(self) -> None:
        """Skill registered with enabled_by_default=True starts enabled."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("s1", enabled=True))
        assert registry.is_enabled("s1") is True

    def test_enabled_by_default_false(self) -> None:
        """Skill registered with enabled_by_default=False starts disabled."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("s2", enabled=False))
        assert registry.is_enabled("s2") is False

    def test_enable(self) -> None:
        """A disabled skill can be enabled."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("s3", enabled=False))
        result = registry.enable("s3")
        assert result is True
        assert registry.is_enabled("s3") is True

    def test_disable(self) -> None:
        """An enabled skill can be disabled."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("s4", enabled=True))
        result = registry.disable("s4")
        assert result is True
        assert registry.is_enabled("s4") is False

    def test_enable_unknown_returns_false(self) -> None:
        """Enabling a non-existent skill id returns False."""
        registry = SkillRegistry()
        assert registry.enable("ghost") is False

    def test_disable_unknown_returns_false(self) -> None:
        """Disabling a non-existent skill id returns False."""
        registry = SkillRegistry()
        assert registry.disable("ghost") is False

    def test_list_enabled_filters_correctly(self) -> None:
        """list_enabled returns only enabled skills."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("on", enabled=True))
        registry.register(self._make_manifest("off", enabled=False))

        enabled = registry.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].id == "on"

    def test_list_enabled_after_disable(self) -> None:
        """Disabling a skill removes it from list_enabled."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("alpha", enabled=True))
        registry.register(self._make_manifest("beta", enabled=True))
        registry.disable("alpha")

        enabled_ids = {s.id for s in registry.list_enabled()}
        assert enabled_ids == {"beta"}

    def test_re_register_resets_enabled_state(self) -> None:
        """Re-registering a skill resets its enabled state to the manifest default."""
        registry = SkillRegistry()
        registry.register(self._make_manifest("r", enabled=True))
        registry.disable("r")
        assert registry.is_enabled("r") is False

        # Re-register with enabled_by_default=True
        registry.register(self._make_manifest("r", enabled=True))
        assert registry.is_enabled("r") is True

    def test_len(self) -> None:
        """len(registry) returns the count of registered skills."""
        registry = SkillRegistry()
        assert len(registry) == 0
        registry.register(self._make_manifest("x"))
        assert len(registry) == 1

    def test_is_enabled_unknown_returns_false(self) -> None:
        """is_enabled for an unknown id returns False (not KeyError)."""
        registry = SkillRegistry()
        assert registry.is_enabled("nonexistent") is False


# ===========================================================================
# Loader
# ===========================================================================


class TestLoader:
    """Tests for load_skills_from_directory."""

    def test_load_valid_skill(self, tmp_path: Path) -> None:
        """A well-formed skill.json is loaded and returned."""
        _write_skill(tmp_path, "my-skill", _minimal_manifest_data(id="my-skill"))

        results = load_skills_from_directory(tmp_path)
        assert len(results) == 1
        assert results[0].id == "my-skill"

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        """Multiple valid skill folders are all loaded."""
        for skill_id in ("alpha", "beta", "gamma"):
            _write_skill(tmp_path, skill_id, _minimal_manifest_data(id=skill_id))

        results = load_skills_from_directory(tmp_path)
        assert len(results) == 3
        loaded_ids = {m.id for m in results}
        assert loaded_ids == {"alpha", "beta", "gamma"}

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """A directory that does not exist returns an empty list."""
        results = load_skills_from_directory(tmp_path / "nonexistent")
        assert results == []

    def test_folder_without_manifest_skipped(self, tmp_path: Path) -> None:
        """A skill folder without skill.json is silently skipped."""
        (tmp_path / "no-manifest").mkdir()

        results = load_skills_from_directory(tmp_path)
        assert results == []

    def test_invalid_json_skipped_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A skill folder with invalid JSON is skipped and a warning is logged."""
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()
        (broken_dir / "skill.json").write_text("{not valid json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="omniclaw.skills"):
            results = load_skills_from_directory(tmp_path)

        assert results == []
        assert any("Invalid JSON" in r.message for r in caplog.records)

    def test_missing_required_field_skipped_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A manifest missing a required field is skipped and a warning is logged."""
        bad_data = {"id": "bad", "name": "Bad Skill"}  # missing version, description, entry_prompt
        _write_skill(tmp_path, "bad", bad_data)

        with caplog.at_level(logging.WARNING, logger="omniclaw.skills"):
            results = load_skills_from_directory(tmp_path)

        assert results == []
        assert any("validation" in r.message.lower() for r in caplog.records)

    def test_non_dict_json_skipped_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A manifest that is valid JSON but not an object is skipped."""
        array_dir = tmp_path / "array-skill"
        array_dir.mkdir()
        (array_dir / "skill.json").write_text("[1, 2, 3]", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="omniclaw.skills"):
            results = load_skills_from_directory(tmp_path)

        assert results == []

    def test_invalid_skill_does_not_affect_valid_skills(
        self, tmp_path: Path
    ) -> None:
        """A bad manifest is skipped but valid skills in the same directory still load."""
        _write_skill(tmp_path, "good-skill", _minimal_manifest_data(id="good-skill"))

        broken_dir = tmp_path / "broken-skill"
        broken_dir.mkdir()
        (broken_dir / "skill.json").write_text("{bad json", encoding="utf-8")

        results = load_skills_from_directory(tmp_path)
        assert len(results) == 1
        assert results[0].id == "good-skill"

    def test_files_in_root_are_ignored(self, tmp_path: Path) -> None:
        """Files (not directories) at the root level of skills_dir are ignored."""
        (tmp_path / "stray-file.json").write_text("{}", encoding="utf-8")
        _write_skill(tmp_path, "real-skill", _minimal_manifest_data(id="real-skill"))

        results = load_skills_from_directory(tmp_path)
        assert len(results) == 1
        assert results[0].id == "real-skill"

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """load_skills_from_directory accepts a plain string as path."""
        _write_skill(tmp_path, "str-skill", _minimal_manifest_data(id="str-skill"))

        results = load_skills_from_directory(str(tmp_path))
        assert len(results) == 1

    def test_extra_fields_in_manifest_are_ignored(self, tmp_path: Path) -> None:
        """Unknown fields in skill.json do not cause loading to fail."""
        data = _minimal_manifest_data(id="future-skill")
        data["new_v2_field"] = "some-value"
        _write_skill(tmp_path, "future-skill", data)

        results = load_skills_from_directory(tmp_path)
        assert len(results) == 1

    def test_load_and_register_integration(self, tmp_path: Path) -> None:
        """Skills loaded from disk can be registered and queried via registry."""
        _write_skill(tmp_path, "integrated", _minimal_manifest_data(id="integrated"))

        registry = SkillRegistry()
        for manifest in load_skills_from_directory(tmp_path):
            registry.register(manifest)

        assert registry.get("integrated") is not None
        assert registry.is_enabled("integrated") is True

    def test_example_skill_is_loadable(self) -> None:
        """The bundled hello-world example skill in .agents/skills/ is valid."""
        # Locate the example skill relative to this test file.
        # tests/ -> project root -> .agents/skills/
        project_root = Path(__file__).parent.parent
        skills_path = project_root / ".agents" / "skills"

        if not skills_path.exists():
            pytest.skip(".agents/skills directory not found — skipping example skill test")

        manifests = load_skills_from_directory(skills_path)
        ids = {m.id for m in manifests}

        # hello-world must load; omniclaw-cli has no skill.json so will be skipped
        # (SKILL.md is an agent instruction file, not a skill manifest).
        assert "hello-world" in ids


# ===========================================================================
# SkillValidationError
# ===========================================================================


class TestSkillValidationError:
    """Ensures SkillValidationError is a proper ValueError subclass."""

    def test_is_value_error(self) -> None:
        err = SkillValidationError("bad manifest")
        assert isinstance(err, ValueError)

    def test_message_preserved(self) -> None:
        err = SkillValidationError("missing id")
        assert "missing id" in str(err)
