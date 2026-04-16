from __future__ import annotations

import os

from fastapi import FastAPI

from omniclaw import OmniClaw


app = FastAPI(title="OmniClaw B2B Vendor - Self-Hosted Exact")
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
        "service": "vendor-self-hosted-exact-compute",
        "paid_by": payment.payer,
        "amount": payment.amount,
        "network": os.getenv("OMNICLAW_X402_EXACT_NETWORK_PROFILE", "ARC-TESTNET"),
        "result": {"status": "complete"},
    }

