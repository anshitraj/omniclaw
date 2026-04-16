#!/usr/bin/env python3
from __future__ import annotations

import os

from eth_account import Account
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from web3 import Web3
from omniclaw.facilitator.networks import (
    build_exact_asset_amount,
    resolve_exact_settlement_network_profile,
)
from omniclaw.protocols.x402_compat import patch_x402_web3_compat


patch_x402_web3_compat()

from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


APP_PORT = int(_env("OMNICLAW_X402_EXACT_PORT", "4021"))
NETWORK_PROFILE = resolve_exact_settlement_network_profile(
    _env("OMNICLAW_X402_EXACT_NETWORK_PROFILE", _env("OMNICLAW_NETWORK", "BASE-SEPOLIA"))
)


def _resolve_pay_to() -> str:
    explicit = os.environ.get("OMNICLAW_X402_EXACT_PAY_TO", "").strip()
    if explicit:
        return Web3.to_checksum_address(explicit)

    private_key = os.environ.get("OMNICLAW_PRIVATE_KEY", "").strip()
    if private_key:
        return Account.from_key(private_key).address

    raise RuntimeError(
        "Set OMNICLAW_X402_EXACT_PAY_TO or OMNICLAW_PRIVATE_KEY before starting the seller"
    )


PAY_TO = _resolve_pay_to()
NETWORK = _env("OMNICLAW_X402_EXACT_NETWORK", NETWORK_PROFILE.caip2)
PRICE = _env("OMNICLAW_X402_EXACT_PRICE", "$0.25")
FACILITATOR_URL = _env("OMNICLAW_X402_EXACT_FACILITATOR_URL", "https://x402.org/facilitator")


app = FastAPI(title=f"OmniClaw Exact Seller ({NETWORK_PROFILE.label})")

facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
server = x402ResourceServer(facilitator)
exact_scheme = ExactEvmServerScheme()
exact_scheme.register_money_parser(
    lambda amount, network: build_exact_asset_amount(
        profile=NETWORK_PROFILE,
        decimal_amount=amount,
        network=str(network),
    )
)
server.register("eip155:*", exact_scheme)

routes = {
    "GET /compute": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                price=PRICE,
                network=NETWORK,
                pay_to=PAY_TO,
            )
        ],
        description=f"{NETWORK_PROFILE.label} exact x402 compute job",
        mime_type="application/json",
    )
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)


@app.get("/compute")
async def compute(size: int = 70000) -> JSONResponse:
    return JSONResponse(
        {
            "service": "x402-exact-testnet-seller",
            "job": "prime-count",
            "input": {"size": size},
            "output": {"prime_count": _prime_count(size)},
            "network": NETWORK,
            "network_profile": NETWORK_PROFILE.label,
            "asset": NETWORK_PROFILE.default_asset_address,
            "price": PRICE,
            "facilitator": FACILITATOR_URL,
        }
    )


def _prime_count(limit: int) -> int:
    if limit < 2:
        return 0
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    n = 2
    while n * n <= limit:
        if sieve[n]:
            start = n * n
            step = n
            sieve[start : limit + 1 : step] = b"\x00" * (((limit - start) // step) + 1)
        n += 1
    return int(sum(sieve))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
