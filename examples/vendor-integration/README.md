# Vendor Integration Guide

This guide shows how a traditional software vendor can expose a paid HTTP surface using the OmniClaw Python SDK.

Use this when you (a human developer or business) own the product endpoint and want autonomous agents to pay before they receive data, compute, or another gated response.

> **Note on Tooling:** Vendors build applications using the **OmniClaw Python SDK** (`client.sell()`). The `omniclaw-cli` tool is designed for the autonomous agents that will act as the *buyers* of your service.

## What It Covers

- Vendor-side payment gating with FastAPI
- HTTP `402 Payment Required` flows
- Production-safe vendor APIs without human checkout
- SDK-first seller integration for B2B and enterprise deployments

## Recommended Shape

Keep the public surface simple:

- one paid endpoint per product class
- one clear price or pricing tier per endpoint
- one idempotency key per job or request
- one seller-side log stream for verification and audit

Example public endpoint:

```text
https://vendor.example.com/compute
```

## Vendor Setup (FastAPI SDK)

To require payment for an endpoint, integrate the OmniClaw SDK into your application. See the provided `app.py` for the complete example.

```python
from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

@app.get("/compute")
async def premium_compute(
    payment=client.sell("$0.25", seller_address="0xYourVendorWalletAddress"),
):
    # This code only runs AFTER payment is verified and settled!
    return {
        "status": "success",
        "paid_by": payment.payer,
        "result": {"data": "..."}
    }
```

Run your vendor application:

```bash
uvicorn app:app --port 8000
```

## Facilitator Options

The vendor controls the seller integration and chooses the settlement path.

### Circle Gateway

Default seller path when using Circle Gateway:

```python
payment=client.sell("$0.25", seller_address="0xYourVendorWalletAddress")
```

### Thirdweb Managed x402

Use Thirdweb when the vendor wants managed x402 facilitator coverage:

```bash
export THIRDWEB_SECRET_KEY="..."
export THIRDWEB_SERVER_WALLET_ADDRESS="0xThirdwebServerWallet"
export THIRDWEB_X402_NETWORK="base-sepolia"
```

```python
payment=client.sell(
    "$0.25",
    seller_address="0xThirdwebServerWallet",
    facilitator="thirdweb",
)
```

### OmniClaw Self-Hosted Exact

Use this when the vendor wants to run its own exact facilitator for Arc, Base Sepolia, or another supported EVM profile:

```bash
omniclaw facilitator exact \
  --network-profile ARC-TESTNET \
  --port 4022
```

```bash
export OMNICLAW_X402_SELF_HOSTED_FACILITATOR_URL="http://127.0.0.1:4022"
export OMNICLAW_X402_EXACT_NETWORK_PROFILE="ARC-TESTNET"
```

```python
payment=client.sell(
    "$0.25",
    seller_address="0xYourVendorWalletAddress",
    facilitator="omniclaw",
)
```

## Buyer Integration

Buyers can pay from an agent CLI, a backend using the SDK, or any compatible x402 buyer.

Agent buyer:

```bash
export OMNICLAW_SERVER_URL="http://127.0.0.1:8080"
export OMNICLAW_TOKEN="agent-token-123"

# The agent inspects your requirements
omniclaw-cli inspect-x402 --recipient https://vendor.example.com/compute

# The agent executes the payment
omniclaw-cli pay --recipient https://vendor.example.com/compute --idempotency-key job-123
```

SDK buyer:

```python
result = await client.pay(
    wallet_id="buyer-wallet-id",
    recipient="https://vendor.example.com/compute",
    amount="1.00",
    purpose="vendor compute",
    idempotency_key="job-123",
)
```

## Verification Checklist

- unauthenticated/unpaid requests return `402 Payment Required`
- paid requests return `200 OK` and the expected product payload
- the seller log shows a matching settlement event
- the published URL does not require a human login flow

## Related Examples

- [Business Compute](../business-compute/README.md) - A larger example of a vendor web app with sessions.
- [B2B SDK Integration](../b2b-sdk-integration/README.md)
- [Machine-to-Machine](../machine-to-machine/README.md)
