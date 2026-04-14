# Arc Marketplace Showcase

This showcase is a visual vendor marketplace for Arc Testnet settlement.

It is intentionally not a text-heavy demo. The browser UI represents the vendor as a kiosk with paid services. A buyer agent selects a paid URL, OmniClaw enforces buyer policy, x402 `exact` settles on Arc Testnet, and the vendor unlocks the result.

## What It Proves

- A vendor can expose multiple paid services from one marketplace surface.
- The seller advertises standard x402 `exact` requirements for Arc Testnet.
- The buyer pays through OmniClaw policy control instead of raw wallet access.
- The self-hosted OmniClaw exact facilitator verifies and settles on Arc.
- The settlement transaction can be opened on ArcScan.

## Components

| Component | Role |
| --- | --- |
| Kiosk vendor app | Marketplace UI and paid product endpoints |
| OmniClaw exact facilitator | Self-hosted x402 `verify` and `settle` service |
| Buyer Financial Policy Engine | Policy-controlled payment executor for OpenClaw or `omniclaw-cli` |
| ArcScan | External proof that settlement happened on Arc Testnet |

## Start The Vendor Kiosk

Required seller/facilitator env:

```bash
export OMNICLAW_PRIVATE_KEY="0xSellerOrFacilitatorKey"
export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="0xFacilitatorKey"
```

If both roles use the same funded test key, `OMNICLAW_X402_FACILITATOR_PRIVATE_KEY` can be omitted and the launcher will reuse `OMNICLAW_PRIVATE_KEY`.

Start the showcase:

```bash
bash scripts/start_arc_marketplace_showcase.sh
```

Open:

```text
http://127.0.0.1:8020
```

The kiosk displays three vendor services:

- Prime Market Scan
- Risk Oracle Brief
- Settlement Receipt Kit

Each card exposes a paid URL for OpenClaw or `omniclaw-cli`.

## Buyer Flow

Point the agent CLI at the buyer Financial Policy Engine:

```bash
export OMNICLAW_SERVER_URL="http://127.0.0.1:8080"
export OMNICLAW_TOKEN="buyer-agent-token"
```

Inspect the seller requirements:

```bash
omniclaw-cli inspect-x402 \
  --recipient "http://127.0.0.1:8020/buy/prime-market-scan"
```

Pay:

```bash
omniclaw-cli pay \
  --recipient "http://127.0.0.1:8020/buy/prime-market-scan" \
  --idempotency-key "arc-kiosk-001"
```

OpenClaw prompt:

```text
pay for this url: http://127.0.0.1:8020/buy/prime-market-scan
```

## ArcScan Proof

The buyer payment response should include the settlement transaction hash. Open it with:

```text
https://testnet.arcscan.app/tx/<settlement_tx>
```

Capture these proof assets:

- kiosk UI before payment
- `inspect-x402` output showing `exact` and Arc `eip155:5042002`
- `pay` output showing settled status and transaction hash
- ArcScan transaction page
- kiosk fulfillment feed after unlock

## Environment Overrides

```bash
export ARC_MARKETPLACE_PORT=8020
export ARC_MARKETPLACE_PUBLIC_BASE_URL="http://127.0.0.1:8020"
export ARC_MARKETPLACE_BUYER_BASE_URL="http://127.0.0.1:8020"
export ARC_MARKETPLACE_EXPLORER_BASE_URL="https://testnet.arcscan.app/tx/"

export OMNICLAW_X402_EXACT_NETWORK_PROFILE="ARC-TESTNET"
export OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE="ARC-TESTNET"
export OMNICLAW_X402_FACILITATOR_RPC_URL="https://rpc.testnet.arc.network"
export OMNICLAW_X402_FACILITATOR_NETWORKS="eip155:5042002"
export OMNICLAW_X402_EXACT_FACILITATOR_URL="http://127.0.0.1:4022"
```

## Product Framing

The demo should be explained in one line:

```text
An agent buys from an Arc vendor kiosk through OmniClaw policy control, and x402 exact settlement is confirmed on ArcScan.
```
