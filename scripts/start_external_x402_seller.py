#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OMNICLAW_X402_EXACT_NETWORK_PROFILE", "BASE-SEPOLIA")
os.environ.setdefault("OMNICLAW_X402_EXACT_FACILITATOR_URL", "https://x402.org/facilitator")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.start_x402_exact_testnet_seller import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("OMNICLAW_X402_EXACT_PORT", "4021"))
    uvicorn.run(app, host="0.0.0.0", port=port)
