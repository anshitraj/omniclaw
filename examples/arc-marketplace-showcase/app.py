from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isqrt
from typing import Any

from eth_account import Account
from fastapi import FastAPI
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


@app.get("/api/events")
async def events() -> dict[str, Any]:
    return {
        "events": EVENTS,
        "fulfillments": FULFILLMENTS[:20],
        "revenue_usdc": f"{sum(float(p.price.strip('$')) for p in PRODUCTS if any(f['slug'] == p.slug for f in FULFILLMENTS)):.2f}",
    }


@app.get("/buy/prime-market-scan")
async def buy_prime_market_scan() -> JSONResponse:
    product = _product_by_slug("prime-market-scan")
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
    _fulfill(product, result)
    return JSONResponse(result)


@app.get("/buy/risk-oracle-brief")
async def buy_risk_oracle_brief() -> JSONResponse:
    product = _product_by_slug("risk-oracle-brief")
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
    _fulfill(product, result)
    return JSONResponse(result)


@app.get("/buy/settlement-receipt-kit")
async def buy_settlement_receipt_kit() -> JSONResponse:
    product = _product_by_slug("settlement-receipt-kit")
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
    _fulfill(product, result)
    return JSONResponse(result)


def _proof_fields(product: KioskProduct) -> dict[str, Any]:
    return {
        "seller_url": _paid_url(product),
        "scheme": "exact",
        "network": NETWORK,
        "network_profile": NETWORK_PROFILE.label,
        "asset": NETWORK_PROFILE.default_asset_address,
        "pay_to": PAY_TO,
        "facilitator": FACILITATOR_URL,
        "explorer_base_url": EXPLORER_BASE_URL,
        "arcscan_note": "Append the settlement transaction hash returned by the buyer to explorer_base_url.",
    }


def _fulfill(product: KioskProduct, payload: dict[str, Any]) -> None:
    record = {
        "time": _now(),
        "slug": product.slug,
        "label": product.label,
        "price": product.price,
        "network": NETWORK,
        "pay_to": PAY_TO,
    }
    FULFILLMENTS.insert(0, record)
    del FULFILLMENTS[40:]
    _record(
        "fulfilled", f"{product.label} unlocked after x402 exact settlement", product=product.slug
    )


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OmniClaw Arc Kiosk</title>
  <style>
    :root {
      --ink: #14221d;
      --muted: #60726b;
      --cream: #f5eddc;
      --paper: #fff9eb;
      --line: #d9c9a7;
      --amber: #d97904;
      --blue: #1f6f8b;
      --green: #27805b;
      --shadow: rgba(38, 30, 12, .18);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 14% 12%, rgba(217,121,4,.22), transparent 28%),
        radial-gradient(circle at 78% 0%, rgba(31,111,139,.20), transparent 25%),
        linear-gradient(135deg, #fbf1dc 0%, #efe0bd 48%, #f7edd8 100%);
      font-family: "Avenir Next", "Gill Sans", "Trebuchet MS", sans-serif;
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 30px 18px 52px; }
    .hero {
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 18px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .signboard, .proof, .card, .terminal {
      border: 2px solid var(--ink);
      box-shadow: 8px 8px 0 var(--shadow);
      background: var(--paper);
      border-radius: 24px;
    }
    .signboard { padding: 28px; position: relative; overflow: hidden; }
    .signboard:after {
      content: "";
      position: absolute;
      width: 260px;
      height: 260px;
      right: -80px;
      top: -80px;
      border-radius: 50%;
      background: repeating-linear-gradient(45deg, rgba(217,121,4,.18), rgba(217,121,4,.18) 10px, rgba(31,111,139,.16) 10px, rgba(31,111,139,.16) 20px);
    }
    .eyebrow { font-size: 13px; text-transform: uppercase; letter-spacing: .16em; color: var(--amber); font-weight: 800; }
    h1 { margin: 10px 0 10px; font-size: clamp(38px, 7vw, 76px); line-height: .9; letter-spacing: -.05em; max-width: 780px; }
    .sub { color: var(--muted); font-size: 18px; max-width: 680px; position: relative; z-index: 1; }
    .proof { padding: 22px; display: grid; gap: 12px; }
    .pill { display: inline-flex; align-items: center; gap: 8px; width: fit-content; padding: 7px 10px; border-radius: 999px; border: 2px solid var(--ink); background: #fff3cc; font-weight: 800; font-size: 12px; text-transform: uppercase; letter-spacing: .1em; }
    .kv { display: grid; gap: 4px; padding: 10px 0; border-bottom: 1px dashed var(--line); }
    .k { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .12em; font-weight: 800; }
    .v { font-family: "SFMono-Regular", Consolas, monospace; font-size: 13px; overflow-wrap: anywhere; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 18px 0; }
    .card { padding: 18px; display: flex; flex-direction: column; min-height: 320px; }
    .card.amber { background: #fff3d5; }
    .card.blue { background: #eaf8ff; }
    .card.green { background: #eaf8ed; }
    .lane { font-size: 12px; text-transform: uppercase; letter-spacing: .14em; color: var(--muted); font-weight: 900; }
    .card h2 { margin: 10px 0 8px; font-size: 28px; line-height: 1; letter-spacing: -.03em; }
    .desc { color: var(--muted); min-height: 58px; }
    .price { margin: 14px 0; font-size: 34px; font-weight: 900; }
    .url { padding: 12px; border-radius: 14px; background: rgba(255,255,255,.62); border: 1px solid var(--line); font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }
    .actions { margin-top: auto; display: flex; gap: 8px; flex-wrap: wrap; padding-top: 14px; }
    button { border: 2px solid var(--ink); color: var(--paper); background: var(--ink); border-radius: 14px; padding: 10px 12px; font-weight: 900; cursor: pointer; }
    button.secondary { background: transparent; color: var(--ink); }
    .bottom { display: grid; grid-template-columns: .9fr 1.1fr; gap: 16px; }
    .terminal { padding: 18px; background: #13221c; color: #dff7dd; }
    .terminal h2 { margin: 0 0 12px; color: #fff9eb; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }
    .events { display: grid; gap: 10px; max-height: 300px; overflow: auto; }
    .event { padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,.64); border: 1px solid var(--line); }
    .event strong { display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .1em; }
    .toast { position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); background: var(--ink); color: var(--paper); border-radius: 999px; padding: 10px 14px; display: none; }
    @media (max-width: 900px) {
      .hero, .grid, .bottom { grid-template-columns: 1fr; }
      .signboard:after { opacity: .45; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="signboard">
        <div class="eyebrow">Arc Service Kiosk</div>
        <h1>Vendor goods for agent buyers.</h1>
        <p class="sub">A buyer agent selects a service, OmniClaw enforces policy, x402 exact settles on Arc Testnet, and the vendor unlocks the result.</p>
      </div>
      <aside class="proof" id="proof"></aside>
    </section>
    <section class="grid" id="products"></section>
    <section class="bottom">
      <div class="terminal">
        <h2>OpenClaw prompt</h2>
        <pre id="prompt"></pre>
      </div>
      <div class="proof">
        <div class="pill">Live Fulfillment Feed</div>
        <div class="events" id="events"></div>
      </div>
    </section>
  </main>
  <div class="toast" id="toast">Copied</div>
<script>
const state = { products: [] };
function esc(value) {
  return String(value).replace(/[&<>]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[char]));
}
function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 1200);
}
async function json(path) {
  const res = await fetch(path);
  return await res.json();
}
async function boot() {
  const catalog = await json('/api/catalog');
  state.products = catalog.products;
  document.getElementById('proof').innerHTML = `
    <div class="pill">Settlement Proof Surface</div>
    <div class="kv"><div class="k">Network</div><div class="v">${esc(catalog.network_profile)} · ${esc(catalog.network)}</div></div>
    <div class="kv"><div class="k">Seller PayTo</div><div class="v">${esc(catalog.pay_to)}</div></div>
    <div class="kv"><div class="k">Asset</div><div class="v">${esc(catalog.asset_symbol)} · ${esc(catalog.asset)}</div></div>
    <div class="kv"><div class="k">Facilitator</div><div class="v">${esc(catalog.facilitator_url)}</div></div>
    <div class="kv"><div class="k">ArcScan</div><div class="v">${esc(catalog.explorer_base_url)}&lt;tx&gt;</div></div>`;
  document.getElementById('products').innerHTML = catalog.products.map((product, index) => `
    <article class="card ${esc(product.accent)}">
      <div class="lane">${esc(product.lane)} lane</div>
      <h2>${esc(product.label)}</h2>
      <div class="desc">${esc(product.description)}</div>
      <div class="price">${esc(product.price)}</div>
      <div class="url">${esc(product.pay_url)}</div>
      <div class="actions">
        <button onclick="copyPrompt(${index})">Copy agent prompt</button>
        <button class="secondary" onclick="copyUrl(${index})">Copy URL</button>
      </div>
    </article>`).join('');
  document.getElementById('prompt').textContent = `pay for this url: ${catalog.products[0].pay_url}`;
  await refreshEvents();
}
function copyPrompt(index) {
  const prompt = `pay for this url: ${state.products[index].pay_url}`;
  navigator.clipboard.writeText(prompt);
  document.getElementById('prompt').textContent = prompt;
  toast('Agent prompt copied');
}
function copyUrl(index) {
  navigator.clipboard.writeText(state.products[index].pay_url);
  toast('Paid URL copied');
}
async function refreshEvents() {
  const data = await json('/api/events');
  document.getElementById('events').innerHTML = data.events.length
    ? data.events.map(event => `<div class="event"><strong>${esc(event.stage)} · ${esc(event.time)}</strong>${esc(event.message)}</div>`).join('')
    : '<div class="event"><strong>waiting</strong>No paid fulfillment yet.</div>';
}
boot();
setInterval(refreshEvents, 2000);
</script>
</body>
</html>
"""
