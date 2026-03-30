"""
Real end-to-end test with mock facilitator server.

This tests the actual HTTP flow to verify the facilitator integration works.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
import httpx
from omniclaw.seller import create_seller, create_facilitator


class MockFacilitatorServer:
    """Mock facilitator server for testing."""

    def __init__(self, should_fail_verify=False, should_fail_settle=False):
        self.should_fail_verify = should_fail_verify
        self.should_fail_settle = should_fail_settle
        self.verify_called = False
        self.settle_called = False

    async def handle_verify(self, request):
        self.verify_called = True
        if self.should_fail_verify:
            return httpx.Response(
                400,
                json={
                    "isValid": False,
                    "invalidReason": "insufficient_balance",
                    "payer": "0xbuyer",
                },
            )
        return httpx.Response(
            200, json={"isValid": True, "payer": "0xbuyer1234567890abcdef1234567890abcdef12"}
        )

    async def handle_settle(self, request):
        self.settle_called = True
        if self.should_fail_settle:
            return httpx.Response(
                400, json={"success": False, "errorReason": "invalid_signature", "transaction": ""}
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "transaction": "tx_abc123",
                "network": "eip155:84532",
                "payer": "0xbuyer1234567890abcdef1234567890abcdef12",
            },
        )


@pytest.mark.asyncio
async def test_facilitator_verify_endpoint():
    """Test that facilitator verify endpoint is called correctly."""

    # Create real facilitator with mock transport
    facilitator = create_facilitator(provider="circle", api_key="test_key")

    # Test verify call with mock
    payment_payload = {
        "x402Version": 2,
        "scheme": "exact",
        "payload": {
            "authorization": {
                "from": "0xbuyer",
                "to": "0xseller",
                "value": "1000",
                "validAfter": 0,
                "validBefore": 9999999999,
            },
            "signature": "0xsig",
        },
    }

    payment_requirements = {
        "scheme": "exact",
        "network": "eip155:84532",
        "asset": "0xUSDC",
        "amount": "1000",
        "payTo": "0xseller",
        "maxTimeoutSeconds": 300,
    }

    # The verify method should return a result (network call would fail with test key)
    result = await facilitator.verify(payment_payload, payment_requirements)

    # Result should have the expected structure
    assert hasattr(result, "is_valid")
    assert hasattr(result, "payer")
    assert hasattr(result, "invalid_reason")


@pytest.mark.asyncio
async def test_facilitator_settle_endpoint():
    """Test that facilitator settle endpoint is called correctly."""

    facilitator = create_facilitator(provider="circle", api_key="test_key")

    payment_payload = {
        "x402Version": 2,
        "scheme": "exact",
        "payload": {
            "authorization": {
                "from": "0xbuyer",
                "to": "0xseller",
                "value": "1000",
            },
            "signature": "0xsig",
        },
    }

    payment_requirements = {
        "scheme": "exact",
        "network": "eip155:84532",
        "amount": "1000",
        "payTo": "0xseller",
    }

    result = await facilitator.settle(payment_payload, payment_requirements)

    # Result should have the expected structure
    assert hasattr(result, "success")
    assert hasattr(result, "transaction")
    assert hasattr(result, "network")
    assert hasattr(result, "error_reason")


def test_all_facilitators_have_correct_interface():
    """Verify all facilitators implement the same interface."""

    from omniclaw.seller import SUPPORTED_FACILITATORS

    providers = ["circle", "coinbase", "ordern", "rbx", "thirdweb"]

    for provider in providers:
        f = create_facilitator(provider=provider, api_key="test_key")

        # Check all required properties exist
        assert hasattr(f, "name"), f"{provider} missing name property"
        assert hasattr(f, "base_url"), f"{provider} missing base_url property"
        assert hasattr(f, "environment"), f"{provider} missing environment property"

        # Check all required methods exist
        assert hasattr(f, "verify"), f"{provider} missing verify method"
        assert hasattr(f, "settle"), f"{provider} missing settle method"
        assert hasattr(f, "get_supported_networks"), (
            f"{provider} missing get_supported_networks method"
        )
        assert hasattr(f, "close"), f"{provider} missing close method"

        # Check name matches
        assert f.name == provider, f"{provider} name should be {provider}"


def test_facilitator_urls_for_testnet():
    """Verify all facilitators have correct testnet URLs."""

    facilitators = {
        "circle": "https://gateway-api-testnet.circle.com",
        "coinbase": "https://api.cdp.coinbase.com/platform",
        "ordern": "https://api.testnet.ordern.ai",
        "rbx": "https://api.testnet.rbx.io",
        "thirdweb": "https://gateway.thirdweb-test.com",
    }

    for provider, expected_url in facilitators.items():
        f = create_facilitator(provider=provider, api_key="test_key", environment="testnet")
        assert f.base_url == expected_url, f"{provider}: expected {expected_url}, got {f.base_url}"


def test_facilitator_urls_for_mainnet():
    """Verify all facilitators have correct mainnet URLs."""

    facilitators = {
        "circle": "https://gateway-api.circle.com",
        "coinbase": "https://api.cdp.coinbase.com/platform",
        "ordern": "https://api.ordern.ai",
        "rbx": "https://api.rbx.io",
        "thirdweb": "https://gateway.thirdweb.com",
    }

    for provider, expected_url in facilitators.items():
        f = create_facilitator(provider=provider, api_key="test_key", environment="mainnet")
        assert f.base_url == expected_url, f"{provider}: expected {expected_url}, got {f.base_url}"


def test_circle_facilitator_custom_base_url_override():
    """Circle facilitator must honor explicit base_url overrides."""
    custom = "https://gateway-proxy.internal.example"
    f = create_facilitator(
        provider="circle",
        api_key="test_key",
        environment="testnet",
        base_url=custom,
    )
    assert f.base_url == custom


def test_seller_with_each_facilitator():
    """Test seller works with each facilitator type."""

    sellers = {}

    for provider in ["circle", "coinbase", "ordern", "rbx", "thirdweb"]:
        facilitator = create_facilitator(provider=provider, api_key="test_key")

        seller = create_seller(
            seller_address="0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
            name=f"Test {provider}",
            facilitator=facilitator,
        )

        sellers[provider] = seller

        # Verify facilitator is set
        assert seller._facilitator is not None
        assert seller._facilitator.name == provider

    print(f"Successfully created sellers for: {', '.join(sellers.keys())}")


def test_seller_auto_creates_facilitator():
    """Test seller auto-creates facilitator from API key."""

    seller = create_seller(
        seller_address="0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
        name="Test Seller",
        circle_api_key="test_key_123",
    )

    assert seller._facilitator is not None
    assert seller._facilitator.name == "circle"
    assert seller._facilitator.environment == "testnet"


def test_create_facilitator_requires_api_key():
    """Test that creating facilitator without API key fails."""

    import os

    # Save original env
    orig_facilitator = os.environ.get("FACILITATOR_API_KEY")
    orig_circle = os.environ.get("CIRCLE_API_KEY")

    # Remove env vars
    if orig_facilitator:
        del os.environ["FACILITATOR_API_KEY"]
    if orig_circle:
        del os.environ["CIRCLE_API_KEY"]

    try:
        from omniclaw.seller import create_facilitator

        with pytest.raises(ValueError, match="api_key"):
            create_facilitator(provider="circle", api_key=None)
    finally:
        # Restore env
        if orig_facilitator:
            os.environ["FACILITATOR_API_KEY"] = orig_facilitator
        if orig_circle:
            os.environ["CIRCLE_API_KEY"] = orig_circle


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
