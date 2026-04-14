# B2B SDK Integration

This is the enterprise/vendor integration path.

Use this when a business owns the product surface, backend, API, or workflow. The vendor integrates OmniClaw through the Python SDK. Agents may still buy from that vendor, but the vendor does not need to run `omniclaw-cli`.

## Deployment Model

| Component | Who Runs It | Purpose |
| --- | --- | --- |
| Vendor app | enterprise/vendor | Serves the product API and uses `client.sell(...)` |
| Buyer app or agent | customer/partner/internal team | Pays through SDK or CLI |
| Financial Policy Engine | owner/operator | Optional API service for policy-controlled agent execution |
| Facilitator | vendor/operator/managed provider | Verifies and settles x402 payloads |

The Financial Policy Engine is the hosted policy-control service built on the same OmniClaw SDK primitives. Use it when the payer is an agent, workflow, or external automation that should not hold raw wallet authority.

For pure backend-to-backend integrations, a business can also embed the SDK directly in its own service and apply guards/policy in-process.

## Scenario 1: Vendor API With Circle Gateway

Use this when the vendor wants Circle Gateway `GatewayWalletBatched` settlement.

Environment:

```bash
export CIRCLE_API_KEY="..."
export OMNICLAW_PRIVATE_KEY="0xVendorOrOperatorKey"
export OMNICLAW_NETWORK="BASE-SEPOLIA"
export OMNICLAW_RPC_URL="https://sepolia.base.org"
export SELLER_ADDRESS="0xVendorSellerAddress"
```

Vendor app:

```python
import os

from fastapi import FastAPI
from omniclaw import Network, OmniClaw

app = FastAPI()
client = OmniClaw(network=Network.BASE_SEPOLIA)

@app.get("/compute")
async def compute(
    payment=client.sell("$0.25", seller_address=os.environ["SELLER_ADDRESS"]),
):
    return {
        "service": "vendor-compute",
        "paid_by": payment.payer,
        "result": {"job": "complete"},
    }
```

Executable example: `vendor_circle.py`

Run:

```bash
uvicorn vendor_app:app --host 0.0.0.0 --port 8000
```

## Scenario 2: Vendor API With Thirdweb Managed x402

Use this when the vendor wants managed external x402 settlement and Thirdweb server wallet support.

Environment:

```bash
export THIRDWEB_SECRET_KEY="..."
export THIRDWEB_SERVER_WALLET_ADDRESS="0xThirdwebServerWallet"
export THIRDWEB_X402_NETWORK="base-sepolia"
export SELLER_ADDRESS="$THIRDWEB_SERVER_WALLET_ADDRESS"
```

Vendor app:

```python
import os

from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

@app.get("/report")
async def report(
    payment=client.sell(
        "$0.50",
        seller_address=os.environ["SELLER_ADDRESS"],
        facilitator="thirdweb",
    ),
):
    return {
        "service": "vendor-report",
        "paid_by": payment.payer,
        "report": {"status": "ready"},
    }
```

Executable example: `vendor_thirdweb.py`

Thirdweb creates the seller `accepts` requirements and handles `verify` / `settle`. OmniClaw still controls the SDK surface and exposes the same paid endpoint behavior.

## Scenario 3: Vendor API With OmniClaw Self-Hosted Exact Facilitator

Use this when the vendor wants self-hosted exact settlement on a supported EVM profile such as Arc Testnet or Base Sepolia.

Start the facilitator:

```bash
export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="0xFacilitatorKey"

omniclaw facilitator exact \
  --network-profile ARC-TESTNET \
  --port 4022
```

Vendor app environment:

```bash
export OMNICLAW_X402_SELF_HOSTED_FACILITATOR_URL="http://127.0.0.1:4022"
export OMNICLAW_X402_EXACT_NETWORK_PROFILE="ARC-TESTNET"
export SELLER_ADDRESS="0xVendorSellerAddress"
```

Vendor app:

```python
import os

from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

@app.get("/arc-compute")
async def arc_compute(
    payment=client.sell(
        "$0.25",
        seller_address=os.environ["SELLER_ADDRESS"],
        facilitator="omniclaw",
    ),
):
    return {
        "service": "arc-vendor-compute",
        "paid_by": payment.payer,
        "result": {"network": "ARC-TESTNET", "status": "complete"},
    }
```

Executable example: `vendor_self_hosted_exact.py`

In this mode:

- the vendor app creates `accepts`
- the self-hosted OmniClaw facilitator handles `/verify` and `/settle`
- the buyer can pay with OmniClaw CLI, OmniClaw SDK, or any compatible x402 buyer

## Scenario 4: Enterprise Buyer With SDK

Use this when a backend service, not an interactive agent, needs to buy from a paid vendor endpoint.

```python
from omniclaw import Network, OmniClaw

client = OmniClaw(network=Network.BASE_SEPOLIA)

result = await client.pay(
    wallet_id="enterprise-wallet-id",
    recipient="https://vendor.example.com/compute",
    amount="1.00",
    purpose="vendor compute job",
    idempotency_key="compute-job-2026-04-14-001",
)

if not result.success:
    raise RuntimeError(result.error or "payment failed")

print(result.status, result.blockchain_tx or result.transaction_id)
```

Executable example: `buyer_sdk.py`

## Scenario 5: Enterprise Buyer With Policy Engine

Use this when the payer is an internal agent, worker, or partner-facing integration and the enterprise wants a network boundary between the agent and signing authority.

Policy engine environment:

```bash
export OMNICLAW_PRIVATE_KEY="0xEnterpriseBuyerKey"
export OMNICLAW_AGENT_TOKEN="enterprise-agent-token"
export OMNICLAW_AGENT_POLICY_PATH="./policy.json"
export OMNICLAW_NETWORK="BASE-SEPOLIA"
export OMNICLAW_RPC_URL="https://sepolia.base.org"

omniclaw server --port 8080
```

Agent or worker environment:

```bash
export OMNICLAW_SERVER_URL="https://policy.enterprise.example"
export OMNICLAW_TOKEN="enterprise-agent-token"
```

The worker can now call the policy engine instead of holding wallet authority directly. The CLI is one client for this API; an enterprise can also call the API from its own worker.

## Deployment Checklist

- Choose the seller path: Circle Gateway, Thirdweb, or OmniClaw self-hosted exact.
- Put the vendor product API behind `client.sell(...)`.
- Run the buyer through SDK directly or through the Financial Policy Engine.
- Use one idempotency key per business job.
- Log seller fulfillment separately from settlement.
- Capture `402`, `inspect`, `pay`, settlement tx, and final paid response before production traffic.
