# Production Readiness

This is the short production checklist for OmniClaw.

Use it before publishing a release, running a pilot, or demoing a real external facilitator flow.

## What OmniClaw Is

OmniClaw is the policy-controlled execution layer for agent payments.

It does four things:

- inspects what a seller accepts
- enforces buyer policy before money moves
- routes to a compatible payment rail
- records what happened for operators

## Facilitator Strategy

OmniClaw is facilitator-aware. Sellers can use the settlement path that fits their deployment while buyers keep OmniClaw policy controls in front of money movement.

Supported facilitator paths:

- x402.org can validate external standard exact settlement immediately on Base Sepolia
- Thirdweb can provide broad gas-sponsored x402 settlement
- Circle Gateway can provide batched gasless nanopayments
- x402.org or other facilitators can support standard exact settlement
- OmniClaw self-hosted exact facilitator is optional infrastructure for proof, Arc/custom networks, and self-hosted control

## Validating Deployment Readiness

For any production environment deployment, we recommend verifying:

- seller URL
- `inspect-x402` output
- `pay` output
- transaction hash or settlement ID
- dashboard/explorer screenshot
- policy file used for the buyer

Ensure this validation checklist is complete before moving to production.

## Buyer Lock

The buyer path is locked when:

- `omniclaw-cli can-pay` works
- `omniclaw-cli inspect-x402` reports the selected route
- `omniclaw-cli pay` uses `/api/v1/pay`
- policy blocks unsafe recipients before settlement
- exact x402 payments use the standard x402 SDK path
- Gateway payments require Gateway readiness before selecting `GatewayWalletBatched`

## Seller Lock

The seller path is locked when:

- seller advertises correct x402 requirements
- seller does not leak Gateway metadata into non-Gateway exact flows
- paid response unlocks only after settlement
- settlement status is visible in logs and response metadata

## Facilitator Lock

The facilitator strategy is locked as:

- x402.org first for external exact validation on Base Sepolia
- Thirdweb next for managed external x402 validation once account access is available
- Circle Gateway for batched nanopayments
- external exact facilitators where seller requirements support them
- OmniClaw self-hosted exact facilitator only for proof, custom networks, Arc, and self-hosted enterprise deployments

Operational split:

- seller surface creates `accepts`
- facilitator verifies and settles
- buyer policy engine decides whether payment is allowed and which route is selected

Keep these layers separate in deployment docs and product claims.

## Current Supported Capabilities

OmniClaw officially supports:

- Base Sepolia external exact via x402.org: fully supported
- buyer exact x402 path via `/api/v1/pay`: fully supported
- seller exact route advertising correct `payTo`: fully supported
- OmniClaw self-hosted exact facilitator: fully supported on Arc Testnet and EVM profiles
- Arc exact profile: fully supported with self-hosted facilitator settlement
- Thirdweb HTTP integration: fully supported for `accepts`, `verify`, `settle`, `fetch`, and discovery; requires managed Thirdweb account configuration

## Release Gate

Run before shipping:

```bash
uv sync --extra dev
uv run pytest \
  tests/test_setup.py \
  tests/test_payment_intents.py \
  tests/test_client.py \
  tests/test_webhook_verification.py

python3 -m py_compile \
  src/omniclaw/seller/facilitator_generic.py \
  examples/thirdweb-http-facilitator/verify_settle.py \
  src/omniclaw/admin_cli.py \
  src/omniclaw/facilitator/exact.py \
  src/omniclaw/facilitator/networks.py \
  scripts/verify_release_artifact.py

python3 scripts/release_verify.sh
```

If you are validating exact-flow pilot coverage, run the current smoke slice after syncing
dependencies:

```bash
uv run pytest \
  tests/test_facilitator_e2e.py \
  tests/test_cli_facilitator.py \
  tests/test_cctp_constants.py \
  tests/test_exact_network_profiles.py \
  tests/test_exact_facilitator_app.py \
  tests/test_x402_sdk_adapter.py \
  -q
```

This exact-flow slice currently depends on an `x402` build that exposes `x402.schemas`.
