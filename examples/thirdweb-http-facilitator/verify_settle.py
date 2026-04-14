#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from omniclaw.seller import create_facilitator


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open() as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


async def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Thirdweb x402 HTTP facilitator calls.")
    parser.add_argument("--payment-payload", required=True, help="Path to signed payment payload JSON")
    parser.add_argument(
        "--payment-requirements",
        required=True,
        help="Path to selected payment requirements JSON",
    )
    parser.add_argument("--verify-only", action="store_true", help="Do not call settle")
    parser.add_argument(
        "--secret-key",
        default=os.environ.get("THIRDWEB_SECRET_KEY"),
        help="Thirdweb secret key. Defaults to THIRDWEB_SECRET_KEY.",
    )
    args = parser.parse_args()

    if not args.secret_key:
        raise SystemExit("Set THIRDWEB_SECRET_KEY or pass --secret-key")

    facilitator = create_facilitator(provider="thirdweb", api_key=args.secret_key)
    try:
        payment_payload = load_json(args.payment_payload)
        payment_requirements = load_json(args.payment_requirements)

        verify_result = await facilitator.verify(payment_payload, payment_requirements)
        output: dict[str, Any] = {
            "facilitator": facilitator.name,
            "base_url": facilitator.base_url,
            "verify": {
                "is_valid": verify_result.is_valid,
                "payer": verify_result.payer,
                "invalid_reason": verify_result.invalid_reason,
            },
        }

        if not args.verify_only:
            settle_result = await facilitator.settle(payment_payload, payment_requirements)
            output["settle"] = {
                "success": settle_result.success,
                "transaction": settle_result.transaction,
                "network": settle_result.network,
                "payer": settle_result.payer,
                "error_reason": settle_result.error_reason,
            }

        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    finally:
        await facilitator.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
