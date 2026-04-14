from __future__ import annotations

import os

from fastapi import FastAPI

from omniclaw import OmniClaw


app = FastAPI(title="OmniClaw B2B Vendor - Thirdweb")
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
        "service": "vendor-thirdweb-report",
        "paid_by": payment.payer,
        "amount": payment.amount,
        "report": {"status": "ready"},
    }

