from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from math import isqrt
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

SELLER_SERVER_URL = os.environ.get("SELLER_OMNICLAW_SERVER_URL", "http://localhost:9091")
SELLER_TOKEN = os.environ.get("SELLER_OMNICLAW_TOKEN", "seller-agent-token")
BUYER_SERVER_URL = os.environ.get("BUYER_OMNICLAW_SERVER_URL", "http://localhost:9090")
BUYER_TOKEN = os.environ.get("BUYER_OMNICLAW_TOKEN", "payment-agent-token")
APP_PORT = int(os.environ.get("BUSINESS_COMPUTE_PORT", "8010"))
NETWORK_NAME = os.environ.get("BUSINESS_COMPUTE_NETWORK", "ARC-TESTNET")
EXPLORER_BASE_URL = os.environ.get(
    "BUSINESS_COMPUTE_EXPLORER_BASE_URL", "https://testnet.arcscan.app"
)
ENABLE_LOCAL_BUYER = os.environ.get("BUSINESS_COMPUTE_ENABLE_LOCAL_BUYER", "false").lower() in {
    "1",
    "true",
    "yes",
}
PAPERS_DIR = Path(__file__).resolve().parent / "papers"
DOWNLOAD_SIGNING_SECRET = os.environ.get(
    "BUSINESS_COMPUTE_DOWNLOAD_SECRET", "local-business-compute-demo-secret"
)
DOWNLOAD_TOKEN_TTL_SECONDS = int(os.environ.get("BUSINESS_COMPUTE_DOWNLOAD_TTL", "900"))
REDIS_URL = os.environ.get("BUSINESS_COMPUTE_REDIS_URL", "redis://business-compute-redis:6379/0")
REDIS_STATE_KEY = os.environ.get("BUSINESS_COMPUTE_REDIS_STATE_KEY", "business-compute-demo:state")


def default_buyer_base_url() -> str:
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "127.0.0.1"
    return f"http://{ip}:{APP_PORT}"


PUBLIC_BASE_URL = os.environ.get(
    "BUSINESS_COMPUTE_PUBLIC_BASE_URL",
    os.environ.get("BUSINESS_COMPUTE_BUYER_BASE_URL", default_buyer_base_url()),
)
AGENT_BASE_URL = os.environ.get("BUSINESS_COMPUTE_AGENT_BASE_URL", default_buyer_base_url())

app = FastAPI(title="OmniClaw Business Demo")
EVENTS: deque[dict[str, Any]] = deque(maxlen=120)
RECENT_SETTLEMENTS: deque[dict[str, Any]] = deque(maxlen=40)
SESSION_STORE: dict[str, dict[str, Any]] = {}
METRICS: dict[str, Any] = {
    "revenue_usdc": 0.0,
    "deliveries": 0,
    "compute_runs": 0,
    "paper_unlocks": 0,
    "downloads": 0,
    "sessions_created": 0,
}
REDIS_CLIENT: redis.Redis | None = None


@dataclass
class ComputeProduct:
    kind: str
    slug: str
    label: str
    price_usdc: str
    description: str
    job: str
    size: int


@dataclass
class SessionProduct:
    kind: str
    slug: str
    label: str
    price_usdc: str
    description: str
    tier: str
    credits: int


@dataclass
class PaperProduct:
    kind: str
    slug: str
    label: str
    price_usdc: str
    description: str
    title: str
    abstract: str
    filename: str


COMPUTE_PRODUCTS = [
    ComputeProduct(
        kind="compute",
        slug="prime-quick",
        label="Quick prime scan",
        price_usdc="0.01",
        description="Counts primes up to 1,000.",
        job="prime-count",
        size=1000,
    ),
    ComputeProduct(
        kind="compute",
        slug="prime-research",
        label="Research prime batch",
        price_usdc="0.25",
        description="Counts primes up to 70,000.",
        job="prime-count",
        size=70000,
    ),
    ComputeProduct(
        kind="compute",
        slug="fib-long",
        label="Fibonacci long-run",
        price_usdc="0.05",
        description="Computes fibonacci(250).",
        job="fib",
        size=250,
    ),
]

PAPER_PRODUCTS = [
    PaperProduct(
        kind="paper",
        slug="agentic-wallet-control-plane",
        label="Policy-Controlled Agent Finance",
        price_usdc="0.03",
        description="A concise paper on why wallets become policy systems in the agent era.",
        title="Policy-Controlled Agent Finance",
        abstract="A short research note on zero-trust financial execution, bounded authority, and why agentic commerce requires a control plane above settlement rails.",
        filename="policy-controlled-agent-finance.pdf",
    ),
    PaperProduct(
        kind="paper",
        slug="machine-commerce-settlement",
        label="Machine Commerce Settlement Design",
        price_usdc="0.04",
        description="A paper on buyer/seller settlement loops with x402 and batch settlement.",
        title="Machine Commerce Settlement Design",
        abstract="A short paper explaining why buyer usability depends on seller-side acceptance, verification, and batch settlement visibility.",
        filename="machine-commerce-settlement-design.pdf",
    ),
]


SESSION_PRODUCTS = [
    SessionProduct(
        kind="session",
        slug="compute-starter-session",
        label="Compute starter session",
        price_usdc="0.08",
        description="Creates a short-lived compute session with 3 credits for queued jobs.",
        tier="starter",
        credits=3,
    ),
    SessionProduct(
        kind="session",
        slug="compute-research-session",
        label="Compute research session",
        price_usdc="0.20",
        description="Creates a research session with 10 credits for larger compute jobs.",
        tier="research",
        credits=10,
    ),
]


HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>OmniClaw Arc Vendor Demo</title>
  <style>
    :root {
      --bg: #0c1220;
      --panel: #141c2b;
      --line: #263347;
      --text: #e8edf4;
      --muted: #9aa7b8;
      --accent: #2f81f7;
      --accent2: #1d4ed8;
      --good: #2ea043;
      --warn: #d29922;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; color: var(--text); background: radial-gradient(circle at top, #13203a 0%, #0c1220 55%); }
    .wrap { max-width: 1260px; margin: 0 auto; padding: 28px 20px 54px; }
    .hero { display: grid; gap: 10px; margin-bottom: 22px; }
    .eyebrow { display: inline-block; width: fit-content; padding: 5px 10px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: 12px; }
    h1 { margin: 0; font-size: 40px; line-height: 1.05; }
    .sub { color: var(--muted); font-size: 18px; max-width: 860px; }
    .meta { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 22px; }
    .stat, .panel, .product { background: rgba(20,28,43,.92); border: 1px solid var(--line); border-radius: 18px; }
    .stat { padding: 14px; }
    .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .v { margin-top: 6px; font-size: 15px; font-weight: 600; word-break: break-word; }
    .layout { display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; }
    .stack { display: grid; gap: 16px; }
    .panel { padding: 18px; }
    .panel h2 { margin: 0 0 12px; font-size: 19px; }
    .products { display: grid; gap: 12px; }
    .product { padding: 16px; }
    .product h3 { margin: 0 0 6px; font-size: 18px; }
    .product p { margin: 0 0 12px; color: var(--muted); }
    .badges { margin-bottom: 10px; }
    .badge { display: inline-block; padding: 4px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); font-size: 12px; margin-right: 6px; margin-bottom: 6px; }
    .url { font-family: ui-monospace, monospace; font-size: 13px; padding: 10px; border-radius: 10px; border: 1px solid var(--line); background: #0b1020; overflow-wrap: anywhere; }
    .small { color: var(--muted); font-size: 13px; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    button { cursor: pointer; border: 0; border-radius: 10px; padding: 10px 14px; font-weight: 600; color: white; background: linear-gradient(180deg, var(--accent), var(--accent2)); }
    button.secondary { background: transparent; border: 1px solid var(--line); color: var(--text); }
    pre { margin: 0; font-family: ui-monospace, monospace; white-space: pre-wrap; word-break: break-word; font-size: 12px; }
    .events { display: grid; gap: 8px; max-height: 620px; overflow: auto; }
    .evt { border-left: 3px solid var(--accent); padding: 10px; background: rgba(11,16,32,.75); border-radius: 10px; }
    .evt.good { border-left-color: var(--good); }
    .evt.warn { border-left-color: var(--warn); }
    .evt .t { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    .evt .m { font-size: 14px; }
    @media (max-width: 980px) {
      .meta { grid-template-columns: 1fr; }
      .layout { grid-template-columns: 1fr; }
      h1 { font-size: 32px; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"hero\">
      <div class=\"eyebrow\">Arc Vendor Flow</div>
      <h1>Arc vendor services powered by OmniClaw</h1>
      <div class=\"sub\">This server is the vendor surface. It exposes paid compute and paid research-paper products over HTTP, uses OmniClaw directly for seller-side x402 verification and Circle Gateway settlement, and only unlocks the product after payment. The buyer is expected to be your external Telegram/OpenClaw agent using omniclaw-cli against the buyer policy engine.</div>
    </div>
    <div class=\"meta\" id=\"meta\"></div>
    <div class=\"meta\" id=\"summary\"></div>
    <div class=\"layout\">
      <div class=\"stack\">
        <div class=\"panel\">
          <h2>Business products</h2>
          <div id=\"products\" class=\"products\"></div>
        </div>
        <div class=\"panel\">
          <h2>Buyer usage</h2>
          <div class=\"small\">Use the exact paid URL below inside Telegram/OpenClaw. This deployed flow assumes your external agent is the real buyer.</div>
          <div style=\"height:10px\"></div>
          <pre id=\"buyerPrompt\"></pre>
        </div>
      </div>
      <div class=\"stack\">
        <div class=\"panel\">
          <h2>Seller event log</h2>
          <div class="small">402 first, then 200 after seller-side verification and settlement.</div>
          <div class=\"events\" id=\"events\"></div>
        </div>
        <div class=\"panel\">
          <h2>Business settlements</h2>
          <pre id=\"settlements\">No settlements yet.</pre>
        </div>
        <div class=\"panel\">
          <h2>Buyer integration</h2>
          <pre id=\"result\">External buyer mode. Use your Telegram/OpenClaw agent with the buyer policy engine details printed by the launcher.</pre>
        </div>
      </div>
    </div>
  </div>
<script>
async function fetchJSON(path, opts) {
  const res = await fetch(path, opts);
  return await res.json();
}
function esc(s) { return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
async function load() {
  const [catalog, summary] = await Promise.all([fetchJSON('/api/catalog'), fetchJSON('/api/summary')]);
  window.__products = catalog.products;
  window.__enableLocalBuyer = Boolean(catalog.enable_local_buyer);
  document.getElementById('meta').innerHTML = `
    <div class="stat"><div class="k">Network</div><div class="v">${esc(catalog.network)}</div></div>
    <div class="stat"><div class="k">Seller policy engine</div><div class="v">${esc(catalog.seller_server)}</div></div>
    <div class="stat"><div class="k">Buyer policy engine</div><div class="v">${esc(catalog.buyer_server)}</div></div>
    <div class="stat"><div class="k">Buyer-facing base</div><div class="v">${esc(catalog.buyer_base_url)}</div></div>
    <div class="stat"><div class="k">Buyer execution base</div><div class="v">${esc(catalog.agent_base_url)}</div></div>
    <div class="stat"><div class="k">Explorer</div><div class="v">${esc(catalog.explorer_base_url)}</div></div>
    <div class="stat"><div class="k">Browser base</div><div class="v">${esc(catalog.browser_base_url)}</div></div>`;
  document.getElementById('summary').innerHTML = `
    <div class="stat"><div class="k">Revenue</div><div class="v">$${esc(summary.revenue_usdc)} USDC</div></div>
    <div class="stat"><div class="k">Deliveries</div><div class="v">${esc(summary.deliveries)}</div></div>
    <div class="stat"><div class="k">Active sessions</div><div class="v">${esc(summary.active_sessions)}</div></div>
    <div class="stat"><div class="k">Downloads</div><div class="v">${esc(summary.downloads)}</div></div>`;
  document.getElementById('settlements').textContent = JSON.stringify(summary.recent_settlements, null, 2);
  document.getElementById('buyerPrompt').textContent = `pay for this url: ${catalog.products[0].pay_url}`;
  document.getElementById('products').innerHTML = catalog.products.map((p, i) => `
    <div class="product">
      <h3>${esc(p.label)} — $${esc(p.price_usdc)}</h3>
      <p>${esc(p.description)}</p>
      <div class="badges">${p.badges.map(b => `<span class="badge">${esc(b)}</span>`).join('')}</div>
      <div class="url">${esc(p.pay_url)}</div>
      <div class="small" style="margin-top:8px">Buyer execution URL: ${esc(p.pay_url)}</div>
      <div class="small" style="margin-top:4px">Public URL: ${esc(p.public_pay_url)}</div>
      <div class="small" style="margin-top:4px">Browser endpoint: ${esc(p.browser_url)}</div>
      <div class="actions">
        <button class="secondary" onclick='copyUrl(${i})'>Copy URL</button>
        <button class="secondary" onclick='copyPrompt(${i})'>Copy OpenClaw prompt</button>
        ${catalog.enable_local_buyer ? `<button onclick='runLocalBuyer(${i})'>Run local buyer test</button>` : ``}
      </div>
    </div>`).join('');
  await refreshEvents();
}
function copyUrl(i) {
  navigator.clipboard.writeText(window.__products[i].pay_url);
}
function copyPrompt(i) {
  navigator.clipboard.writeText('pay for this url: ' + window.__products[i].pay_url);
}
async function runLocalBuyer(i) {
  if (!window.__enableLocalBuyer) {
    document.getElementById('result').textContent = 'Local buyer mode disabled for this deployment.';
    return;
  }
  document.getElementById('result').textContent = 'Running local buyer payment...';
  const data = await fetchJSON('/api/demo/pay', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(window.__products[i])});
  document.getElementById('result').textContent = JSON.stringify(data, null, 2);
  await refreshEvents();
}
async function refreshEvents() {
  const [data, summary] = await Promise.all([fetchJSON('/api/events'), fetchJSON('/api/summary')]);
  document.getElementById('events').innerHTML = data.events.map(evt => `
    <div class="evt ${esc(evt.level)}">
      <div class="t">${esc(evt.time)} · ${esc(evt.stage)}</div>
      <div class="m">${esc(evt.message)}</div>
    </div>`).join('');
  document.getElementById('summary').innerHTML = `
    <div class="stat"><div class="k">Revenue</div><div class="v">$${esc(summary.revenue_usdc)} USDC</div></div>
    <div class="stat"><div class="k">Deliveries</div><div class="v">${esc(summary.deliveries)}</div></div>
    <div class="stat"><div class="k">Active sessions</div><div class="v">${esc(summary.active_sessions)}</div></div>
    <div class="stat"><div class="k">Downloads</div><div class="v">${esc(summary.downloads)}</div></div>`;
  document.getElementById('settlements').textContent = JSON.stringify(summary.recent_settlements, null, 2);
}
load();
setInterval(refreshEvents, 2000);
</script>
</body>
</html>"""


def connect_redis() -> redis.Redis | None:
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def serialize_state() -> dict[str, Any]:
    return {
        "events": list(EVENTS),
        "recent_settlements": list(RECENT_SETTLEMENTS),
        "sessions": SESSION_STORE,
        "metrics": METRICS,
    }


def load_state() -> None:
    global REDIS_CLIENT
    REDIS_CLIENT = connect_redis()
    if REDIS_CLIENT is None:
        return
    raw = REDIS_CLIENT.get(REDIS_STATE_KEY)
    if not raw:
        return
    data = json.loads(raw)
    EVENTS.clear()
    EVENTS.extend(data.get("events", []))
    RECENT_SETTLEMENTS.clear()
    RECENT_SETTLEMENTS.extend(data.get("recent_settlements", []))
    SESSION_STORE.clear()
    SESSION_STORE.update(data.get("sessions", {}))
    METRICS.update(data.get("metrics", {}))


def persist_state() -> None:
    if REDIS_CLIENT is None:
        return
    REDIS_CLIENT.set(REDIS_STATE_KEY, json.dumps(serialize_state()))


def reset_state() -> None:
    EVENTS.clear()
    RECENT_SETTLEMENTS.clear()
    SESSION_STORE.clear()
    METRICS.clear()
    METRICS.update(
        {
            "revenue_usdc": 0.0,
            "deliveries": 0,
            "compute_runs": 0,
            "paper_unlocks": 0,
            "downloads": 0,
            "sessions_created": 0,
        }
    )
    if REDIS_CLIENT is not None:
        REDIS_CLIENT.delete(REDIS_STATE_KEY)


def log_event(stage: str, message: str, level: str = "info") -> None:
    EVENTS.appendleft(
        {
            "time": time.strftime("%H:%M:%S"),
            "stage": stage,
            "message": message,
            "level": level,
        }
    )
    persist_state()


def record_settlement(
    kind: str, label: str, amount: str, payer: str, tx_hash: str, resource: str
) -> None:
    METRICS["revenue_usdc"] += float(amount)
    METRICS["deliveries"] += 1
    if kind == "compute":
        METRICS["compute_runs"] += 1
    elif kind == "paper":
        METRICS["paper_unlocks"] += 1
    elif kind == "session":
        METRICS["sessions_created"] += 1
    RECENT_SETTLEMENTS.appendleft(
        {
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "label": label,
            "amount_usdc": f"{float(amount):.2f}",
            "payer": payer or "unknown",
            "transaction": tx_hash,
            "resource": resource,
        }
    )
    persist_state()


def build_summary() -> dict[str, Any]:
    return {
        "revenue_usdc": f"{METRICS['revenue_usdc']:.2f}",
        "deliveries": METRICS["deliveries"],
        "compute_runs": METRICS["compute_runs"],
        "paper_unlocks": METRICS["paper_unlocks"],
        "downloads": METRICS["downloads"],
        "sessions_created": METRICS["sessions_created"],
        "recent_settlements": list(RECENT_SETTLEMENTS),
        "active_sessions": len(SESSION_STORE),
    }


def create_session(tier: str, credits: int, payer: str, tx_hash: str) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "tier": tier,
        "credits_total": credits,
        "credits_remaining": credits,
        "payer": payer or "unknown",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "transaction": tx_hash,
        "jobs": [],
    }
    SESSION_STORE[session_id] = session
    persist_state()
    return session


def run_session_job(session_id: str, job: str, size: int) -> dict[str, Any]:
    session = SESSION_STORE.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session["credits_remaining"] < 1:
        raise HTTPException(status_code=402, detail="session has no credits remaining")
    result = build_compute_result(job, size, session["payer"], "0.00", session["transaction"])
    session["credits_remaining"] -= 1
    session["jobs"].append(
        {
            "job": job,
            "size": size,
            "ran_at": time.strftime("%H:%M:%S"),
            "output": result["output"],
        }
    )
    METRICS["compute_runs"] += 1
    persist_state()
    return {
        "session_id": session_id,
        "tier": session["tier"],
        "credits_remaining": session["credits_remaining"],
        "job_result": result,
    }


def _download_payload(filename: str, tx_hash: str, expires: int) -> str:
    return f"{filename}:{tx_hash}:{expires}"


def sign_download_token(filename: str, tx_hash: str, expires: int | None = None) -> str:
    if expires is None:
        expires = int(time.time()) + DOWNLOAD_TOKEN_TTL_SECONDS
    payload = _download_payload(filename, tx_hash, expires)
    sig = hmac.new(DOWNLOAD_SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = {"filename": filename, "tx": tx_hash, "exp": expires, "sig": sig}
    return base64.urlsafe_b64encode(json.dumps(token).encode()).decode()


def verify_download_token(token: str, filename: str) -> None:
    try:
        data = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
    except Exception as exc:
        raise HTTPException(status_code=403, detail="invalid download token") from exc
    expected_filename = data.get("filename")
    tx_hash = data.get("tx", "")
    exp = int(data.get("exp", 0))
    sig = data.get("sig", "")
    if expected_filename != filename:
        raise HTTPException(status_code=403, detail="download token filename mismatch")
    if exp < int(time.time()):
        raise HTTPException(status_code=403, detail="download token expired")
    payload = _download_payload(filename, tx_hash, exp)
    expected_sig = hmac.new(
        DOWNLOAD_SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=403, detail="invalid download token signature")


def payment_response_header(verify_data: dict[str, Any]) -> str:
    return base64.b64encode(
        json.dumps(
            {
                "success": True,
                "transaction": verify_data.get("transaction", ""),
                "network": "",
                "payer": verify_data.get("sender", ""),
            }
        ).encode()
    ).decode()


def ensure_sample_pdf(path: Path, title: str, subtitle: str, body: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [title, subtitle, ""] + body
    escaped = []
    for raw in lines:
        raw = raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        escaped.append(raw)
    content_lines = ["BT", "/F1 18 Tf", "72 760 Td", f"({escaped[0]}) Tj"]
    content_lines += ["0 -26 Td", "/F1 12 Tf", f"({escaped[1]}) Tj"]
    y_step = -20
    for line in escaped[2:]:
        content_lines += [f"0 {y_step} Td", f"({line}) Tj"]
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objs = []
    objs.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objs.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objs.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objs.append(
        b"4 0 obj<< /Length "
        + str(len(stream)).encode()
        + b" >>stream\n"
        + stream
        + b"\nendstream\nendobj\n"
    )
    objs.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(pdf)


for paper in PAPER_PRODUCTS:
    ensure_sample_pdf(
        PAPERS_DIR / paper.filename,
        paper.title,
        "OmniClaw business demo paper",
        [
            paper.abstract,
            "",
            "Paid access is unlocked only after OmniClaw verification and Circle settlement.",
        ],
    )


async def seller_post(path: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(
            f"{SELLER_SERVER_URL}{path}",
            headers={"Authorization": f"Bearer {SELLER_TOKEN}"},
            json=payload,
        )


async def buyer_post(path: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.post(
            f"{BUYER_SERVER_URL}{path}",
            headers={"Authorization": f"Bearer {BUYER_TOKEN}"},
            json=payload,
        )


def build_compute_result(
    job: str, size: int, payer: str, amount: str, tx_hash: str
) -> dict[str, Any]:
    if job == "prime-count":
        if size < 10 or size > 500000:
            raise ValueError("size must be between 10 and 500000 for prime-count")
        output = {"prime_count": prime_count(size)}
    elif job == "fib":
        if size < 1 or size > 5000:
            raise ValueError("size must be between 1 and 5000 for fib")
        output = {"fib": str(fib(size))}
    else:
        raise ValueError(f"unsupported job: {job}")
    return {
        "service": "mini-aws-compute",
        "job": job,
        "input": {"size": size},
        "output": output,
        "paid_by": payer,
        "amount_usdc": amount,
        "settlement_tx": tx_hash,
    }


def prime_count(limit: int) -> int:
    if limit < 2:
        return 0
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for n in range(2, isqrt(limit) + 1):
        if sieve[n]:
            start = n * n
            step = n
            sieve[start : limit + 1 : step] = b"\x00" * (((limit - start) // step) + 1)
    return int(sum(sieve))


def fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def find_compute(slug: str) -> ComputeProduct:
    for product in COMPUTE_PRODUCTS:
        if product.slug == slug:
            return product
    raise KeyError(slug)


def find_paper(slug: str) -> PaperProduct:
    for paper in PAPER_PRODUCTS:
        if paper.slug == slug:
            return paper
    raise KeyError(slug)


async def requirements_response(resource: str, price: str) -> JSONResponse:
    resp = await seller_post(
        "/api/v1/x402/requirements", {"amount": f"${price}", "resource": resource}
    )
    req_data = resp.json()
    return JSONResponse(
        status_code=req_data.get("status_code", 402),
        content=req_data.get("detail", {}),
        headers=req_data.get("headers", {}),
    )


async def verify_or_402(
    request: Request, resource: str, price: str, label: str
) -> dict[str, Any] | JSONResponse:
    sig_header = request.headers.get("payment-signature") or request.headers.get(
        "PAYMENT-SIGNATURE"
    )
    if not sig_header:
        log_event("payment-required", f"Unpaid request for {label} -> 402", "warn")
        return await requirements_response(resource, price)
    log_event(
        "verify", f"Payment signature received for {label}; verifying via OmniClaw seller backend"
    )
    verify = await seller_post(
        "/api/v1/x402/verify",
        {
            "signature": sig_header,
            "amount": price,
            "sender": request.headers.get("x-forwarded-for", ""),
            "resource": resource,
        },
    )
    verify_data = verify.json()
    if verify.status_code >= 400 or not verify_data.get("valid"):
        log_event("verify", f"Verification failed for {label}", "warn")
        return await requirements_response(resource, price)
    return verify_data


@app.on_event("startup")
async def startup() -> None:
    load_state()
    log_event("boot", "Business seller booted. Waiting for buyer traffic.")


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return HTML


@app.get("/api/catalog")
async def catalog(request: Request) -> dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    products: list[dict[str, Any]] = []
    for product in COMPUTE_PRODUCTS:
        query = urlencode({"job": product.job, "size": product.size})
        browser_url = f"{base_url}/compute?{query}"
        pay_url = f"{AGENT_BASE_URL}/compute?{query}"
        public_pay_url = f"{PUBLIC_BASE_URL}/compute?{query}"
        products.append(
            {
                **asdict(product),
                "browser_url": browser_url,
                "pay_url": pay_url,
                "public_pay_url": public_pay_url,
                "badges": ["compute", f"job={product.job}", f"size={product.size}"],
            }
        )
    for session in SESSION_PRODUCTS:
        browser_url = f"{base_url}/compute/session?tier={session.tier}"
        pay_url = f"{AGENT_BASE_URL}/compute/session?tier={session.tier}"
        public_pay_url = f"{PUBLIC_BASE_URL}/compute/session?tier={session.tier}"
        products.append(
            {
                **asdict(session),
                "browser_url": browser_url,
                "pay_url": pay_url,
                "public_pay_url": public_pay_url,
                "badges": ["session", session.tier, f"credits={session.credits}"],
            }
        )
    for paper in PAPER_PRODUCTS:
        browser_url = f"{base_url}/papers/{paper.slug}"
        pay_url = f"{AGENT_BASE_URL}/papers/{paper.slug}"
        public_pay_url = f"{PUBLIC_BASE_URL}/papers/{paper.slug}"
        products.append(
            {
                **asdict(paper),
                "browser_url": browser_url,
                "pay_url": pay_url,
                "public_pay_url": public_pay_url,
                "badges": ["paper", "pdf", paper.title],
            }
        )
    return {
        "network": NETWORK_NAME,
        "explorer_base_url": EXPLORER_BASE_URL,
        "seller_server": SELLER_SERVER_URL,
        "buyer_server": BUYER_SERVER_URL,
        "buyer_base_url": PUBLIC_BASE_URL,
        "agent_base_url": AGENT_BASE_URL,
        "browser_base_url": base_url,
        "enable_local_buyer": ENABLE_LOCAL_BUYER,
        "products": products,
    }


@app.get("/api/events")
async def events() -> dict[str, Any]:
    return {"events": list(EVENTS)}


@app.get("/api/summary")
async def summary() -> dict[str, Any]:
    return build_summary()


@app.post("/api/admin/reset")
async def admin_reset() -> dict[str, Any]:
    reset_state()
    log_event("boot", "Business seller reset. Waiting for buyer traffic.")
    return {"ok": True, "status": "reset"}


@app.post("/api/demo/pay")
async def demo_pay(payload: dict[str, Any]) -> JSONResponse:
    if not ENABLE_LOCAL_BUYER:
        return JSONResponse(
            status_code=409,
            content={"success": False, "status": "disabled", "detail": "Local buyer mode disabled"},
        )
    url = payload["pay_url"]
    log_event("buyer", f"Buyer initiated payment for {url}")
    resp = await buyer_post("/api/v1/x402/pay", {"url": url, "method": "GET"})
    data = resp.json()
    outcome = data.get("status", "unknown")
    log_event(
        "buyer",
        f"Buyer payment {outcome} for {payload['label']}",
        "good" if data.get("success") else "warn",
    )
    return JSONResponse(status_code=resp.status_code, content=data)


@app.get("/compute")
async def compute(request: Request) -> JSONResponse:
    params = request.query_params
    job = (params.get("job") or "prime-count").strip().lower()
    size = int((params.get("size") or "1000").strip())
    price = "0.10"
    label = f"compute job={job} size={size}"
    for product in COMPUTE_PRODUCTS:
        if product.job == job and product.size == size:
            price = product.price_usdc
            label = product.label
            break
    resource = str(request.url)
    verified = await verify_or_402(request, resource, price, label)
    if isinstance(verified, JSONResponse):
        return verified
    result = build_compute_result(
        job, size, verified.get("sender") or "unknown", price, verified.get("transaction") or ""
    )
    record_settlement(
        "compute",
        label,
        price,
        verified.get("sender") or "unknown",
        verified.get("transaction") or "",
        resource,
    )
    log_event(
        "delivery",
        f"Delivered compute result for {label}; tx {verified.get('transaction', '')}",
        "good",
    )
    return JSONResponse(
        status_code=200,
        content=result,
        headers={"PAYMENT-RESPONSE": payment_response_header(verified)},
    )


@app.get("/compute/session")
async def compute_session(request: Request) -> JSONResponse:
    tier = (request.query_params.get("tier") or "starter").strip().lower()
    product = next((p for p in SESSION_PRODUCTS if p.tier == tier), None)
    if product is None:
        raise HTTPException(status_code=404, detail="session tier not found")
    resource = str(request.url)
    verified = await verify_or_402(request, resource, product.price_usdc, product.label)
    if isinstance(verified, JSONResponse):
        return verified
    session = create_session(
        product.tier,
        product.credits,
        verified.get("sender") or "unknown",
        verified.get("transaction") or "",
    )
    record_settlement(
        "session",
        product.label,
        product.price_usdc,
        verified.get("sender") or "unknown",
        verified.get("transaction") or "",
        resource,
    )
    log_event("delivery", f"Created {product.label}; session {session['session_id']}", "good")
    return JSONResponse(
        status_code=200,
        content={
            "service": "mini-aws-compute",
            "product": product.label,
            "tier": product.tier,
            "session_id": session["session_id"],
            "credits_total": product.credits,
            "credits_remaining": product.credits,
            "submit_url": f"{PUBLIC_BASE_URL}/compute/jobs/{session['session_id']}?job=prime-count&size=5000",
            "status_url": f"{PUBLIC_BASE_URL}/compute/sessions/{session['session_id']}",
            "paid_by": verified.get("sender") or "unknown",
            "amount_usdc": product.price_usdc,
            "settlement_tx": verified.get("transaction") or "",
        },
        headers={"PAYMENT-RESPONSE": payment_response_header(verified)},
    )


@app.get("/compute/sessions/{session_id}")
async def compute_session_status(session_id: str) -> JSONResponse:
    session = SESSION_STORE.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(status_code=200, content=session)


@app.get("/compute/jobs/{session_id}")
async def compute_session_job(session_id: str, request: Request) -> JSONResponse:
    job = (request.query_params.get("job") or "prime-count").strip().lower()
    size = int((request.query_params.get("size") or "5000").strip())
    result = run_session_job(session_id, job, size)
    log_event("delivery", f"Ran session job {job} size={size} for session {session_id}", "good")
    return JSONResponse(status_code=200, content=result)


@app.get("/papers/{slug}")
async def paper(slug: str, request: Request) -> JSONResponse:
    paper = find_paper(slug)
    resource = str(request.url)
    verified = await verify_or_402(request, resource, paper.price_usdc, paper.label)
    if isinstance(verified, JSONResponse):
        return verified
    download_token = sign_download_token(paper.filename, verified.get("transaction") or "")
    download_url = f"{PUBLIC_BASE_URL}/downloads/{paper.filename}?token={download_token}"
    result = {
        "service": "research-library",
        "product": paper.title,
        "abstract": paper.abstract,
        "download_url": download_url,
        "format": "pdf",
        "paid_by": verified.get("sender") or "unknown",
        "amount_usdc": paper.price_usdc,
        "settlement_tx": verified.get("transaction") or "",
    }
    record_settlement(
        "paper",
        paper.title,
        paper.price_usdc,
        verified.get("sender") or "unknown",
        verified.get("transaction") or "",
        resource,
    )
    log_event(
        "delivery", f"Unlocked paper {paper.title}; tx {verified.get('transaction', '')}", "good"
    )
    return JSONResponse(
        status_code=200,
        content=result,
        headers={"PAYMENT-RESPONSE": payment_response_header(verified)},
    )


@app.get("/downloads/{filename}")
async def download_pdf(filename: str, token: str | None = None) -> FileResponse:
    if not token:
        raise HTTPException(status_code=403, detail="download token required")
    verify_download_token(token, filename)
    path = PAPERS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    METRICS["downloads"] += 1
    persist_state()
    log_event("download", f"PDF downloaded: {filename}")
    return FileResponse(path, media_type="application/pdf", filename=filename)
