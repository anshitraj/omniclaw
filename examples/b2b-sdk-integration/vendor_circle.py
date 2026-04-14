from __future__ import annotations

import os

from fastapi import FastAPI

from omniclaw import Network, OmniClaw


app = FastAPI(title="OmniClaw B2B Vendor - Circle Gateway")
client = OmniClaw(network=Network.from_string(os.getenv("OMNICLAW_NETWORK", "BASE-SEPOLIA")))


@app.get("/compute")
async def compute(
    payment=client.sell("$0.25", seller_address=os.environ["SELLER_ADDRESS"]),
):
    return {
        "service": "vendor-circle-compute",
        "paid_by": payment.payer,
        "amount": payment.amount,
        "result": {"status": "complete"},
    }

