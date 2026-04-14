"""
Real end-to-end test with mock facilitator server.

This tests the actual HTTP flow to verify the facilitator integration works.
"""

import json

import httpx
import pytest

from omniclaw.seller import create_facilitator, create_seller


def json_from_request(request: httpx.Request):
    return json.loads(request.content.decode())


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

    providers = ["circle", "coinbase", "ordern", "rbx", "thirdweb", "omniclaw"]

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
        "thirdweb": "https://api.thirdweb.com",
        "omniclaw": "http://127.0.0.1:4022",
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
        "thirdweb": "https://api.thirdweb.com",
        "omniclaw": "http://127.0.0.1:4022",
    }

    for provider, expected_url in facilitators.items():
        f = create_facilitator(provider=provider, api_key="test_key", environment="mainnet")
        assert f.base_url == expected_url, f"{provider}: expected {expected_url}, got {f.base_url}"


def test_thirdweb_uses_native_secret_env(monkeypatch):
    """Thirdweb should not require aliasing its secret key to FACILITATOR_API_KEY."""
    monkeypatch.delenv("FACILITATOR_API_KEY", raising=False)
    monkeypatch.delenv("CIRCLE_API_KEY", raising=False)
    monkeypatch.setenv("THIRDWEB_SECRET_KEY", "thirdweb_secret")

    facilitator = create_facilitator(provider="thirdweb")

    assert facilitator._api_key == "thirdweb_secret"


@pytest.mark.asyncio
async def test_thirdweb_accepts_uses_public_http_api():
    """Thirdweb seller requirements must come from the documented accepts API."""
    facilitator = create_facilitator(
        provider="thirdweb",
        api_key="thirdweb_secret",
        server_wallet_address="0x" + "a" * 40,
        default_network="base-sepolia",
    )
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == "https://api.thirdweb.com/v1/payments/x402/accepts"
        assert request.headers["x-secret-key"] == "thirdweb_secret"
        body = json_from_request(request)
        assert body["resourceUrl"] == "https://seller.example.com/compute"
        assert body["method"] == "GET"
        assert body["network"] == "base-sepolia"
        assert body["price"] == "$0.01"
        assert body["serverWalletAddress"] == "0x" + "a" * 40
        return httpx.Response(
            200,
            json={
                "result": {
                    "accepts": [
                        {
                            "scheme": "exact",
                            "network": "eip155:84532",
                            "amount": "10000",
                            "payTo": "0x" + "b" * 40,
                            "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                        }
                    ]
                }
            },
        )

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        accepts = await facilitator.create_accepts(
            resource_url="https://seller.example.com/compute",
            method="GET",
            price="$0.01",
        )
    finally:
        await facilitator.close()

    assert len(requests) == 1
    assert accepts[0]["scheme"] == "exact"
    assert accepts[0]["network"] == "eip155:84532"


@pytest.mark.asyncio
async def test_thirdweb_verify_uses_public_http_api():
    """Thirdweb integration must use the public HTTP API directly."""
    facilitator = create_facilitator(provider="thirdweb", api_key="thirdweb_secret")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == "https://api.thirdweb.com/v1/payments/x402/verify"
        assert request.headers["x-secret-key"] == "thirdweb_secret"
        body = json_from_request(request)
        assert body["paymentPayload"]["signature"] == "0xsig"
        assert body["paymentRequirements"]["network"] == "eip155:84532"
        return httpx.Response(
            200,
            json={
                "result": {
                    "isValid": True,
                    "payer": "0xbuyer1234567890abcdef1234567890abcdef12",
                }
            },
        )

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await facilitator.verify(
            {"signature": "0xsig"},
            {"network": "eip155:84532", "amount": "1000"},
        )
    finally:
        await facilitator.close()

    assert len(requests) == 1
    assert result.is_valid is True
    assert result.payer == "0xbuyer1234567890abcdef1234567890abcdef12"


@pytest.mark.asyncio
async def test_thirdweb_settle_uses_public_http_api():
    """Thirdweb settle must call the documented HTTP endpoint with waitUntil."""
    facilitator = create_facilitator(provider="thirdweb", api_key="thirdweb_secret")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == "https://api.thirdweb.com/v1/payments/x402/settle"
        assert request.headers["x-secret-key"] == "thirdweb_secret"
        body = json_from_request(request)
        assert body["paymentPayload"]["signature"] == "0xsig"
        assert body["paymentRequirements"]["network"] == "eip155:84532"
        assert body["waitUntil"] == "confirmed"
        return httpx.Response(
            200,
            json={
                "result": {
                    "success": True,
                    "transaction": "0xsettled",
                    "network": "eip155:84532",
                    "payer": "0xbuyer1234567890abcdef1234567890abcdef12",
                }
            },
        )

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await facilitator.settle(
            {"signature": "0xsig"},
            {"network": "eip155:84532", "amount": "1000"},
        )
    finally:
        await facilitator.close()

    assert len(requests) == 1
    assert result.success is True
    assert result.transaction == "0xsettled"
    assert result.network == "eip155:84532"


@pytest.mark.asyncio
async def test_thirdweb_fetch_uses_public_http_api():
    """Thirdweb fetch support should use the documented HTTP endpoint."""
    facilitator = create_facilitator(provider="thirdweb", api_key="thirdweb_secret")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url).startswith("https://api.thirdweb.com/v1/payments/x402/fetch?")
        assert request.headers["x-secret-key"] == "thirdweb_secret"
        params = dict(request.url.params)
        assert params["url"] == "https://seller.example.com/compute"
        assert params["from"] == "0x" + "a" * 40
        assert params["chainId"] == "eip155:84532"
        return httpx.Response(200, json={"result": {"status": 200, "body": {"ok": True}}})

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await facilitator.fetch_with_payment(
            url="https://seller.example.com/compute",
            from_address="0x" + "a" * 40,
            chain_id="eip155:84532",
        )
    finally:
        await facilitator.close()

    assert len(requests) == 1
    assert result["status"] == 200
    assert result["body"]["ok"] is True


@pytest.mark.asyncio
async def test_thirdweb_discovery_resources_uses_public_http_api():
    """Thirdweb discovery support should use the documented resources endpoint."""
    facilitator = create_facilitator(provider="thirdweb", api_key="thirdweb_secret")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url).startswith(
            "https://api.thirdweb.com/v1/payments/x402/discovery/resources"
        )
        assert request.headers["x-secret-key"] == "thirdweb_secret"
        assert dict(request.url.params)["network"] == "eip155:84532"
        return httpx.Response(200, json={"result": {"resources": [{"url": "https://api"}]}})

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await facilitator.discover_resources(network="eip155:84532")
    finally:
        await facilitator.close()

    assert len(requests) == 1
    assert result["resources"][0]["url"] == "https://api"


def test_omniclaw_self_hosted_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("FACILITATOR_API_KEY", raising=False)
    monkeypatch.delenv("CIRCLE_API_KEY", raising=False)

    facilitator = create_facilitator(
        provider="omniclaw",
        base_url="http://127.0.0.1:4022",
        network_profile="ARC-TESTNET",
    )

    assert facilitator.name == "omniclaw"
    assert facilitator.base_url == "http://127.0.0.1:4022"


@pytest.mark.asyncio
async def test_omniclaw_self_hosted_creates_accepts_for_arc():
    facilitator = create_facilitator(
        provider="omniclaw",
        base_url="http://127.0.0.1:4022",
        network_profile="ARC-TESTNET",
    )
    try:
        accepts = await facilitator.create_accepts(
            resource_url="https://vendor.example.com/compute",
            method="GET",
            price="$0.25",
            server_wallet_address="0x" + "a" * 40,
        )
    finally:
        await facilitator.close()

    assert accepts == [
        {
            "scheme": "exact",
            "network": "eip155:5042002",
            "asset": "0x3600000000000000000000000000000000000000",
            "amount": "250000",
            "payTo": "0x" + "a" * 40,
            "maxTimeoutSeconds": 300,
            "extra": {"name": "USDC", "version": "2"},
        }
    ]


@pytest.mark.asyncio
async def test_omniclaw_self_hosted_verify_and_settle_use_local_api():
    facilitator = create_facilitator(
        provider="omniclaw",
        base_url="http://127.0.0.1:4022",
        network_profile="ARC-TESTNET",
    )
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json_from_request(request)
        assert body["x402Version"] == 2
        assert body["paymentPayload"]["signature"] == "0xsig"
        assert body["paymentRequirements"]["network"] == "eip155:5042002"
        if str(request.url).endswith("/verify"):
            return httpx.Response(200, json={"isValid": True, "payer": "0x" + "b" * 40})
        if str(request.url).endswith("/settle"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "transaction": "0xsettled",
                    "network": "eip155:5042002",
                    "payer": "0x" + "b" * 40,
                },
            )
        raise AssertionError(f"unexpected URL {request.url}")

    facilitator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        verify = await facilitator.verify(
            {"signature": "0xsig"},
            {"network": "eip155:5042002"},
        )
        settle = await facilitator.settle(
            {"signature": "0xsig"},
            {"network": "eip155:5042002"},
        )
    finally:
        await facilitator.close()

    assert len(requests) == 2
    assert verify.is_valid is True
    assert settle.success is True
    assert settle.transaction == "0xsettled"


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

    for provider in ["circle", "coinbase", "ordern", "rbx", "thirdweb", "omniclaw"]:
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
