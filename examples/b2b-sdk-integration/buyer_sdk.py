from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from omniclaw import Network, OmniClaw


async def main() -> None:
    client = OmniClaw(network=Network.from_string(os.getenv("OMNICLAW_NETWORK", "BASE-SEPOLIA")))
    result = await client.pay(
        wallet_id=os.environ["OMNICLAW_BUYER_WALLET_ID"],
        recipient=os.environ["OMNICLAW_BUYER_RECIPIENT"],
        amount=os.getenv("OMNICLAW_BUYER_MAX_AMOUNT", "1.00"),
        purpose=os.getenv("OMNICLAW_BUYER_PURPOSE", "vendor payment"),
        idempotency_key=os.getenv("OMNICLAW_BUYER_IDEMPOTENCY_KEY", f"buyer-sdk-{uuid4()}"),
    )
    print(result.model_dump_json(indent=2) if hasattr(result, "model_dump_json") else result)


if __name__ == "__main__":
    asyncio.run(main())
