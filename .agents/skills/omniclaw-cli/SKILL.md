---
name: omniclaw
description: >
  Use this skill whenever you need to pay for an x402 URL, transfer USDC to an
  address, inspect OmniClaw balances or ledger entries, or expose a paid API
  with omniclaw-cli serve. OmniClaw is the Economic Execution and Control Layer
  for Agentic Systems. The CLI is the zero-trust execution layer: buyers use
  `omniclaw-cli pay`, sellers use `omniclaw-cli serve`. Use this skill for the
  CLI execution path only, not for owner setup, policy editing, wallet
  provisioning, or Financial Policy Engine administration.
requires:
  - env: OMNICLAW_SERVER_URL
    description: >
      OmniClaw Financial Policy Engine base URL. Required unless the CLI was
      already configured locally before the agent turn.
  - env: OMNICLAW_TOKEN
    description: >
      Scoped agent token. Never print, log, or transmit it. If missing, stop
      and notify the owner.
version: 0.0.4
author: Omnuron AI
---

# OmniClaw CLI Skill

## Trigger

Use `omniclaw-cli` only when the task is directly about one of these actions:

- pay for a paid URL that returns `402 Payment Required`
- transfer USDC to an address
- inspect wallet, Gateway, or Circle balances
- inspect transaction history
- expose a paid seller endpoint with `serve`

Do not use this skill for:

- editing policy files
- creating wallets
- provisioning secrets
- changing allowlists, limits, or owner approvals outside the exposed CLI commands
- administering the Financial Policy Engine process itself

## Core Model

OmniClaw is not just a wallet wrapper.
It is the economic execution and control layer that combines:

- zero-trust execution through the CLI
- owner-defined financial policy through the Financial Policy Engine
- settlement rails such as direct transfers, x402, CCTP, and Circle Gateway nanopayments

This skill is specifically about the CLI execution surface.

The same CLI has two economic roles:

- buyer role: `omniclaw-cli pay`
- seller role: `omniclaw-cli serve`

The agent does not control the private key.
The Financial Policy Engine enforces policy and signs allowed actions.

## Inputs The Agent Should Expect

The runtime should normally provide either:

1. environment-driven execution
- `OMNICLAW_SERVER_URL`
- `OMNICLAW_TOKEN`
- optionally `OMNICLAW_OWNER_TOKEN` if this run is allowed to approve confirmations

2. preconfigured CLI state
- `omniclaw-cli configure` was already run before the turn

If neither is true, stop and ask the owner for:

- Financial Policy Engine URL
- agent token
- wallet alias

Do not invent or search for them yourself.

## Safe Default Workflow

### For any new spend

1. Run `omniclaw-cli status` if connectivity or health is uncertain.
2. Run `omniclaw-cli balance-detail` if Gateway balance matters.
3. Run `omniclaw-cli can-pay --recipient ...` before paying a new recipient.
4. Use `--idempotency-key` for job-based payments.
5. For direct-address payments where budget/guards matter, use `simulate` first.

### For x402 URLs

1. Use `omniclaw-cli pay --recipient <url>`.
2. Add `--method`, `--body`, and `--header` when the paid endpoint expects a non-GET request.
3. Add `--output` if the paid response should be saved.

### For direct address transfers

1. Use `omniclaw-cli pay --recipient <0xaddress> --amount <usdc>`.
2. Always include `--purpose`.

### For seller tasks

1. Inspect current state with `balance-detail`.
2. Start the paid endpoint with `omniclaw-cli serve`.
3. Remember that `serve` binds to `0.0.0.0` even if the banner prints `localhost`.

## Approval Handling

If `pay` returns approval-required output, for example:

- `requires_confirmation: true`
- `confirmation_id: ...`

Then:

- do not retry blindly
- do not invent a workaround
- if the run explicitly has owner authority, use `omniclaw-cli confirmations approve --id <confirmation-id>`
- otherwise stop and notify the owner

## Stop Conditions

Stop and notify the owner if any of these happen:

- token or Financial Policy Engine URL is missing
- `can-pay` says the recipient is blocked
- `pay` returns a policy or guard rejection
- available or Gateway balance is insufficient
- the exact command or flag is unclear

## Command Reference

For exact command schemas, flags, and live help output, read:

- `references/cli-reference.md`

Do not guess flags from memory when a reference is available.
