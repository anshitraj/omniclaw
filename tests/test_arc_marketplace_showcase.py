from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_APP = ROOT / "examples" / "arc-marketplace-showcase" / "app.py"
DUMMY_PRIVATE_KEY = "0x" + "11" * 32


def _load_showcase_module(monkeypatch):
    monkeypatch.setenv("OMNICLAW_PRIVATE_KEY", DUMMY_PRIVATE_KEY)
    monkeypatch.delenv("OMNICLAW_X402_EXACT_PAY_TO", raising=False)
    monkeypatch.setenv("OMNICLAW_X402_EXACT_NETWORK_PROFILE", "ARC-TESTNET")
    monkeypatch.setenv("OMNICLAW_X402_EXACT_FACILITATOR_URL", "http://127.0.0.1:4022")
    monkeypatch.setenv("ARC_MARKETPLACE_PUBLIC_BASE_URL", "http://127.0.0.1:8020")
    monkeypatch.setenv("ARC_MARKETPLACE_BUYER_BASE_URL", "http://buyer.local:8020")

    module_name = f"arc_showcase_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, SHOWCASE_APP)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_arc_marketplace_catalog_uses_arc_exact_profile(monkeypatch):
    module = _load_showcase_module(monkeypatch)

    with TestClient(module.app) as client:
        response = client.get("/api/catalog")

    assert response.status_code == 200
    catalog = response.json()
    assert catalog["network_profile"] == "ARC-TESTNET"
    assert catalog["network"] == "eip155:5042002"
    assert catalog["asset"] == "0x3600000000000000000000000000000000000000"
    assert catalog["facilitator_url"] == "http://127.0.0.1:4022"
    assert catalog["explorer_base_url"] == "https://testnet.arcscan.app/tx/"
    assert catalog["buyer_engine_configured"] is False
    assert [product["slug"] for product in catalog["products"]] == [
        "prime-market-scan",
        "risk-oracle-brief",
        "settlement-receipt-kit",
    ]
    assert catalog["products"][0]["pay_url"] == "http://buyer.local:8020/buy/prime-market-scan"


def test_arc_marketplace_paid_routes_advertise_arc_exact(monkeypatch):
    module = _load_showcase_module(monkeypatch)

    route = module.routes["GET /buy/prime-market-scan"]
    payment_option = route.accepts[0]

    assert payment_option.scheme == "exact"
    assert payment_option.price == "$0.25"
    assert payment_option.network == "eip155:5042002"
    assert payment_option.pay_to == module.PAY_TO


def test_arc_marketplace_mini_agent_reports_missing_buyer_engine(monkeypatch):
    module = _load_showcase_module(monkeypatch)

    with TestClient(module.app) as client:
        response = client.post("/api/agent/inspect/prime-market-scan")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["status_code"] == 503
    assert "Buyer Financial Policy Engine" in body["error"]
