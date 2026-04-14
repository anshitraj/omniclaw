# OmniClaw

**Policy-controlled payments for AI agents and machine services.**

[![CI](https://github.com/omnuron/omniclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/omnuron/omniclaw/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omniclaw.svg)](https://pypi.org/project/omniclaw/)
[![Python](https://img.shields.io/pypi/pyversions/omniclaw.svg)](https://pypi.org/project/omniclaw/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

OmniClaw lets software agents pay, earn, and access paid APIs without giving the agent unrestricted wallet authority.

The owner runs a **Financial Policy Engine**. Agents and applications execute through constrained interfaces. Every payment is checked against policy before funds move.

## Why It Exists

AI agents can browse, reason, call APIs, and run workflows. The hard part is money movement.

OmniClaw solves the control problem:

- agents can pay for services without receiving raw wallet control
- sellers can monetize APIs through x402-compatible payment gates
- operators can enforce budgets, recipient rules, confirmations, and route selection
- payments can settle through Circle Gateway, standard x402 exact settlement, or a self-hosted exact facilitator

## Core Surfaces

| Surface | Used By | Purpose |
| --- | --- | --- |
| Financial Policy Engine | owner / operator | Enforces policy, signs allowed actions, exposes the control API |
| `omniclaw-cli` | agents / automation | Executes buyer payments through the policy engine without direct key access |
| Python SDK | developers / vendors | Embeds buyer payments and seller monetization into Python applications |
| Seller middleware | vendors / enterprises | Turns production HTTP routes into paid x402 endpoints |
| Exact facilitator | operators | Optional self-hosted x402 exact settlement for supported EVM networks |

## Install

```bash
pip install omniclaw
```

For local development:

```bash
uv add omniclaw
```

## Choose The Right Path

| If you are building... | Use... | Why |
| --- | --- | --- |
| An agent that needs to buy services | Financial Policy Engine + `omniclaw-cli` | The agent can pay without holding raw wallet authority |
| A backend service that buys from paid APIs | Python SDK `client.pay(...)` | Programmatic payments inside your own app |
| A vendor or enterprise API | Python SDK `client.sell(...)` | Production paid endpoints inside your application |
| A temporary local paid agent service | `omniclaw-cli serve` | Fast agent-owned/local monetization, not the enterprise seller path |
| Custom or Arc exact settlement infrastructure | `omniclaw facilitator exact` | Self-hosted standard x402 `verify` / `settle` |

## Credential Model

OmniClaw has two different key surfaces:

- `OMNICLAW_PRIVATE_KEY` is the EOA key used for direct x402 exact settlement and Circle Gateway nanopayment signing.
- `ENTITY_SECRET` is Circle's developer-controlled wallet encryption secret.

If your Circle account/API key already has an Entity Secret, set it directly. Circle allows one active Entity Secret per account/API key. OmniClaw only auto-generates and registers a new one when no existing secret is provided or found in its managed local credential store.

```bash
export CIRCLE_API_KEY="..."
export ENTITY_SECRET="your_existing_64_char_hex_entity_secret"
export OMNICLAW_PRIVATE_KEY="0x..."
```

For a non-interactive local setup:

```bash
omniclaw setup --api-key "$CIRCLE_API_KEY" --entity-secret "$ENTITY_SECRET"
```

## Buyer: Agent CLI

Use this when an autonomous agent or script should pay through the **Financial Policy Engine** (run via the `omniclaw server` command).

Start the owner-side policy engine:

```bash
export OMNICLAW_PRIVATE_KEY="0x..."
export OMNICLAW_AGENT_TOKEN="agent-token"
export OMNICLAW_AGENT_POLICY_PATH="./policy.json"
export OMNICLAW_NETWORK="BASE-SEPOLIA"
export OMNICLAW_RPC_URL="https://sepolia.base.org"

omniclaw server --port 8080
```

Configure the agent runtime:

```bash
export OMNICLAW_SERVER_URL="http://localhost:8080"
export OMNICLAW_TOKEN="agent-token"
```

Pay a protected x402 URL:

```bash
omniclaw-cli can-pay --recipient https://seller.example.com/compute
omniclaw-cli inspect-x402 --recipient https://seller.example.com/compute
omniclaw-cli pay --recipient https://seller.example.com/compute --idempotency-key job-123
```

Pay a direct address:

```bash
omniclaw-cli pay \
  --recipient 0xRecipientAddress \
  --amount 5.00 \
  --purpose "service payment" \
  --idempotency-key job-123
```

## Buyer: Python SDK

Use this when a Python service should pay programmatically.

```python
from omniclaw import Network, OmniClaw

client = OmniClaw(network=Network.BASE_SEPOLIA)

result = await client.pay(
    wallet_id="wallet-id",
    recipient="https://seller.example.com/compute",
    amount="1.00",
    purpose="compute job",
    idempotency_key="job-123",
)

print(result.status, result.blockchain_tx or result.transaction_id)
```

For x402 URLs, `amount` acts as the maximum spend allowed for that request. The seller's x402 requirements define the exact amount to settle.

## Seller: Vendor / Enterprise SDK

Use this when a vendor, enterprise, or application team wants to monetize API routes. This is the default seller path for real products.

```python
from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

@app.get("/premium-data")
async def premium_data(
    payment=client.sell("$0.25", seller_address="0xYourSellerWallet")
):
    return {
        "data": "premium content",
        "paid_by": payment.payer,
        "amount": payment.amount,
    }
```

The route returns `402 Payment Required` until the buyer submits a valid x402 payment. After verification and settlement, the handler executes and returns the paid response.

## Seller: Agent-Owned Local Service

Use this only when an agent or local automation wants to expose a temporary paid service. It is not the recommended integration path for vendor or enterprise APIs.

```bash
omniclaw-cli serve \
  --price 0.25 \
  --endpoint /compute \
  --exec "python compute_job.py" \
  --port 8000
```

For vendor and enterprise APIs, use the Python SDK middleware so payments are part of the application itself.

## Settlement Paths

OmniClaw is settlement-rail aware and policy-first. The buyer uses one execution path while the seller advertises the x402 requirements it supports.

| Path | Status | Notes |
| --- | --- | --- |
| Circle Gateway `GatewayWalletBatched` | supported | Gasless nanopayments through Circle Gateway |
| Standard x402 exact via x402.org | supported (Base Sepolia) | External exact facilitator validation |
| OmniClaw self-hosted exact facilitator | supported (Arc Testnet) | Self-hosted `verify` and `settle` for supported EVM profiles |
| Thirdweb x402 HTTP facilitator | supported | Managed Thirdweb account required |

Current capabilities:

- Base Sepolia external x402 exact settlement
- Arc Testnet self-hosted exact settlement
- buyer/seller wallet separation
- policy-controlled buyer route through `/api/v1/pay`

## Examples

| Example | Demonstrates |
| --- | --- |
| [B2B SDK Integration](examples/b2b-sdk-integration/README.md) | Enterprise buyer/seller SDK integration with multiple facilitators |
| [Machine to Machine](examples/machine-to-machine/README.md) | One machine service paying another |
| [Machine to Vendor](examples/machine-to-vendor/README.md) | Agent buyer paying a vendor-owned API |
| [Vendor Integration](examples/vendor-integration/README.md) | Vendor-side paid API integration |
| [Business Compute](examples/business-compute/README.md) | Payment-gated compute service |
| [Local Economy](examples/local-economy/README.md) | Local buyer/seller economy with Docker |
| [External x402 Facilitator](examples/external-x402-facilitator/README.md) | x402.org Base Sepolia validation |
| [Thirdweb HTTP Facilitator](examples/thirdweb-http-facilitator/README.md) | Thirdweb HTTP API validation |

## Documentation

| Start Here | Use Case |
| --- | --- |
| [Documentation Index](docs/README.md) | Complete docs map |
| [Developer Guide](docs/developer-guide.md) | Python SDK buyer and seller integration |
| [Agent Getting Started](docs/agent-getting-started.md) | Agent CLI setup and usage |
| [CLI Reference](docs/cli-reference.md) | Generated `omniclaw-cli` reference |
| [Operator CLI](docs/operator-cli.md) | `omniclaw server`, setup, policy, facilitator commands |
| [Policy Reference](docs/POLICY_REFERENCE.md) | Policy file structure and controls |
| [Facilitators](docs/facilitators.md) | x402 facilitator model and deployment paths |
| [Production Readiness](docs/production-readiness.md) | Proof status and release checklist |
| [API Reference](docs/API_REFERENCE.md) | Python SDK and API details |

## Development

```bash
uv sync --extra dev
uv run pytest
```

Release verification:

```bash
./scripts/release_verify.sh
```

## Security

OmniClaw is designed around separation of authority: agents do not need unrestricted wallet access. Production deployments should still use restricted keys, policy limits, confirmation thresholds, hardened secrets, and audited infrastructure.

Report vulnerabilities through [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
