# x402 Facilitators

OmniClaw supports x402 payments through facilitator-backed settlement.

A facilitator is the service that verifies an x402 payment payload and settles it on the target rail. OmniClaw is integration-first: it governs agent financial authority and routes into the facilitator that fits the seller's requirements.

Supported deployment shapes:

- Circle Gateway `GatewayWalletBatched` for gasless nanopayments
- standard x402 `exact` settlement through an external facilitator such as Thirdweb or x402.org
- optional standard x402 `exact` settlement through a self-hosted OmniClaw facilitator

## Deployment Matrix

Use this matrix as the canonical operating model:

| Mode | Seller creates `accepts` | Who runs `verify` / `settle` | Status |
| --- | --- | --- | --- |
| Circle Gateway | OmniClaw seller middleware | Circle Gateway facilitator | already supported in OmniClaw seller flow |
| External exact via x402.org | seller app or OmniClaw external seller harness | x402.org | supported on Base Sepolia |
| External exact via Thirdweb | Thirdweb `accepts` API or seller using Thirdweb server wallet | Thirdweb | supported; requires managed Thirdweb account |
| Self-hosted OmniClaw exact facilitator | seller app or OmniClaw seller harness | OmniClaw exact facilitator | supported on Arc Testnet; use for Arc, Base, Ethereum Sepolia, and other applicable EVM profiles |

The architectural split matters:

- `accepts` is a seller concern
- `verify` and `settle` are facilitator concerns
- buyer routing is an OmniClaw policy concern

OmniClaw does not mix these layers together.

The buyer still uses one action:

```bash
omniclaw-cli inspect-x402 --recipient https://seller.example.com/compute
omniclaw-cli pay --recipient https://seller.example.com/compute --idempotency-key job-123
```

The Financial Policy Engine inspects the seller's x402 requirements and chooses a route that the seller supports and the buyer can actually fund.

## Integration Model

OmniClaw supports managed and self-hosted settlement paths. Thirdweb, Circle, x402.org, and other facilitators can handle settlement where they are the best fit.

OmniClaw's product responsibility:

- inspect what the seller accepts
- enforce buyer policy before money moves
- choose a fundable route
- sign only the allowed action
- preserve logs, limits, and payment visibility

That means a seller can use managed facilitator coverage, while the buyer still uses OmniClaw as the policy-controlled execution layer.

## SDK Seller Examples

Vendor and enterprise sellers should normally use the Python SDK.

Circle Gateway:

```python
payment=client.sell("$0.25", seller_address="0xVendorWallet")
```

Thirdweb:

```python
payment=client.sell(
    "$0.25",
    seller_address="0xThirdwebServerWallet",
    facilitator="thirdweb",
)
```

OmniClaw self-hosted exact:

```python
payment=client.sell(
    "$0.25",
    seller_address="0xVendorWallet",
    facilitator="omniclaw",
)
```

For the self-hosted exact path, set:

```env
OMNICLAW_X402_SELF_HOSTED_FACILITATOR_URL=http://127.0.0.1:4022
OMNICLAW_X402_EXACT_NETWORK_PROFILE=ARC-TESTNET
```

## Self-Hosted Exact Facilitator

OmniClaw includes a self-hosted exact facilitator for teams that need direct control over settlement infrastructure.

Common use cases:

- custom network support
- enterprise self-hosting requirements
- deterministic testnet proof
- chain-native settlement on a selected EVM profile
- local development and integration testing

The self-hosted facilitator implements standard x402 `exact` verify and settle behavior. The seller still owns the resource URL and `accepts` requirements; the facilitator verifies and settles the signed payment payload.

## Buyer Route Selection

For URL payments, the buyer path is:

1. request the resource
2. receive HTTP 402 x402 requirements
3. inspect accepted payment schemes
4. enforce OmniClaw policy
5. choose the best supported route
6. sign and execute through the selected payment rail

Current route priority:

- use `GatewayWalletBatched` when the seller supports Circle Gateway nanopayments and the buyer has Gateway balance on the required network
- use `exact` when the seller supports standard x402 exact settlement
- if the seller supports both and Gateway is not ready, use `exact`
- if no supported route is available, fail clearly before spending
- for direct exact payments, inspect checks the buyer's direct-wallet token balance when the selected EVM network and RPC are known

## Self-Host An Exact Facilitator

Use self-hosting when you need local proof, custom network control, or a fallback while validating an external provider.

Run a facilitator with the first-class OmniClaw command:

```bash
export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="0x..."

omniclaw facilitator exact \
  --network-profile ARC-TESTNET \
  --port 4022
```

For Base Sepolia:

```bash
export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="0x..."

omniclaw facilitator exact \
  --network-profile BASE-SEPOLIA \
  --port 4022
```

You can override the RPC and accepted CAIP-2 network explicitly:

```bash
omniclaw facilitator exact \
  --network-profile ARC-TESTNET \
  --network eip155:5042002 \
  --rpc-url https://rpc.testnet.arc.network \
  --port 4022
```

The facilitator exposes:

- `GET /supported`
- `POST /verify`
- `POST /settle`

It does not need to expose `accepts`.

For standard x402, `accepts` comes from the seller endpoint that is being monetized. OmniClaw's seller layer and seller harnesses create those requirements, and the facilitator handles verification and settlement after the buyer signs.

## Environment Variables

Self-hosted facilitator:

```env
OMNICLAW_X402_FACILITATOR_PRIVATE_KEY=0x...
OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE=ARC-TESTNET
OMNICLAW_X402_FACILITATOR_RPC_URL=https://rpc.testnet.arc.network
OMNICLAW_X402_FACILITATOR_NETWORKS=eip155:5042002
OMNICLAW_X402_FACILITATOR_HOST=0.0.0.0
OMNICLAW_X402_FACILITATOR_PORT=4022
```

Seller exact endpoint:

```env
OMNICLAW_X402_EXACT_NETWORK_PROFILE=ARC-TESTNET
OMNICLAW_X402_EXACT_FACILITATOR_URL=http://127.0.0.1:4022
OMNICLAW_X402_EXACT_PRICE=$0.25
```

Preferred behavior:

- set `OMNICLAW_PRIVATE_KEY` for the seller runtime
- let the seller derive `payTo` from that key

Optional override:

```env
OMNICLAW_X402_EXACT_PAY_TO=0xSellerAddress
```

Use the override only when you intentionally want the seller to advertise a payout address different from the runtime key.

External exact facilitator:

```env
OMNICLAW_X402_EXACT_FACILITATOR_URL=https://x402.org/facilitator
```

### x402.org Base Sepolia

Use x402.org first when you need an external facilitator test without Thirdweb account setup.

```bash
export OMNICLAW_PRIVATE_KEY="0xYourSellerPrivateKey"
export OMNICLAW_X402_EXACT_NETWORK_PROFILE="BASE-SEPOLIA"
export OMNICLAW_X402_EXACT_FACILITATOR_URL="https://x402.org/facilitator"

python scripts/start_external_x402_seller.py
```

If you need a non-default payout address, add:

```bash
export OMNICLAW_X402_EXACT_PAY_TO="0xYourSellerAddress"
```

Then pay the seller with:

```bash
omniclaw-cli inspect-x402 --recipient http://127.0.0.1:4021/compute?size=70000
omniclaw-cli pay --recipient http://127.0.0.1:4021/compute?size=70000 --idempotency-key x402-org-base-sepolia-001
```

Full runbook: [../examples/external-x402-facilitator/README.md](../examples/external-x402-facilitator/README.md).

Thirdweb-backed sellers normally configure their seller middleware with Thirdweb's own facilitator object. OmniClaw buyers do not need special Thirdweb configuration; they inspect and pay the seller's x402 endpoint through the standard buyer path.

For OmniClaw seller-side Thirdweb validation, set:

```env
THIRDWEB_SECRET_KEY=...
THIRDWEB_SERVER_WALLET_ADDRESS=0x...
THIRDWEB_X402_NETWORK=base-sepolia
```

Then create the seller gate with `facilitator="thirdweb"` and use the Thirdweb server wallet address as the seller address.

Thirdweb is different from the self-hosted OmniClaw exact facilitator:

- Thirdweb exposes `accepts`, `verify`, `settle`, `fetch`, and discovery over HTTP
- OmniClaw exact facilitator exposes `supported`, `verify`, and `settle`
- OmniClaw seller middleware or seller app still owns the resource URL and price policy

## Arc Testnet

Arc is supported as an exact-settlement EVM network profile:

- OmniClaw profile: `ARC-TESTNET`
- CAIP-2 network: `eip155:5042002`
- default RPC: `https://rpc.testnet.arc.network`
- explorer: `https://testnet.arcscan.app`
- USDC interface: `0x3600000000000000000000000000000000000000`

That means an Arc seller can advertise standard x402 `exact` requirements, the buyer can pay through OmniClaw policy controls, and settlement can be viewed on ArcScan.

Arc self-hosted exact is fully supported with this standard workflow:

- seller advertises `exact` on `eip155:5042002`
- OmniClaw buyer selects `x402` with `direct_wallet`
- OmniClaw exact facilitator handles `verify` and `settle`
- settlement confirms on Arc Testnet RPC

Practical boundary:

- yes, self-hosted OmniClaw exact can be used for Arc
- yes, the same exact model works for Base Sepolia and other supported EVM profiles
- no, this does not mean "every network automatically works"

For the profiles already configured in OmniClaw, nothing else needs to be invented in the product layer. The required network metadata is already present in code:

- CAIP-2 mapping
- default RPC
- explorer base URL where available
- default USDC asset address where available

The network must have:

- an EVM CAIP-2 mapping
- a configured network profile
- an RPC endpoint
- a USDC asset address compatible with the exact flow

So the operational requirement for an already configured profile is only:

- run the facilitator with a funded seller key
- run the seller surface with the same target profile
- run the buyer policy engine with a funded buyer key on that network
- execute `inspect-x402` and `pay`

That is a deployment requirement, not a missing architecture requirement.

For Arc Testnet, the buyer key must hold Arc Testnet USDC. The seller/facilitator key must hold Arc Testnet gas because it submits the x402 exact settlement transaction to the USDC contract.

To run only the Arc self-hosted exact facilitator:

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

The facilitator exposes:

| Endpoint | Purpose |
| --- | --- |
| `GET /supported` | Advertise supported x402 schemes and networks |
| `POST /verify` | Verify a signed x402 payment payload |
| `POST /settle` | Submit settlement on Arc Testnet |

For a visual Arc vendor demo, use the Arc marketplace showcase:

```bash
bash scripts/start_arc_marketplace_showcase_docker.sh
```

Runbook: [../examples/arc-marketplace-showcase/README.md](../examples/arc-marketplace-showcase/README.md).

The showcase includes a browser mini buyer agent. It calls the kiosk backend, and the kiosk backend calls the buyer Financial Policy Engine using `ARC_MARKETPLACE_BUYER_ENGINE_URL` and `ARC_MARKETPLACE_BUYER_TOKEN`. This keeps the browser flow simple while the Financial Policy Engine remains the payment authority boundary.

The Docker launcher starts:

| Service | URL |
| --- | --- |
| Browser UI | `http://127.0.0.1:8020` |
| Vendor kiosk | `http://172.18.0.51:8020` |
| Buyer policy engine | `http://172.18.0.52:8080` |
| Exact facilitator | `http://172.18.0.50:4022` |

It also prints the buyer Arc USDC balance, seller Arc gas balance, and the paid product URLs:

| Product | Price | URL |
| --- | --- | --- |
| Prime Market Scan | `$0.25` | `http://172.18.0.51:8020/buy/prime-market-scan` |
| Risk Oracle Brief | `$0.15` | `http://172.18.0.51:8020/buy/risk-oracle-brief` |
| Settlement Receipt Kit | `$0.10` | `http://172.18.0.51:8020/buy/settlement-receipt-kit` |

For ecosystem forms that require a contract address, use the Arc Testnet USDC contract used by x402 exact settlement:

```text
0x3600000000000000000000000000000000000000
```

OmniClaw does not require a custom application contract for this flow. The settlement transaction calls `transferWithAuthorization` on Arc Testnet USDC.

Latest public proof transaction:

```text
https://testnet.arcscan.app/tx/0xd40dc800a54bee4ff80da4709e65cfd3d0346eb1995ebc34fba433a6306b9219
```

## External Facilitators

External facilitators remain first-class. If a seller advertises an `exact` payment requirement using another facilitator, OmniClaw's buyer flow can still pay through the standard x402 SDK path as long as:

- the buyer has the required chain funds
- the seller requirements include a supported `exact` payment option
- the selected facilitator can verify and settle the payload

The product rule is simple: OmniClaw governs financial authority; facilitators settle supported x402 payment payloads.

### Thirdweb

Thirdweb is the recommended managed external facilitator path to validate next. It is a strong fit for teams that want broad EVM network coverage and gas sponsorship without operating their own facilitator.

Based on Thirdweb's x402 facilitator docs, their facilitator:

- verifies and submits x402 payments
- uses the seller's Thirdweb server wallet
- supports gasless transaction submission through EIP-7702
- exposes public HTTP `accepts`, `verify`, `settle`, `fetch`, and discovery endpoints that OmniClaw can call directly from Python
- supports payments across 170+ EVM chains
- supports tokens that expose ERC-2612 permit or ERC-3009 authorization

How this fits OmniClaw:

- buyer side: OmniClaw can pay Thirdweb-backed x402 endpoints through the standard `exact` buyer path
- seller side: a team can use Thirdweb's own seller/facilitator stack instead of running an OmniClaw facilitator
- policy layer: OmniClaw still controls whether the agent is allowed to pay before money moves

Recommended Thirdweb validation flow:

1. call Thirdweb's HTTP `accepts` endpoint through OmniClaw's Python facilitator adapter to generate seller requirements
2. capture a signed x402 `paymentPayload` and matching `paymentRequirements`
3. call Thirdweb's HTTP `verify` endpoint through OmniClaw's Python facilitator adapter
4. call Thirdweb's HTTP `settle` endpoint through OmniClaw's Python facilitator adapter
5. optionally test Thirdweb's HTTP `fetch` and discovery endpoints for ecosystem integration
6. confirm the transaction in the Thirdweb dashboard and chain explorer
7. run a full buyer flow against a Thirdweb-backed seller URL once seller credentials are available

The repo includes a direct HTTP validation target at [../examples/thirdweb-http-facilitator/README.md](../examples/thirdweb-http-facilitator/README.md).

When Thirdweb credentials are available, validate the full flow with the same proof checklist used for other facilitators: seller URL, requirements, payment result, settlement transaction, and final paid response.

## Operational Model

For production-like deployments, run the facilitator as separate infrastructure from the Financial Policy Engine.

Recommended separation:

- buyer Financial Policy Engine: enforces the buyer's policy and signs buyer-side actions
- seller app: exposes paid resources and advertises x402 requirements
- facilitator: verifies and settles x402 payloads

This separation matters because it keeps policy, resource serving, and settlement independently deployable.

## References

- Arc contract addresses: https://docs.arc.network/arc/references/contract-addresses
- Circle USDC contract addresses: https://developers.circle.com/stablecoins/usdc-contract-addresses
- Thirdweb x402 facilitator: https://portal.thirdweb.com/x402/facilitator
- x402 network and token support: https://docs.x402.org/core-concepts/network-and-token-support
