"""
Vendor Integration Example: FastAPI app protected by OmniClaw

This example demonstrates how a human developer (a vendor or business)
uses the OmniClaw Python SDK to monetize an API endpoint.

Unlike autonomous agents that use `omniclaw-cli`, vendors integrate
the OmniClaw SDK directly into their backend services.
"""

from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI(title="Vendor Payment-Gated API")
client = OmniClaw()

# 1. Provide your seller wallet address.
# This represents the vendor's wallet where payments will settle.
# For this example, we use a placeholder or assume it's passed via env.
import os
SELLER_ADDRESS = os.environ.get("SELLER_ADDRESS", "0xYourVendorWalletAddress")

# 2. Add an endpoint that is free
@app.get("/status")
async def status():
    return {"status": "ok", "message": "This endpoint is free."}

# 3. Add an endpoint protected by OmniClaw x402 payment gate (Price: $0.25)
# The `client.sell` dependency handles the 402 Payment Required handshake
# and only allows the request through once settlement is verified.
@app.get("/compute")
async def premium_compute(
    payment=client.sell("$0.25", seller_address=SELLER_ADDRESS),
):
    # If the code reaches here, OmniClaw has verified the payment!
    
    # You can access payment metadata for logging or audit
    payer_address = payment.payer
    
    return {
        "status": "success",
        "message": "Payment verified. Compute complete.",
        "paid_by": payer_address,
        "amount": "$0.25",
        "result": {
            "computation": "complex_data_analysis_result"
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Run the vendor app
    uvicorn.run(app, host="127.0.0.1", port=8000)
