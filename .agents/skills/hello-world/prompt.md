# Hello World — OmniClaw Example Skill

This is an example skill that demonstrates the format expected by the
OmniClaw installable skills framework (v1).

## What this skill does

Greet a named target with a friendly message.  This skill has no payment
capability, no side-effects, and no external dependencies.  It exists
purely to illustrate how skills are structured.

## Inputs

| Input  | Type   | Required | Description                     |
|--------|--------|----------|---------------------------------|
| target | string | No       | The name of who to greet.       |

If `target` is not provided, default to `"world"`.

## Prompt template

```
Greet {{ target | default("world") }} with a short, friendly message.
Keep the response to one sentence.
```

## Notes for contributors

- Copy this folder to create a new skill.
- Replace `skill.json` fields and update `prompt.md`.
- The `id` in `skill.json` must be unique across all installed skills.
- See `docs/installable-skills.md` for the full reference.
