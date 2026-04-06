"""
Simple x402 Facilitator Mock Server.
Implements the x402 protocol (402 Payment Required) for testing.
"""

import time
import uuid

import uvicorn
from fastapi import FastAPI, Header, Request, Response

app = FastAPI()

# In-memory store for paid requests (just for testing idempotency logic)
PAID_REQUESTS = {}


@app.get("/weather")
async def get_weather(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("x402 "):
        return Response(
            status_code=402,
            headers={
                "WWW-Authenticate": 'x402 payment_url="http://localhost:8000/x402/facilitator", invoice_id="'
                + str(uuid.uuid4())
                + '"',
                "x402-amount": "1000",
                "x402-token": "USDC",
            },
            content="Payment Required",
        )
    return {"weather": "sunny", "temperature": 25}


@app.get("/premium-content")
async def get_premium(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("x402 "):
        return Response(
            status_code=402,
            headers={
                "WWW-Authenticate": 'x402 payment_url="http://localhost:8000/x402/facilitator", invoice_id="'
                + str(uuid.uuid4())
                + '"',
                "x402-amount": "10000",
                "x402-token": "USDC",
            },
            content="Payment Required",
        )
    return {"content": "Ultra secret data 💎"}


@app.post("/x402/facilitator")
async def facilitator(request: Request):
    data = await request.json()
    # Mock successful settlement
    return {
        "status": "success",
        "transaction_id": f"mock_tx_{uuid.uuid4().hex[:8]}",
        "settled_at": int(time.time()),
        "facilitator_sig": "mock_signature_0x123",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
