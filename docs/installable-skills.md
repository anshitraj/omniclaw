# Installable Skills — OmniClaw v1

Installable skills are self-contained, manifest-driven capability
packages that OmniClaw can discover, validate, and register at
startup — without modifying the core SDK or payment infrastructure.

---

## What this is (and isn't)

**v1 covers:**
- A standard layout for a skill folder
- A machine-readable `skill.json` manifest
- A Python API to load skills from disk and query them via a registry
- Enable / disable support (in-memory, reset each process start)

**v1 does not include:**
- Remote or npm-based skill installation
- A CLI for managing skills (`omniclaw skills list`)
- Runtime permission enforcement
- Execution-path integration (skills are discovered and registered, not called)
- A marketplace, dashboard, or billing surface
- Persistent enable/disable state across process restarts

---

## Folder structure

Each skill lives in its own folder under `.agents/skills/`:

```
.agents/skills/
├── omniclaw-cli/          # Existing agent instruction skill (SKILL.md only)
│   └── SKILL.md
└── hello-world/           # Example installable skill (v1)
    ├── skill.json          # Required — machine-readable manifest
    └── prompt.md           # Required by manifest (entry_prompt field)
```

The loader scans one level deep: `.agents/skills/*/skill.json`.
Folders without a `skill.json` are silently skipped (backward-compatible
with the existing `omniclaw-cli` folder which has only `SKILL.md`).

---

## Manifest fields (`skill.json`)

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | ✅ | Unique identifier. Lowercase letters, digits, hyphens, underscores. Must start with a letter or digit. |
| `name` | string | ✅ | Human-readable display name. |
| `version` | string | ✅ | Version string, e.g. `"1.0.0"`. |
| `description` | string | ✅ | Short description shown when listing skills. |
| `entry_prompt` | string | ✅ | Relative path to the prompt/instruction file inside the skill folder. |
| `inputs` | array | — | Declared input descriptors (informational in v1). |
| `permissions` | array of strings | — | Permission hints (informational in v1, not enforced). |
| `install_scope` | string | — | `"agent"` or `"workspace"` (informational in v1). |
| `enabled_by_default` | boolean | — | Whether the skill starts enabled when registered. Defaults to `true`. |

Unknown fields are silently ignored, so future manifest versions are forward-compatible.

### Minimal example

```json
{
  "id": "my-skill",
  "name": "My Skill",
  "version": "1.0.0",
  "description": "What this skill does.",
  "entry_prompt": "prompt.md"
}
```

### Full example

See [`.agents/skills/hello-world/skill.json`](../.agents/skills/hello-world/skill.json).

---

## How discovery and loading works

```python
from pathlib import Path
from omniclaw.skills import load_skills_from_directory, get_registry

# 1. Discover skills on disk
manifests = load_skills_from_directory(Path(".agents/skills"))

# 2. Register them
registry = get_registry()
for manifest in manifests:
    registry.register(manifest)

# 3. Query the registry
all_skills = registry.list_all()
active_skills = registry.list_enabled()
my_skill = registry.get("my-skill")          # returns SkillManifest or None
```

Invalid manifests are **skipped with a warning**, never raised as exceptions.
The rest of the skills load normally.

---

## Enable / disable

```python
registry = get_registry()

registry.disable("my-skill")          # returns True if found
registry.enable("my-skill")           # returns True if found

registry.is_enabled("my-skill")       # bool
registry.list_enabled()               # only enabled skills
```

State is **in-memory only** in v1 — it resets each process start.
`enabled_by_default` in the manifest controls the initial state.

---

## How to add a new skill

1. Create a folder under `.agents/skills/` using your skill's id as the name.
2. Add a `skill.json` manifest.
3. Add the file referenced by `entry_prompt` (e.g. `prompt.md`).
4. Optionally call `load_skills_from_directory` + `registry.register()` in your startup code.

The loader will automatically pick up the new folder on the next run.

---

## Backward compatibility

The existing `.agents/skills/omniclaw-cli/` folder (which contains only
`SKILL.md`) is **completely unaffected**.  The loader ignores any folder
that does not have a `skill.json`, so the existing agent instruction skill
continues to work exactly as before.

---

## Python API reference

```python
from omniclaw.skills import (
    SkillManifest,          # Pydantic model for a skill manifest
    InputField,             # Pydantic model for a single input descriptor
    SkillRegistry,          # In-memory registry class
    SkillValidationError,   # Raised when a manifest fails validation
    get_registry,           # Returns the module-level singleton registry
    load_skills_from_directory,  # Discovers skills from a directory path
)
```

---

## Running the tests

```bash
pytest tests/test_skills.py -v
```

No API keys or network access required.
