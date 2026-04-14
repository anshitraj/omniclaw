# Machine-to-Vendor Payments

This example documents the flow where an external machine or agent pays a vendor-owned service.

Use it when the vendor controls the product surface and the buyer is a separate agent, workflow, or integration.

## What It Proves

- a vendor can publish a paid endpoint without a human checkout
- an external buyer can discover the required payment scheme
- the paid response unlocks only after settlement
- the vendor keeps control of the product and logs

## Example Vendor Surface

```text
https://vendor.example.com/premium-report
```

The vendor should expose that URL through the SDK, for example:

```python
from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

@app.get("/premium-report")
async def premium_report(
    payment=client.sell("$0.50", seller_address="0xVendorWallet"),
):
    return {"report": "paid report", "paid_by": payment.payer}
```

The buyer treats that URL as a paid resource.

Agent buyer (requires the Financial Policy Engine `omniclaw server` to be running):

```bash
export OMNICLAW_SERVER_URL="http://127.0.0.1:8080"
export OMNICLAW_TOKEN="buyer-agent-token"

omniclaw-cli inspect-x402 --recipient https://vendor.example.com/premium-report
omniclaw-cli pay --recipient https://vendor.example.com/premium-report --idempotency-key report-2026-04-14
```

SDK buyer:

```python
result = await client.pay(
    wallet_id="buyer-wallet-id",
    recipient="https://vendor.example.com/premium-report",
    amount="1.00",
    purpose="premium report",
    idempotency_key="report-2026-04-14",
)
```

## Vendor Responsibilities

- advertise the paid endpoint clearly
- return `402 Payment Required` until payment is verified
- use a stable product URL
- keep the response public-safe and deterministic
- log settlement and fulfillment events separately

## Buyer Responsibilities

- inspect the seller requirements before paying
- use a stable idempotency key for each attempt
- do not assume a specific rail unless the seller advertises it
- retry only with the same job identity

## Operational Notes

The vendor does not need to know the buyer's internal system.
The buyer does not need direct wallet access.
OmniClaw sits between the policy decision and the payment execution.

For vendor-facing API surfaces, pair this runbook with:

- [B2B SDK Integration](../b2b-sdk-integration/README.md)
- [Vendor Integration](../vendor-integration/README.md)
- [External x402 Facilitator](../external-x402-facilitator/README.md)
- [Thirdweb HTTP Facilitator](../thirdweb-http-facilitator/README.md)
