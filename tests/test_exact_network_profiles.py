from __future__ import annotations

from decimal import Decimal

from x402.schemas import AssetAmount

from omniclaw.facilitator.exact import load_exact_facilitator_config_from_env
from omniclaw.facilitator.networks import (
    build_exact_asset_amount,
    resolve_exact_settlement_network_profile,
)


def test_resolve_arc_exact_network_profile():
    profile = resolve_exact_settlement_network_profile("ARC-TESTNET")

    assert profile.label == "ARC-TESTNET"
    assert profile.caip2 == "eip155:5042002"
    assert profile.default_rpc_url == "https://rpc.testnet.arc.network"
    assert profile.explorer_base_url == "https://testnet.arcscan.app/tx/"
    assert profile.default_asset_address == "0x3600000000000000000000000000000000000000"


def test_resolve_base_sepolia_exact_network_profile():
    profile = resolve_exact_settlement_network_profile("BASE-SEPOLIA")

    assert profile.label == "BASE-SEPOLIA"
    assert profile.caip2 == "eip155:84532"
    assert profile.default_rpc_url == "https://sepolia.base.org"


def test_load_exact_facilitator_config_uses_profile_defaults(monkeypatch):
    monkeypatch.setenv("OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE", "ARC-TESTNET")
    monkeypatch.setenv(
        "OMNICLAW_X402_FACILITATOR_PRIVATE_KEY",
        "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )
    monkeypatch.delenv("OMNICLAW_X402_FACILITATOR_RPC_URL", raising=False)
    monkeypatch.delenv("OMNICLAW_X402_FACILITATOR_NETWORKS", raising=False)

    config = load_exact_facilitator_config_from_env()

    assert config.network_profile == "ARC-TESTNET"
    assert config.rpc_url == "https://rpc.testnet.arc.network"
    assert config.networks == ("eip155:5042002",)


def test_build_exact_asset_amount_for_arc():
    profile = resolve_exact_settlement_network_profile("ARC-TESTNET")

    result = build_exact_asset_amount(
        profile=profile,
        decimal_amount=Decimal("0.25"),
        network="eip155:5042002",
    )

    assert isinstance(result, AssetAmount)
    assert result.amount == "250000"
    assert result.asset == "0x3600000000000000000000000000000000000000"
    assert result.extra == {"name": "USDC", "version": "2"}


def test_build_exact_asset_amount_ignores_other_networks():
    profile = resolve_exact_settlement_network_profile("ARC-TESTNET")

    result = build_exact_asset_amount(
        profile=profile,
        decimal_amount="0.25",
        network="eip155:84532",
    )

    assert result is None
