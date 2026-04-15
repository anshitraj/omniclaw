from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isqrt
from typing import Any

import httpx
from eth_account import Account
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from web3 import Web3

from omniclaw.facilitator.networks import (
    build_exact_asset_amount,
    resolve_exact_settlement_network_profile,
)
from omniclaw.protocols.x402_compat import patch_x402_web3_compat

patch_x402_web3_compat()

from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption  # noqa: E402
from x402.http.middleware.fastapi import PaymentMiddlewareASGI  # noqa: E402
from x402.http.types import RouteConfig  # noqa: E402
from x402.mechanisms.evm.exact import ExactEvmServerScheme  # noqa: E402
from x402.server import x402ResourceServer  # noqa: E402


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


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


APP_PORT = int(_env("ARC_MARKETPLACE_PORT", "8020"))
NETWORK_PROFILE = resolve_exact_settlement_network_profile(
    _env("OMNICLAW_X402_EXACT_NETWORK_PROFILE", _env("OMNICLAW_NETWORK", "ARC-TESTNET"))
)
NETWORK = _env("OMNICLAW_X402_EXACT_NETWORK", NETWORK_PROFILE.caip2)
FACILITATOR_URL = _env("OMNICLAW_X402_EXACT_FACILITATOR_URL", "http://127.0.0.1:4022")
PUBLIC_BASE_URL = _env("ARC_MARKETPLACE_PUBLIC_BASE_URL", f"http://127.0.0.1:{APP_PORT}")
BUYER_BASE_URL = _env("ARC_MARKETPLACE_BUYER_BASE_URL", PUBLIC_BASE_URL)
BUYER_ENGINE_URL = _env("ARC_MARKETPLACE_BUYER_ENGINE_URL")
BUYER_ENGINE_TOKEN = _env("ARC_MARKETPLACE_BUYER_TOKEN")
EXPLORER_BASE_URL = _env(
    "ARC_MARKETPLACE_EXPLORER_BASE_URL",
    NETWORK_PROFILE.explorer_base_url or "https://testnet.arcscan.app/tx/",
)
PAY_TO = _resolve_pay_to()


@dataclass(frozen=True)
class KioskProduct:
    slug: str
    label: str
    price: str
    lane: str
    description: str
    endpoint: str
    accent: str


PRODUCTS = (
    KioskProduct(
        slug="prime-market-scan",
        label="Prime Market Scan",
        price="$0.25",
        lane="compute",
        description="Runs a deterministic prime-count job for a buyer agent.",
        endpoint="/buy/prime-market-scan",
        accent="amber",
    ),
    KioskProduct(
        slug="risk-oracle-brief",
        label="Risk Oracle Brief",
        price="$0.15",
        lane="data",
        description="Returns a compact vendor-risk signal for an autonomous workflow.",
        endpoint="/buy/risk-oracle-brief",
        accent="blue",
    ),
    KioskProduct(
        slug="settlement-receipt-kit",
        label="Settlement Receipt Kit",
        price="$0.10",
        lane="proof",
        description="Packages the paid response fields needed for an ArcScan proof.",
        endpoint="/buy/settlement-receipt-kit",
        accent="green",
    ),
)

EVENTS: list[dict[str, Any]] = []
FULFILLMENTS: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _record(stage: str, message: str, *, product: str | None = None) -> None:
    EVENTS.insert(
        0,
        {
            "time": _now(),
            "stage": stage,
            "message": message,
            "product": product,
        },
    )
    del EVENTS[80:]


def _extract_buyer(request: Request) -> str | None:
    """Extract the buyer address from x402 payment state set by the middleware."""
    try:
        payload = getattr(request.state, "payment_payload", None)
        if payload is None:
            return None

        def _search(obj: Any, depth: int = 0) -> str | None:
            if depth > 5:
                return None
            if isinstance(obj, dict):
                for key in ("from", "from_address", "payer", "sender", "fromAddress"):
                    if key in obj and obj[key]:
                        return str(obj[key])
                for val in obj.values():
                    if isinstance(val, (dict, list)):
                        result = _search(val, depth + 1)
                        if result:
                            return result
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    result = _search(item, depth + 1)
                    if result:
                        return result
            elif hasattr(obj, "__dict__"):
                for attr_name in ("from_address", "payer", "sender", "fromAddress"):
                    val = getattr(obj, attr_name, None)
                    if val:
                        return str(val)
                for val in vars(obj).values():
                    if isinstance(val, (dict, list)) or hasattr(val, "__dict__"):
                        result = _search(val, depth + 1)
                        if result:
                            return result
            return None

        if hasattr(payload, "to_dict"):
            as_dict = payload.to_dict()
            result = _search(as_dict)
            if result:
                return result
        if hasattr(payload, "model_dump"):
            as_dict = payload.model_dump()
            result = _search(as_dict)
            if result:
                return result

        if isinstance(payload, dict):
            return _search(payload)

        if hasattr(payload, "__dict__"):
            return _search(payload)

        return None
    except Exception:
        return None


def _prime_count(limit: int) -> int:
    if limit < 2:
        return 0
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for value in range(2, isqrt(limit) + 1):
        if sieve[value]:
            start = value * value
            sieve[start : limit + 1 : value] = b"\x00" * (((limit - start) // value) + 1)
    return int(sum(sieve))


def _product_by_slug(slug: str) -> KioskProduct:
    for product in PRODUCTS:
        if product.slug == slug:
            return product
    raise KeyError(slug)


def _paid_url(product: KioskProduct, *, public: bool = False) -> str:
    base = PUBLIC_BASE_URL if public else BUYER_BASE_URL
    return f"{base.rstrip('/')}{product.endpoint}"


app = FastAPI(title="OmniClaw Arc Marketplace Showcase")

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
    f"GET {product.endpoint}": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                price=product.price,
                network=NETWORK,
                pay_to=PAY_TO,
            )
        ],
        description=f"{product.label} on {NETWORK_PROFILE.label}",
        mime_type="application/json",
    )
    for product in PRODUCTS
}
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)


@app.on_event("startup")
async def startup() -> None:
    _record("kiosk", f"Arc marketplace online with {len(PRODUCTS)} paid vendor services")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/api/catalog")
async def catalog() -> dict[str, Any]:
    return {
        "network_profile": NETWORK_PROFILE.label,
        "network": NETWORK,
        "asset": NETWORK_PROFILE.default_asset_address,
        "asset_symbol": NETWORK_PROFILE.default_asset_name,
        "pay_to": PAY_TO,
        "facilitator_url": FACILITATOR_URL,
        "buyer_engine_configured": bool(BUYER_ENGINE_URL and BUYER_ENGINE_TOKEN),
        "buyer_engine_url": BUYER_ENGINE_URL,
        "explorer_base_url": EXPLORER_BASE_URL,
        "products": [
            {
                **asdict(product),
                "pay_url": _paid_url(product),
                "public_pay_url": _paid_url(product, public=True),
            }
            for product in PRODUCTS
        ],
    }


async def _call_buyer_engine(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not BUYER_ENGINE_URL or not BUYER_ENGINE_TOKEN:
        return {
            "ok": False,
            "status_code": 503,
            "error": "Buyer Financial Policy Engine is not configured for this kiosk.",
        }

    url = f"{BUYER_ENGINE_URL.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {BUYER_ENGINE_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        try:
            data: Any = response.json()
        except Exception:
            data = {"raw": response.text}
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "data": data,
        }
    except Exception as exc:
        return {"ok": False, "status_code": 502, "error": str(exc)}


@app.post("/api/agent/inspect/{slug}")
async def mini_agent_inspect(slug: str) -> dict[str, Any]:
    try:
        product = _product_by_slug(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown product") from exc

    _record("buyer-agent", f"Mini buyer agent inspecting {product.label}", product=product.slug)
    return await _call_buyer_engine(
        "/api/v1/x402/inspect",
        {
            "url": _paid_url(product),
            "method": "GET",
        },
    )


@app.post("/api/agent/pay/{slug}")
async def mini_agent_pay(slug: str) -> dict[str, Any]:
    try:
        product = _product_by_slug(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown product") from exc

    idempotency_key = f"arc-ui-{product.slug}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    _record("buyer-agent", f"Mini buyer agent paying {product.label}", product=product.slug)
    result = await _call_buyer_engine(
        "/api/v1/pay",
        {
            "recipient": _paid_url(product),
            "idempotency_key": idempotency_key,
            "purpose": f"Arc marketplace showcase purchase: {product.label}",
            "method": "GET",
        },
    )
    data = result.get("data")
    if result.get("ok") and isinstance(data, dict) and data.get("success"):
        tx = data.get("blockchain_tx") or data.get("transaction_id")
        tx_text = str(tx)
        if tx_text and not tx_text.startswith("0x"):
            tx_text = f"0x{tx_text}"
        suffix = f" ({tx_text[:10]}...)" if tx else ""
        _record("buyer-agent", f"Mini buyer agent settled {product.label}{suffix}", product=slug)
    else:
        message = ""
        if isinstance(data, dict):
            message = str(data.get("error") or data.get("detail") or "")
        _record(
            "buyer-agent",
            f"Mini buyer agent could not pay {product.label}: {message or result.get('error')}",
            product=slug,
        )
    return result


@app.get("/api/events")
async def events() -> dict[str, Any]:
    total_revenue = sum(float(f["price"].strip("$")) for f in FULFILLMENTS)
    return {
        "events": EVENTS,
        "fulfillments": FULFILLMENTS[:20],
        "revenue_usdc": f"{total_revenue:.2f}",
        "total_settlements": len(FULFILLMENTS),
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "explorer_base_url": EXPLORER_BASE_URL,
        "pay_to": PAY_TO,
        "asset_symbol": NETWORK_PROFILE.default_asset_name,
    }


@app.get("/buy/prime-market-scan")
async def buy_prime_market_scan(request: Request) -> JSONResponse:
    product = _product_by_slug("prime-market-scan")
    buyer = _extract_buyer(request)
    result = {
        "service": "arc-marketplace-kiosk",
        "product": product.slug,
        "label": product.label,
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "result": {
            "job": "prime-count",
            "input": {"size": 70000},
            "prime_count": _prime_count(70000),
        },
        "proof": _proof_fields(product),
    }
    _fulfill(product, result, buyer_address=buyer)
    return JSONResponse(result)


@app.get("/buy/risk-oracle-brief")
async def buy_risk_oracle_brief(request: Request) -> JSONResponse:
    product = _product_by_slug("risk-oracle-brief")
    buyer = _extract_buyer(request)
    result = {
        "service": "arc-marketplace-kiosk",
        "product": product.slug,
        "label": product.label,
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "result": {
            "vendor_score": 92,
            "policy_signal": "allow-listed vendor, bounded spend, exact settlement",
            "recommended_action": "fulfill request",
        },
        "proof": _proof_fields(product),
    }
    _fulfill(product, result, buyer_address=buyer)
    return JSONResponse(result)


@app.get("/buy/settlement-receipt-kit")
async def buy_settlement_receipt_kit(request: Request) -> JSONResponse:
    product = _product_by_slug("settlement-receipt-kit")
    buyer = _extract_buyer(request)
    result = {
        "service": "arc-marketplace-kiosk",
        "product": product.slug,
        "label": product.label,
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "result": {
            "receipt_fields": [
                "seller_url",
                "payment_scheme",
                "network",
                "pay_to",
                "asset",
                "settlement_tx",
                "arcscan_url",
            ],
            "message": "Use the settlement transaction returned by the buyer CLI to open ArcScan.",
        },
        "proof": _proof_fields(product),
    }
    _fulfill(product, result, buyer_address=buyer)
    return JSONResponse(result)


def _proof_fields(product: KioskProduct) -> dict[str, Any]:
    return {
        "seller_url": _paid_url(product),
        "scheme": "exact",
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "asset": NETWORK_PROFILE.default_asset_address,
        "asset_symbol": NETWORK_PROFILE.default_asset_name,
        "pay_to": PAY_TO,
        "facilitator": FACILITATOR_URL,
        "explorer_base_url": EXPLORER_BASE_URL,
        "arcscan_note": "Append the settlement transaction hash returned by the buyer to explorer_base_url.",
    }


def _fulfill(
    product: KioskProduct, payload: dict[str, Any], *, buyer_address: str | None = None
) -> None:
    record = {
        "time": _now(),
        "slug": product.slug,
        "label": product.label,
        "price": product.price,
        "lane": product.lane,
        "accent": product.accent,
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "asset_symbol": NETWORK_PROFILE.default_asset_name,
        "pay_to": PAY_TO,
        "buyer_address": buyer_address,
        "scheme": "exact",
        "explorer_base_url": EXPLORER_BASE_URL,
    }
    FULFILLMENTS.insert(0, record)
    del FULFILLMENTS[40:]
    buyer_label = f" by {buyer_address[:10]}…" if buyer_address else ""
    _record(
        "fulfilled",
        f"{product.label} unlocked{buyer_label} after x402 exact settlement",
        product=product.slug,
    )


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OmniClaw Arc Kiosk — Agent Marketplace</title>
  <meta name="description" content="OmniClaw x402 agent marketplace on Arc Testnet. Autonomous agents pay for vendor services with on-chain settlement." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
  <style>
    /* ── Reset & Tokens ─────────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg-base: #0a0e1a;
      --bg-surface: rgba(255,255,255,0.04);
      --bg-glass: rgba(255,255,255,0.06);
      --bg-glass-hover: rgba(255,255,255,0.10);
      --border-glass: rgba(255,255,255,0.08);
      --border-glass-hover: rgba(255,255,255,0.16);
      --text-primary: #f0f2f5;
      --text-secondary: #8b92a5;
      --text-muted: #5a6175;
      --violet: #7c3aed;
      --violet-glow: rgba(124,58,237,0.3);
      --cyan: #06b6d4;
      --cyan-glow: rgba(6,182,212,0.25);
      --emerald: #10b981;
      --emerald-glow: rgba(16,185,129,0.25);
      --amber: #f59e0b;
      --amber-glow: rgba(245,158,11,0.25);
      --rose: #f43f5e;
      --rose-glow: rgba(244,63,94,0.2);
      --radius: 16px;
      --radius-sm: 10px;
      --radius-pill: 999px;
      --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
      --shadow-lg: 0 24px 48px -12px rgba(0,0,0,0.5);
      --shadow-glow: 0 0 40px -8px;
    }
    html { font-size: 15px; }
    body {
      min-height: 100vh;
      color: var(--text-primary);
      font-family: var(--font);
      background: var(--bg-base);
      overflow-x: hidden;
    }
    /* ── Animated background mesh ───────────────────────────── */
    body::before {
      content: '';
      position: fixed; inset: 0;
      background:
        radial-gradient(ellipse 80% 50% at 20% 0%, rgba(124,58,237,0.15), transparent),
        radial-gradient(ellipse 60% 40% at 80% 10%, rgba(6,182,212,0.12), transparent),
        radial-gradient(ellipse 50% 60% at 50% 100%, rgba(16,185,129,0.08), transparent);
      animation: meshMove 20s ease-in-out infinite alternate;
      z-index: 0;
      pointer-events: none;
    }
    @keyframes meshMove {
      0%   { transform: scale(1) translateY(0); }
      100% { transform: scale(1.08) translateY(-30px); }
    }
    /* ── Grid lines overlay ─────────────────────────────────── */
    body::after {
      content: '';
      position: fixed; inset: 0;
      background-image:
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 60px 60px;
      z-index: 0;
      pointer-events: none;
    }
    .app { position: relative; z-index: 1; max-width: 1280px; margin: 0 auto; padding: 32px 24px 64px; }

    /* ── Header ──────────────────────────────────────────────── */
    .header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 40px; flex-wrap: wrap; gap: 16px;
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .logo-mark {
      width: 44px; height: 44px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--violet), var(--cyan));
      display: grid; place-items: center;
      box-shadow: var(--shadow-glow) var(--violet-glow);
    }
    .logo-mark svg { width: 24px; height: 24px; fill: white; }
    .brand-text h1 {
      font-size: 1.35rem; font-weight: 800; letter-spacing: -0.03em;
      background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .brand-text span { font-size: 0.73rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.12em; font-weight: 600; }
    .header-badges { display: flex; gap: 10px; flex-wrap: wrap; }
    .badge {
      display: inline-flex; align-items: center; gap: 7px;
      padding: 6px 14px; border-radius: var(--radius-pill);
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      font-size: 0.73rem; font-weight: 600; letter-spacing: 0.04em;
      backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
      color: var(--text-secondary);
    }
    .badge .dot {
      width: 7px; height: 7px; border-radius: 50%;
      animation: pulse 2s ease-in-out infinite;
    }
    .dot.green { background: var(--emerald); box-shadow: 0 0 8px var(--emerald-glow); }
    .dot.violet { background: var(--violet); box-shadow: 0 0 8px var(--violet-glow); }
    .dot.cyan { background: var(--cyan); box-shadow: 0 0 8px var(--cyan-glow); }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

    /* ── Hero ─────────────────────────────────────────────────── */
    .hero {
      text-align: center; margin-bottom: 48px;
      padding: 48px 24px 40px;
      background: var(--bg-glass);
      border: 1px solid var(--border-glass);
      border-radius: 24px;
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      position: relative; overflow: hidden;
    }
    .hero::before {
      content: ''; position: absolute; top: -2px; left: 50%; width: 200px; height: 3px;
      transform: translateX(-50%);
      background: linear-gradient(90deg, transparent, var(--violet), var(--cyan), transparent);
      border-radius: 4px;
    }
    .hero h2 {
      font-size: clamp(2rem, 5vw, 3.2rem); font-weight: 900; letter-spacing: -0.04em;
      line-height: 1.05; margin-bottom: 14px;
      background: linear-gradient(135deg, #fff 0%, #c4b5fd 40%, #67e8f9 70%, #6ee7b7 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
      animation: gradShift 6s ease-in-out infinite alternate;
      background-size: 200% 200%;
    }
    @keyframes gradShift { 0% { background-position: 0% 50%; } 100% { background-position: 100% 50%; } }
    .hero p { color: var(--text-secondary); font-size: 1.05rem; max-width: 640px; margin: 0 auto 24px; line-height: 1.6; }

    /* ── Flow Diagram ────────────────────────────────────────── */
    .flow-steps {
      display: flex; align-items: center; justify-content: center;
      gap: 0; flex-wrap: wrap; margin: 0 auto;
    }
    .flow-step {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 16px; border-radius: var(--radius-pill);
      background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
      font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
      white-space: nowrap;
    }
    .flow-step .step-icon { font-size: 1rem; }
    .flow-arrow { color: var(--text-muted); font-size: 0.9rem; padding: 0 4px; }

    /* ── Stats Bar ────────────────────────────────────────────── */
    .stats-bar {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px; margin-bottom: 36px;
    }
    .stat-card {
      padding: 20px;
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      border-radius: var(--radius);
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      text-align: center;
      transition: all 0.3s ease;
    }
    .stat-card:hover {
      background: var(--bg-glass-hover);
      border-color: var(--border-glass-hover);
      transform: translateY(-2px);
    }
    .stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--text-muted); font-weight: 700; margin-bottom: 6px; }
    .stat-value { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }
    .stat-value.green { color: var(--emerald); }
    .stat-value.violet { color: var(--violet); }
    .stat-value.cyan { color: var(--cyan); }
    .stat-value.amber { color: var(--amber); }

    /* ── Product Cards ───────────────────────────────────────── */
    .section-title {
      font-size: 0.73rem; text-transform: uppercase; letter-spacing: 0.14em;
      color: var(--text-muted); font-weight: 800; margin-bottom: 18px;
      display: flex; align-items: center; gap: 10px;
    }
    .section-title::after {
      content: ''; flex: 1; height: 1px;
      background: linear-gradient(90deg, var(--border-glass), transparent);
    }
    .products-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px; margin-bottom: 36px;
    }
    .product-card {
      position: relative;
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      border-radius: var(--radius);
      padding: 24px;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
      overflow: hidden;
      display: flex; flex-direction: column;
    }
    .product-card::before {
      content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%;
      border-radius: 3px 0 0 3px;
    }
    .product-card.amber::before { background: linear-gradient(180deg, var(--amber), transparent); }
    .product-card.blue::before { background: linear-gradient(180deg, var(--cyan), transparent); }
    .product-card.green::before { background: linear-gradient(180deg, var(--emerald), transparent); }
    .product-card:hover {
      background: var(--bg-glass-hover);
      border-color: var(--border-glass-hover);
      transform: translateY(-4px);
      box-shadow: var(--shadow-lg);
    }
    .product-card.amber:hover { box-shadow: var(--shadow-glow) var(--amber-glow), var(--shadow-lg); }
    .product-card.blue:hover { box-shadow: var(--shadow-glow) var(--cyan-glow), var(--shadow-lg); }
    .product-card.green:hover { box-shadow: var(--shadow-glow) var(--emerald-glow), var(--shadow-lg); }
    .product-lane {
      font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.16em;
      font-weight: 800; margin-bottom: 10px;
    }
    .product-card.amber .product-lane { color: var(--amber); }
    .product-card.blue .product-lane { color: var(--cyan); }
    .product-card.green .product-lane { color: var(--emerald); }
    .product-name { font-size: 1.25rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px; }
    .product-desc { color: var(--text-secondary); font-size: 0.88rem; line-height: 1.5; margin-bottom: 18px; flex: 1; }
    .product-price {
      font-size: 2rem; font-weight: 900; letter-spacing: -0.03em; margin-bottom: 14px;
      background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .product-card.amber .product-price {
      background: linear-gradient(135deg, var(--amber), #fcd34d);
      -webkit-background-clip: text; background-clip: text;
    }
    .product-card.blue .product-price {
      background: linear-gradient(135deg, var(--cyan), #a5f3fc);
      -webkit-background-clip: text; background-clip: text;
    }
    .product-card.green .product-price {
      background: linear-gradient(135deg, var(--emerald), #6ee7b7);
      -webkit-background-clip: text; background-clip: text;
    }
    .product-url {
      font-family: var(--mono); font-size: 0.72rem; color: var(--text-muted);
      background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05);
      border-radius: var(--radius-sm); padding: 10px 12px;
      overflow-wrap: anywhere; margin-bottom: 16px;
      transition: border-color 0.2s;
    }
    .product-url:hover { border-color: rgba(255,255,255,0.12); }
    .product-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn {
      padding: 9px 18px; border-radius: var(--radius-sm);
      font-family: var(--font); font-size: 0.78rem; font-weight: 700;
      cursor: pointer; border: 1px solid; transition: all 0.25s ease;
      display: inline-flex; align-items: center; gap: 6px;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--violet), #6d28d9);
      border-color: transparent; color: white;
    }
    .btn-primary:hover {
      box-shadow: 0 0 24px var(--violet-glow);
      transform: translateY(-1px);
    }
    .btn-ghost {
      background: transparent;
      border-color: var(--border-glass-hover); color: var(--text-secondary);
    }
    .btn-ghost:hover { background: var(--bg-glass-hover); color: var(--text-primary); }
    .btn-icon { font-size: 0.9rem; }

    /* ── Mini Buyer Agent ───────────────────────────────────── */
    .agent-workbench {
      display: grid; grid-template-columns: 0.95fr 1.25fr;
      gap: 18px; margin-bottom: 36px;
    }
    .agent-card {
      position: relative;
      min-height: 100%;
      background:
        linear-gradient(135deg, rgba(124,58,237,0.14), rgba(6,182,212,0.06)),
        var(--bg-glass);
    }
    .agent-card::before {
      content: ''; position: absolute; inset: 0;
      background:
        radial-gradient(circle at 24px 24px, rgba(255,255,255,0.10) 0 2px, transparent 3px),
        radial-gradient(circle at 88% 18%, rgba(6,182,212,0.22), transparent 120px);
      pointer-events: none;
    }
    .agent-face {
      width: 86px; height: 86px; border-radius: 26px;
      background: linear-gradient(145deg, var(--violet), var(--cyan));
      display: grid; place-items: center;
      font-size: 2.1rem; margin-bottom: 18px;
      box-shadow: 0 0 42px var(--violet-glow);
      position: relative; z-index: 1;
    }
    .agent-copy { position: relative; z-index: 1; }
    .agent-copy h3 { font-size: 1.3rem; font-weight: 900; letter-spacing: -0.03em; margin-bottom: 8px; }
    .agent-copy p { color: var(--text-secondary); line-height: 1.55; font-size: 0.9rem; margin-bottom: 18px; }
    .agent-controls { display: grid; gap: 12px; position: relative; z-index: 1; }
    .agent-select {
      width: 100%;
      padding: 12px 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-glass-hover);
      background: rgba(0,0,0,0.36);
      color: var(--text-primary);
      font: 700 0.86rem var(--font);
      outline: none;
    }
    .agent-buttons { display: flex; gap: 10px; flex-wrap: wrap; }
    .agent-output {
      background: rgba(0,0,0,0.38);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: var(--radius);
      padding: 16px;
      min-height: 276px;
      font-family: var(--mono);
      font-size: 0.76rem;
      line-height: 1.65;
      color: var(--text-secondary);
      overflow: auto;
    }
    .agent-output .ok { color: var(--emerald); }
    .agent-output .fail { color: var(--rose); }
    .agent-output .muted { color: var(--text-muted); }
    .agent-output a { color: var(--cyan); text-decoration: none; }
    .agent-output a:hover { text-decoration: underline; }

    /* ── Bottom Grid: Terminal + Settlement + Feed ────────────── */
    .bottom-grid {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 18px; margin-bottom: 36px;
    }
    .panel {
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      border-radius: var(--radius);
      padding: 24px;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      overflow: hidden;
    }
    .panel-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 18px;
    }
    .panel-title {
      display: flex; align-items: center; gap: 10px;
      font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-primary);
    }
    .panel-title .pill-icon {
      width: 8px; height: 8px; border-radius: 50%;
    }

    /* Terminal */
    .terminal {
      background: rgba(0,0,0,0.4); border-color: rgba(255,255,255,0.06);
    }
    .terminal-content {
      background: rgba(0,0,0,0.3);
      border-radius: var(--radius-sm);
      padding: 16px;
      font-family: var(--mono); font-size: 0.78rem;
      line-height: 1.7; color: var(--text-secondary);
      max-height: 300px; overflow-y: auto;
    }
    .terminal-content .cmd { color: var(--emerald); }
    .terminal-content .comment { color: var(--text-muted); }
    .terminal-content .url { color: var(--cyan); }
    .terminal-content .key { color: var(--amber); }

    /* Settlement proof */
    .proof-grid { display: grid; gap: 12px; }
    .proof-row {
      display: grid; grid-template-columns: 110px 1fr; gap: 8px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      align-items: start;
    }
    .proof-row:last-child { border-bottom: none; }
    .proof-key {
      font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.12em;
      color: var(--text-muted); font-weight: 800; padding-top: 2px;
    }
    .proof-val {
      font-family: var(--mono); font-size: 0.76rem; color: var(--text-secondary);
      overflow-wrap: anywhere;
    }

    /* ── Live Feed (full width) ──────────────────────────────── */
    .feed-section { margin-bottom: 36px; }
    .feed-container {
      max-height: 400px; overflow-y: auto;
      display: grid; gap: 10px;
      scrollbar-width: thin;
      scrollbar-color: rgba(255,255,255,0.08) transparent;
    }
    .feed-item {
      display: grid; grid-template-columns: auto 1fr auto;
      gap: 14px; align-items: center;
      padding: 14px 18px;
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      border-radius: var(--radius-sm);
      animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      transition: all 0.2s ease;
    }
    .feed-item:hover {
      background: var(--bg-glass-hover);
      border-color: var(--border-glass-hover);
    }
    @keyframes slideIn {
      from { opacity: 0; transform: translateX(20px); }
      to { opacity: 1; transform: translateX(0); }
    }
    .feed-icon {
      width: 36px; height: 36px; border-radius: 10px;
      display: grid; place-items: center; font-size: 1rem;
    }
    .feed-icon.fulfilled { background: rgba(16,185,129,0.15); color: var(--emerald); }
    .feed-icon.kiosk { background: rgba(124,58,237,0.15); color: var(--violet); }
    .feed-icon.default { background: rgba(139,146,165,0.15); color: var(--text-secondary); }
    .feed-body {}
    .feed-msg { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
    .feed-meta { font-size: 0.7rem; color: var(--text-muted); margin-top: 3px; }
    .feed-tag {
      font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em;
      font-weight: 800; padding: 4px 10px; border-radius: var(--radius-pill);
    }
    .feed-tag.fulfilled { background: rgba(16,185,129,0.12); color: var(--emerald); }
    .feed-tag.kiosk { background: rgba(124,58,237,0.12); color: var(--violet); }
    .feed-tag.default { background: rgba(139,146,165,0.1); color: var(--text-muted); }
    .feed-empty {
      text-align: center; padding: 40px; color: var(--text-muted);
      font-size: 0.88rem;
    }
    .feed-empty .empty-icon { font-size: 2rem; margin-bottom: 10px; opacity: 0.4; }

    /* ── Fulfillment Detail Cards ────────────────────────────── */
    .fulfillment-section { margin-bottom: 36px; }
    .fulfillment-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 14px;
    }
    .fulfillment-card {
      background: var(--bg-glass); border: 1px solid var(--border-glass);
      border-radius: var(--radius); padding: 20px;
      position: relative; overflow: hidden;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      animation: slideIn 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .fulfillment-card::before {
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, var(--emerald), var(--cyan));
    }
    .fulfillment-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 14px;
    }
    .fulfillment-product { font-weight: 800; font-size: 0.95rem; }
    .fulfillment-price {
      font-family: var(--mono); font-weight: 700; font-size: 0.88rem;
      color: var(--emerald);
    }
    .fulfillment-details { display: grid; gap: 6px; }
    .fulfillment-row {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.73rem;
    }
    .fulfillment-row .fk { color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
    .fulfillment-row .fv { font-family: var(--mono); color: var(--text-secondary); font-size: 0.7rem; }

    /* ── Toast ────────────────────────────────────────────────── */
    .toast-container {
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
      z-index: 100;
    }
    .toast {
      padding: 10px 20px; border-radius: var(--radius-pill);
      background: var(--violet); color: white;
      font-size: 0.82rem; font-weight: 700;
      box-shadow: 0 0 30px var(--violet-glow);
      opacity: 0; transform: translateY(10px);
      transition: all 0.3s ease;
      pointer-events: none;
    }
    .toast.visible { opacity: 1; transform: translateY(0); pointer-events: auto; }

    /* ── Footer ───────────────────────────────────────────────── */
    .footer {
      text-align: center; padding: 24px 0 8px;
      border-top: 1px solid rgba(255,255,255,0.04);
      color: var(--text-muted); font-size: 0.72rem;
    }
    .footer a { color: var(--violet); text-decoration: none; }
    .footer a:hover { color: var(--cyan); }

    /* ── Responsive ──────────────────────────────────────────── */
    @media (max-width: 900px) {
      .bottom-grid { grid-template-columns: 1fr; }
      .agent-workbench { grid-template-columns: 1fr; }
      .fulfillment-grid { grid-template-columns: 1fr; }
      .flow-steps { gap: 4px; }
      .flow-arrow { display: none; }
    }
    @media (max-width: 600px) {
      .header { flex-direction: column; align-items: flex-start; }
      .products-grid { grid-template-columns: 1fr; }
      .stats-bar { grid-template-columns: repeat(2, 1fr); }
    }

    /* ── Scrollbar ────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
  </style>
</head>
<body>
  <main class="app">
    <!-- Header -->
    <header class="header" id="header">
      <div class="brand">
        <div class="logo-mark">
          <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        </div>
        <div class="brand-text">
          <h1>OmniClaw Arc Kiosk</h1>
          <span>Agent Marketplace</span>
        </div>
      </div>
      <div class="header-badges" id="badges"></div>
    </header>

    <!-- Hero -->
    <section class="hero">
      <h2>Vendor services<br>for autonomous agents.</h2>
      <p>A buyer agent selects a service, OmniClaw enforces policy constraints, x402 settles on-chain, and the vendor unlocks the result. Every step is verifiable.</p>
      <div class="flow-steps">
        <div class="flow-step"><span class="step-icon">🛒</span> Select Service</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step"><span class="step-icon">🛡️</span> Policy Check</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step"><span class="step-icon">💳</span> x402 Payment</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step"><span class="step-icon">⛓️</span> On-Chain Settlement</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step"><span class="step-icon">✅</span> Fulfill & Verify</div>
      </div>
    </section>

    <!-- Stats -->
    <section class="stats-bar" id="stats">
      <div class="stat-card"><div class="stat-label">Total Revenue</div><div class="stat-value green" id="stat-revenue">$0.00</div></div>
      <div class="stat-card"><div class="stat-label">Settlements</div><div class="stat-value violet" id="stat-settlements">0</div></div>
      <div class="stat-card"><div class="stat-label">Network</div><div class="stat-value cyan" id="stat-network">—</div></div>
      <div class="stat-card"><div class="stat-label">Asset</div><div class="stat-value amber" id="stat-asset">—</div></div>
    </section>

    <!-- Products -->
    <div class="section-title">Paid Vendor Services</div>
    <section class="products-grid" id="products"></section>

    <!-- Mini Buyer Agent -->
    <div class="section-title">Built-In Buyer Agent</div>
    <section class="agent-workbench">
      <div class="panel agent-card">
        <div class="agent-face">🤖</div>
        <div class="agent-copy">
          <h3>Mini buyer agent</h3>
          <p>Run the whole Arc showcase from this page. The browser asks the kiosk backend, the backend calls the buyer Financial Policy Engine, policy is enforced, and settlement still happens through x402 exact on Arc.</p>
        </div>
        <div class="agent-controls">
          <select class="agent-select" id="agent-product"></select>
          <div class="agent-buttons">
            <button class="btn btn-ghost" onclick="agentInspect()"><span class="btn-icon">🔎</span> Inspect</button>
            <button class="btn btn-primary" onclick="agentPay()"><span class="btn-icon">⚡</span> Pay & Unlock</button>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title"><span class="pill-icon" style="background:var(--violet)"></span> Buyer Agent Console</div>
        </div>
        <div class="agent-output" id="agent-output">
          <span class="muted">Select a product, inspect the x402 requirement, then pay. No OpenClaw prompt is required for this browser demo.</span>
        </div>
      </div>
    </section>

    <!-- Bottom Grid: Terminal + Proof -->
    <div class="bottom-grid">
      <div class="panel terminal">
        <div class="panel-header">
          <div class="panel-title"><span class="pill-icon" style="background:var(--emerald)"></span> Agent Commands</div>
        </div>
        <div class="terminal-content" id="terminal"></div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title"><span class="pill-icon" style="background:var(--cyan)"></span> Settlement Proof Surface</div>
        </div>
        <div class="proof-grid" id="proof"></div>
      </div>
    </div>

    <!-- Fulfillments -->
    <div class="fulfillment-section" id="fulfillment-section" style="display:none">
      <div class="section-title">Recent Settlements</div>
      <div class="fulfillment-grid" id="fulfillments"></div>
    </div>

    <!-- Live Event Feed -->
    <div class="feed-section">
      <div class="section-title">Live Event Feed</div>
      <div class="panel" style="padding:16px">
        <div class="feed-container" id="feed"></div>
      </div>
    </div>

    <footer class="footer">
      OmniClaw — Programmable agent economy infrastructure.
      Settlement verified on <a href="" target="_blank" rel="noopener" id="footer-explorer">ArcScan</a>.
    </footer>
  </main>

  <div class="toast-container"><div class="toast" id="toast">Copied</div></div>

<script>
const state = { catalog: null, events: [], fulfillments: [] };
const esc = v => String(v).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const truncAddr = a => a ? a.slice(0,6) + '···' + a.slice(-4) : '—';

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('visible');
  setTimeout(() => el.classList.remove('visible'), 1600);
}

async function fetchJSON(path, options = undefined) {
  try { const r = await fetch(path, options); return await r.json(); } catch { return null; }
}

function renderBadges(catalog) {
  document.getElementById('badges').innerHTML = `
    <span class="badge"><span class="dot green"></span> Online</span>
    <span class="badge"><span class="dot violet"></span> ${esc(catalog.network_profile)}</span>
    <span class="badge"><span class="dot cyan"></span> ${esc(catalog.network)}</span>
    <span class="badge">${esc(catalog.asset_symbol)}</span>
  `;
}

function renderProducts(catalog) {
  const container = document.getElementById('products');
  container.innerHTML = catalog.products.map((p, i) => `
    <article class="product-card ${esc(p.accent)}" id="product-${i}">
      <div class="product-lane">${esc(p.lane)} lane</div>
      <h3 class="product-name">${esc(p.label)}</h3>
      <div class="product-desc">${esc(p.description)}</div>
      <div class="product-price">${esc(p.price)}</div>
      <div class="product-url">${esc(p.pay_url)}</div>
      <div class="product-actions">
        <button class="btn btn-primary" onclick="selectAgentProduct(${i})">
          <span class="btn-icon">🤖</span> Use Mini Agent
        </button>
        <button class="btn btn-primary" onclick="copyPrompt(${i})">
          <span class="btn-icon">⚡</span> Copy Agent Prompt
        </button>
        <button class="btn btn-ghost" onclick="copyUrl(${i})">
          <span class="btn-icon">🔗</span> Copy URL
        </button>
      </div>
    </article>
  `).join('');
}

function renderTerminal(catalog) {
  const p = catalog.products[0];
  document.getElementById('terminal').innerHTML = `
<span class="comment"># Inspect the paid endpoint</span>
<span class="cmd">$</span> omniclaw-cli inspect-x402 \\
    <span class="key">--recipient</span> <span class="url">"${esc(p.pay_url)}"</span>

<span class="comment"># Execute payment (creates on-chain settlement)</span>
<span class="cmd">$</span> omniclaw-cli pay \\
    <span class="key">--recipient</span> <span class="url">"${esc(p.pay_url)}"</span> \\
    <span class="key">--idempotency-key</span> "arc-kiosk-$(date +%s)"

<span class="comment"># Or use the OpenClaw natural language prompt</span>
<span class="cmd">></span> pay for this url: <span class="url">${esc(p.pay_url)}</span>
  `.trim();
}

function explorerRoot(baseUrl) {
  return baseUrl ? baseUrl.replace(/\\/tx\\/?$/, '/') : '#';
}
function explorerAddress(baseUrl, addr) {
  return baseUrl ? explorerRoot(baseUrl) + 'address/' + addr : '#';
}

function renderProof(catalog) {
  const root = explorerRoot(catalog.explorer_base_url);
  const addrUrl = explorerAddress(catalog.explorer_base_url, catalog.pay_to);
  document.getElementById('proof').innerHTML = `
    <div class="proof-row"><span class="proof-key">Network</span><span class="proof-val">${esc(catalog.network_profile)} · ${esc(catalog.network)}</span></div>
    <div class="proof-row"><span class="proof-key">Seller PayTo</span><span class="proof-val"><a href="${esc(addrUrl)}" target="_blank" rel="noopener" style="color:var(--cyan);text-decoration:none">${esc(catalog.pay_to)}</a></span></div>
    <div class="proof-row"><span class="proof-key">Asset</span><span class="proof-val">${esc(catalog.asset_symbol)} · ${esc(catalog.asset)}</span></div>
    <div class="proof-row"><span class="proof-key">Facilitator</span><span class="proof-val">${esc(catalog.facilitator_url)}</span></div>
    <div class="proof-row"><span class="proof-key">Explorer</span><span class="proof-val"><a href="${esc(root)}" target="_blank" rel="noopener" style="color:var(--cyan);text-decoration:none">${esc(root)}</a></span></div>
    <div class="proof-row"><span class="proof-key">Scheme</span><span class="proof-val">exact (x402 EVM)</span></div>
  `;
  const footerExplorer = document.getElementById('footer-explorer');
  footerExplorer.href = root;
}

function renderStats(eventsData) {
  document.getElementById('stat-revenue').textContent = '$' + (eventsData.revenue_usdc || '0.00');
  document.getElementById('stat-settlements').textContent = eventsData.total_settlements || 0;
  document.getElementById('stat-network').textContent = eventsData.network_profile || '—';
  document.getElementById('stat-asset').textContent = eventsData.asset_symbol || '—';
}

function renderFeed(events) {
  const container = document.getElementById('feed');
  if (!events || events.length === 0) {
    container.innerHTML = `<div class="feed-empty"><div class="empty-icon">📡</div>Waiting for agent activity…<br><small>Events will appear here when a buyer agent pays for a service.</small></div>`;
    return;
  }
  const iconClass = stage => stage === 'fulfilled' ? 'fulfilled' : stage === 'kiosk' ? 'kiosk' : 'default';
  const iconEmoji = stage => stage === 'fulfilled' ? '✅' : stage === 'kiosk' ? '🏪' : stage === 'buyer-agent' ? '🤖' : '📋';
  container.innerHTML = events.map(e => `
    <div class="feed-item">
      <div class="feed-icon ${iconClass(e.stage)}">${iconEmoji(e.stage)}</div>
      <div class="feed-body">
        <div class="feed-msg">${esc(e.message)}</div>
        <div class="feed-meta">${esc(e.time)}${e.product ? ' · ' + esc(e.product) : ''}</div>
      </div>
      <span class="feed-tag ${iconClass(e.stage)}">${esc(e.stage)}</span>
    </div>
  `).join('');
}

function renderFulfillments(fulfillments) {
  const section = document.getElementById('fulfillment-section');
  const container = document.getElementById('fulfillments');
  if (!fulfillments || fulfillments.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  container.innerHTML = fulfillments.map(f => `
    <div class="fulfillment-card">
      <div class="fulfillment-header">
        <span class="fulfillment-product">${esc(f.label)}</span>
        <span class="fulfillment-price">${esc(f.price)}</span>
      </div>
      <div class="fulfillment-details">
        <div class="fulfillment-row"><span class="fk">Time</span><span class="fv">${esc(f.time)}</span></div>
        <div class="fulfillment-row"><span class="fk">Buyer</span><span class="fv">${f.buyer_address ? '<a href="'+esc(explorerAddress(f.explorer_base_url, f.buyer_address))+'" target="_blank" rel="noopener" style="color:var(--violet);text-decoration:none">'+esc(f.buyer_address)+'</a>' : '<span style="color:var(--text-muted)">Unknown</span>'}</span></div>
        <div class="fulfillment-row"><span class="fk">Seller</span><span class="fv"><a href="${esc(explorerAddress(f.explorer_base_url, f.pay_to))}" target="_blank" rel="noopener" style="color:var(--emerald);text-decoration:none">${esc(f.pay_to)}</a></span></div>
        <div class="fulfillment-row"><span class="fk">Network</span><span class="fv">${esc(f.network_profile || f.network)}</span></div>
        <div class="fulfillment-row"><span class="fk">Scheme</span><span class="fv">${esc(f.scheme || 'exact')}</span></div>
        <div class="fulfillment-row"><span class="fk">Asset</span><span class="fv">${esc(f.asset_symbol || 'USDC')}</span></div>
        <div class="fulfillment-row"><span class="fk">Lane</span><span class="fv">${esc(f.lane || '—')}</span></div>
        <div class="fulfillment-row"><span class="fk">Explorer</span><span class="fv"><a href="${esc(explorerAddress(f.explorer_base_url, f.pay_to))}" target="_blank" rel="noopener" style="color:var(--cyan);text-decoration:none;font-family:var(--mono);font-size:0.7rem">View on ArcScan ↗</a></span></div>
      </div>
    </div>
  `).join('');
}

function copyPrompt(index) {
  const p = state.catalog.products[index];
  const prompt = 'pay for this url: ' + p.pay_url;
  navigator.clipboard.writeText(prompt);
  toast('⚡ Agent prompt copied');
}
function copyUrl(index) {
  navigator.clipboard.writeText(state.catalog.products[index].pay_url);
  toast('🔗 Paid URL copied');
}

function renderMiniAgent(catalog) {
  const select = document.getElementById('agent-product');
  select.innerHTML = catalog.products.map((p, i) => (
    `<option value="${i}">${esc(p.label)} · ${esc(p.price)}</option>`
  )).join('');
  const output = document.getElementById('agent-output');
  if (!catalog.buyer_engine_configured) {
    output.innerHTML = `<span class="fail">Buyer engine is not connected.</span>
<br><br><span class="muted">Start with scripts/start_arc_marketplace_showcase_docker.sh so the kiosk receives ARC_MARKETPLACE_BUYER_ENGINE_URL and ARC_MARKETPLACE_BUYER_TOKEN.</span>`;
    return;
  }
  output.innerHTML = `<span class="ok">Buyer engine connected.</span>
<br><span class="muted">Engine:</span> ${esc(catalog.buyer_engine_url)}
<br><span class="muted">Flow:</span> browser → kiosk proxy → Financial Policy Engine → x402 exact → Arc settlement
<br><br><span class="muted">Select a product and run Inspect or Pay & Unlock.</span>`;
}

function currentAgentProduct() {
  const index = Number(document.getElementById('agent-product').value || 0);
  return state.catalog.products[index];
}

function selectAgentProduct(index) {
  const select = document.getElementById('agent-product');
  select.value = String(index);
  const p = state.catalog.products[index];
  document.getElementById('agent-output').innerHTML = `<span class="ok">Loaded product.</span>
<br><span class="muted">Product:</span> ${esc(p.label)}
<br><span class="muted">Price:</span> ${esc(p.price)}
<br><span class="muted">Paid URL:</span> ${esc(p.pay_url)}
<br><br><span class="muted">Run Inspect first, then Pay & Unlock.</span>`;
  document.getElementById('agent-output').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function txUrl(tx) {
  if (!tx || !state.catalog?.explorer_base_url) return null;
  const normalized = String(tx).startsWith('0x') ? String(tx) : '0x' + String(tx);
  return state.catalog.explorer_base_url + normalized;
}

function prettyJSON(value) {
  return esc(JSON.stringify(value, null, 2));
}

async function agentInspect() {
  const p = currentAgentProduct();
  const output = document.getElementById('agent-output');
  output.innerHTML = `<span class="muted">Mini buyer agent inspecting ${esc(p.label)}...</span>`;
  const result = await fetchJSON('/api/agent/inspect/' + encodeURIComponent(p.slug), { method: 'POST' });
  if (!result) {
    output.innerHTML = `<span class="fail">Inspection failed: no response.</span>`;
    return;
  }
  const data = result.data || {};
  const statusClass = result.ok && data.buyer_ready ? 'ok' : 'fail';
  output.innerHTML = `<span class="${statusClass}">Inspect ${result.ok && data.buyer_ready ? 'ready' : 'not ready'}.</span>
<br><span class="muted">Product:</span> ${esc(p.label)}
<br><span class="muted">Route:</span> ${esc(data.selected_route || data.router_detected_route || 'unknown')}
<br><span class="muted">Source:</span> ${esc(data.payment_source || 'unknown')}
<br><span class="muted">Amount:</span> ${esc(data.selected_amount_usdc || p.price)}
<br><span class="muted">Network:</span> ${esc(data.selected_network || state.catalog.network)}
<br><span class="muted">Buyer:</span> ${esc(data.buyer_address || 'unknown')}
<br><span class="muted">Reason:</span> ${esc(data.reason || result.error || 'OK')}
<br><br><span class="muted">Raw inspection:</span>
<pre>${prettyJSON(data)}</pre>`;
  await refreshEvents();
}

async function agentPay() {
  const p = currentAgentProduct();
  const output = document.getElementById('agent-output');
  output.innerHTML = `<span class="muted">Mini buyer agent paying ${esc(p.label)}...</span>
<br><span class="muted">Policy engine is checking recipient, limits, route, signature, and settlement.</span>`;
  const result = await fetchJSON('/api/agent/pay/' + encodeURIComponent(p.slug), { method: 'POST' });
  if (!result) {
    output.innerHTML = `<span class="fail">Payment failed: no response.</span>`;
    return;
  }
  const data = result.data || {};
  let tx = data.blockchain_tx || data.transaction_id;
  if (tx && !String(tx).startsWith('0x')) tx = '0x' + String(tx);
  const link = txUrl(tx);
  const success = Boolean(result.ok && data.success);
  output.innerHTML = `<span class="${success ? 'ok' : 'fail'}">Payment ${success ? 'settled' : 'failed'}.</span>
<br><span class="muted">Product:</span> ${esc(p.label)}
<br><span class="muted">Amount:</span> ${esc(data.amount || p.price)}
<br><span class="muted">Status:</span> ${esc(data.status || 'unknown')}
<br><span class="muted">Method:</span> ${esc(data.method || 'x402')}
<br><span class="muted">Settlement:</span> ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${esc(tx)}</a>` : esc(tx || 'none')}
<br><span class="muted">Error:</span> ${esc(data.error || result.error || 'none')}
<br><br><span class="muted">Paid response:</span>
<pre>${prettyJSON(data.response_data || data)}</pre>`;
  await refreshEvents();
}

async function boot() {
  const catalog = await fetchJSON('/api/catalog');
  if (!catalog) return;
  state.catalog = catalog;
  renderBadges(catalog);
  renderProducts(catalog);
  renderMiniAgent(catalog);
  renderTerminal(catalog);
  renderProof(catalog);
  await refreshEvents();
}

async function refreshEvents() {
  const data = await fetchJSON('/api/events');
  if (!data) return;
  renderStats(data);
  renderFeed(data.events);
  renderFulfillments(data.fulfillments);
}

boot();
setInterval(refreshEvents, 2500);
</script>
</body>
</html>
"""
