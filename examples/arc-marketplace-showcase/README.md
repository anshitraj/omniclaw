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

## Standalone Facilitator

Run this when you only need the self-hosted x402 exact facilitator for Arc:

```bash
export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="0xFacilitatorKeyWithArcGas"
bash scripts/start_arc_exact_facilitator.sh
```

Equivalent installed CLI:

```bash
omniclaw facilitator exact \
  --network-profile ARC-TESTNET \
  --network eip155:5042002 \
  --rpc-url https://rpc.testnet.arc.network \
  --port 4022
```

The facilitator exposes `GET /supported`, `POST /verify`, and `POST /settle`.

## Start The Vendor Kiosk

### Recommended: Docker Clean Slate

Use the Docker launcher when testing with OpenClaw, Telegram agents, or other containerized buyers. It starts all services on the same Docker bridge network with stable `172.18.0.x` addresses.

Required env:

```bash
export BUYER_OMNICLAW_PRIVATE_KEY="0xBuyerKeyWithArcTestnetUSDC"
export SELLER_OMNICLAW_PRIVATE_KEY="0xSellerKey"
export BUYER_CIRCLE_API_KEY="..."
export BUYER_ENTITY_SECRET="..."
```

Funding requirements:

- buyer key: Arc Testnet USDC for the selected product
- seller/facilitator key: Arc Testnet gas for settlement submission

Start:

```bash
bash scripts/start_arc_marketplace_showcase_docker.sh
```

Default runtime addresses:

| Service | URL |
| --- | --- |
| Browser UI | `http://127.0.0.1:8020` |
| Facilitator | `http://172.18.0.50:4022` |
| Vendor kiosk | `http://172.18.0.51:8020` |
| Buyer policy engine | `http://172.18.0.52:8080` |

Paid products:

| Product | Price | URL |
| --- | --- | --- |
| Prime Market Scan | `$0.25` | `http://172.18.0.51:8020/buy/prime-market-scan` |
| Risk Oracle Brief | `$0.15` | `http://172.18.0.51:8020/buy/risk-oracle-brief` |
| Settlement Receipt Kit | `$0.10` | `http://172.18.0.51:8020/buy/settlement-receipt-kit` |

OpenClaw config:

```bash
export OMNICLAW_SERVER_URL="http://172.18.0.52:8080"
export OMNICLAW_TOKEN="payment-agent-token"
```

Browser-only flow:

1. Open `http://127.0.0.1:8020`.
2. Use the `Built-In Buyer Agent` panel.
3. Select a product.
4. Click `Inspect` to verify route, network, buyer readiness, and amount.
5. Click `Pay & Unlock` to execute the policy-controlled x402 payment.
6. Open the returned settlement transaction on ArcScan.

The browser never receives the policy token. The kiosk backend proxies the action to the buyer Financial Policy Engine configured by `ARC_MARKETPLACE_BUYER_ENGINE_URL` and `ARC_MARKETPLACE_BUYER_TOKEN`.

OpenClaw prompt:

```text
pay for this url: http://172.18.0.51:8020/buy/prime-market-scan
```

If the buyer has less than `$0.25` Arc Testnet USDC, use:

```text
pay for this url: http://172.18.0.51:8020/buy/settlement-receipt-kit
```

Host-side CLI test:

```bash
OMNICLAW_SERVER_URL=http://127.0.0.1:8080 \
OMNICLAW_TOKEN=payment-agent-token \
omniclaw-cli inspect-x402 \
  --recipient "http://172.18.0.51:8020/buy/prime-market-scan"

OMNICLAW_SERVER_URL=http://127.0.0.1:8080 \
OMNICLAW_TOKEN=payment-agent-token \
omniclaw-cli pay \
  --recipient "http://172.18.0.51:8020/buy/prime-market-scan" \
  --idempotency-key "arc-kiosk-001"
```

### Host-Only Local Mode

Use this only when the buyer also runs on the host. Containerized buyers cannot use `127.0.0.1` for the vendor URL.

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

Known verified proof transaction:

```text
https://testnet.arcscan.app/tx/0xd40dc800a54bee4ff80da4709e65cfd3d0346eb1995ebc34fba433a6306b9219
```

This transaction shows `transferWithAuthorization` on Arc Testnet USDC. That is expected for standard x402 `exact`: the buyer signs a USDC authorization, the facilitator verifies it, and settlement submits the authorization to the USDC contract.

## ArcLens Ecosystem Submission

OmniClaw does not deploy a custom Arc contract for this showcase. The on-chain contract used by the demo is Arc Testnet USDC:

```text
0x3600000000000000000000000000000000000000
```

If ArcLens asks for a contract address and the field is required, use the Arc Testnet USDC contract above and explain:

```text
OmniClaw does not require a custom application contract for this demo. The Arc integration settles x402 exact payments through Arc Testnet USDC using transferWithAuthorization. Buyer agents pay vendor services through OmniClaw policy control, and settlement is visible on ArcScan.
```

Use this proof transaction in the submission:

```text
https://testnet.arcscan.app/tx/0xd40dc800a54bee4ff80da4709e65cfd3d0346eb1995ebc34fba433a6306b9219
```

## Environment Overrides

```bash
export ARC_MARKETPLACE_PORT=8020
export ARC_MARKETPLACE_PUBLIC_BASE_URL="http://127.0.0.1:8020"
export ARC_MARKETPLACE_BUYER_BASE_URL="http://172.18.0.51:8020"
export ARC_MARKETPLACE_BUYER_ENGINE_URL="http://172.18.0.52:8080"
export ARC_MARKETPLACE_BUYER_TOKEN="payment-agent-token"
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
