"""
Real integration tests for x402 facilitators.

These tests hit actual facilitator APIs and require valid API keys.
Run with: pytest tests/test_facilitator_live_integration.py -v

For CI/local testing without keys, use environment variables:
- COINBASE_API_KEY
- ORDERN_API_KEY
- RBX_API_KEY
- THIRDWEB_API_KEY
- CIRCLE_API_KEY (for Circle facilitator)

Each test can be run individually:
- pytest tests/test_facilitator_live_integration.py::test_coinbase_verify -v
- pytest tests/test_facilitator_live_integration.py::test_ordern_verify -v
- etc.
"""

import os
import pytest
import asyncio
from typing import Optional

# Test payment payload/requirements for verification
TEST_PAYLOAD = {
    "x402Version": 2,
    "scheme": "exact",
    "payload": {
        "authorization": {
            "from": "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
            "to": "0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0",
            "value": "1000000",  # 1 USDC (6 decimals)
            "validAfter": 0,
            "validBefore": 9999999999,
        },
        "signature": "0xsig",
    },
}

TEST_REQUIREMENTS = {
    "scheme": "exact",
    "network": "eip155:84532",
    "asset": "0x4AE85d4018745B8C52bfec71E7f8Ca34E9E3c8A7",  # USDC on Base
    "amount": "1000000",
    "payTo": "0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0",
    "maxTimeoutSeconds": 300,
}


def get_api_key(provider: str) -> Optional[str]:
    """Get API key from environment or return None if not set."""
    env_vars = {
        "coinbase": "COINBASE_API_KEY",
        "ordern": "ORDERN_API_KEY",
        "rbx": "RBX_API_KEY",
        "thirdweb": "THIRDWEB_API_KEY",
        "circle": "CIRCLE_API_KEY",
    }
    return os.environ.get(env_vars.get(provider.lower(), ""))


def requires_api_key(provider: str):
    """Decorator to skip test if API key is not available."""
    key = get_api_key(provider)
    if not key:
        pytest.skip(
            f"API key not set for {provider}. Set {provider.upper()}_API_KEY environment variable."
        )
    return key


# =============================================================================
# Coinbase Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_coinbase_supported_networks():
    """Test fetching supported networks from Coinbase facilitator."""
    api_key = requires_api_key("coinbase")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="coinbase", api_key=api_key, environment="testnet")

    try:
        networks = await facilitator.get_supported_networks()

        # Should return a list of networks
        assert networks is not None
        assert isinstance(networks, list)

        # Print for debugging
        print(f"\nCoinbase supported networks: {networks}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_coinbase_verify():
    """Test Coinbase verify endpoint with test payload."""
    api_key = requires_api_key("coinbase")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="coinbase", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.verify(TEST_PAYLOAD, TEST_REQUIREMENTS)

        # Should return a VerifyResult
        assert hasattr(result, "is_valid")
        assert hasattr(result, "payer")

        print(f"\nCoinbase verify result: is_valid={result.is_valid}, payer={result.payer}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_coinbase_settle():
    """Test Coinbase settle endpoint with test payload."""
    api_key = requires_api_key("coinbase")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="coinbase", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.settle(TEST_PAYLOAD, TEST_REQUIREMENTS)

        # Should return a SettleResult
        assert hasattr(result, "success")
        assert hasattr(result, "transaction")
        assert hasattr(result, "error_reason")

        print(f"\nCoinbase settle result: success={result.success}, error={result.error_reason}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_coinbase_urls():
    """Verify Coinbase URLs for testnet and mainnet."""
    api_key = requires_api_key("coinbase")

    from omniclaw.seller import create_facilitator

    # Testnet
    facilitator_testnet = create_facilitator(
        provider="coinbase", api_key=api_key, environment="testnet"
    )
    assert facilitator_testnet.base_url == "https://api.cdp.coinbase.com/platform"
    await facilitator_testnet.close()

    # Mainnet
    facilitator_mainnet = create_facilitator(
        provider="coinbase", api_key=api_key, environment="mainnet"
    )
    assert facilitator_mainnet.base_url == "https://api.cdp.coinbase.com/platform"
    await facilitator_mainnet.close()

    print("\nCoinbase URLs verified successfully")


# =============================================================================
# OrderN Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_ordern_supported_networks():
    """Test fetching supported networks from OrderN facilitator."""
    api_key = requires_api_key("ordern")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="ordern", api_key=api_key, environment="testnet")

    try:
        networks = await facilitator.get_supported_networks()

        assert networks is not None
        assert isinstance(networks, list)

        print(f"\nOrderN supported networks: {networks}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_ordern_verify():
    """Test OrderN verify endpoint."""
    api_key = requires_api_key("ordern")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="ordern", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.verify(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "is_valid")
        assert hasattr(result, "payer")

        print(f"\nOrderN verify result: is_valid={result.is_valid}, payer={result.payer}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_ordern_settle():
    """Test OrderN settle endpoint."""
    api_key = requires_api_key("ordern")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="ordern", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.settle(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "success")
        assert hasattr(result, "transaction")

        print(f"\nOrderN settle result: success={result.success}, error={result.error_reason}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_ordern_urls():
    """Verify OrderN URLs."""
    api_key = requires_api_key("ordern")

    from omniclaw.seller import create_facilitator

    # Testnet
    f_testnet = create_facilitator(provider="ordern", api_key=api_key, environment="testnet")
    assert f_testnet.base_url == "https://api.testnet.ordern.ai"
    await f_testnet.close()

    # Mainnet
    f_mainnet = create_facilitator(provider="ordern", api_key=api_key, environment="mainnet")
    assert f_mainnet.base_url == "https://api.ordern.ai"
    await f_mainnet.close()

    print("\nOrderN URLs verified successfully")


# =============================================================================
# RBX Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_rbx_supported_networks():
    """Test fetching supported networks from RBX facilitator."""
    api_key = requires_api_key("rbx")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="rbx", api_key=api_key, environment="testnet")

    try:
        networks = await facilitator.get_supported_networks()

        assert networks is not None
        assert isinstance(networks, list)

        print(f"\nRBX supported networks: {networks}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_rbx_verify():
    """Test RBX verify endpoint."""
    api_key = requires_api_key("rbx")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="rbx", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.verify(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "is_valid")
        assert hasattr(result, "payer")

        print(f"\nRBX verify result: is_valid={result.is_valid}, payer={result.payer}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_rbx_settle():
    """Test RBX settle endpoint."""
    api_key = requires_api_key("rbx")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="rbx", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.settle(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "success")
        assert hasattr(result, "transaction")

        print(f"\nRBX settle result: success={result.success}, error={result.error_reason}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_rbx_urls():
    """Verify RBX URLs."""
    api_key = requires_api_key("rbx")

    from omniclaw.seller import create_facilitator

    f_testnet = create_facilitator(provider="rbx", api_key=api_key, environment="testnet")
    assert f_testnet.base_url == "https://api.testnet.rbx.io"
    await f_testnet.close()

    f_mainnet = create_facilitator(provider="rbx", api_key=api_key, environment="mainnet")
    assert f_mainnet.base_url == "https://api.rbx.io"
    await f_mainnet.close()

    print("\nRBX URLs verified successfully")


# =============================================================================
# Thirdweb Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_thirdweb_supported_networks():
    """Test fetching supported networks from Thirdweb facilitator."""
    api_key = requires_api_key("thirdweb")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="thirdweb", api_key=api_key, environment="testnet")

    try:
        networks = await facilitator.get_supported_networks()

        assert networks is not None
        assert isinstance(networks, list)

        print(f"\nThirdweb supported networks: {networks}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_thirdweb_verify():
    """Test Thirdweb verify endpoint."""
    api_key = requires_api_key("thirdweb")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="thirdweb", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.verify(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "is_valid")
        assert hasattr(result, "payer")

        print(f"\nThirdweb verify result: is_valid={result.is_valid}, payer={result.payer}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_thirdweb_settle():
    """Test Thirdweb settle endpoint."""
    api_key = requires_api_key("thirdweb")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="thirdweb", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.settle(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "success")
        assert hasattr(result, "transaction")

        print(f"\nThirdweb settle result: success={result.success}, error={result.error_reason}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_thirdweb_urls():
    """Verify Thirdweb URLs."""
    api_key = requires_api_key("thirdweb")

    from omniclaw.seller import create_facilitator

    f_testnet = create_facilitator(provider="thirdweb", api_key=api_key, environment="testnet")
    assert f_testnet.base_url == "https://gateway.thirdweb-test.com"
    await f_testnet.close()

    f_mainnet = create_facilitator(provider="thirdweb", api_key=api_key, environment="mainnet")
    assert f_mainnet.base_url == "https://gateway.thirdweb.com"
    await f_mainnet.close()

    print("\nThirdweb URLs verified successfully")


# =============================================================================
# Circle Gateway Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_circle_verify():
    """Test Circle Gateway verify endpoint."""
    api_key = requires_api_key("circle")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="circle", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.verify(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "is_valid")
        assert hasattr(result, "payer")

        print(f"\nCircle verify result: is_valid={result.is_valid}, payer={result.payer}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_circle_settle():
    """Test Circle Gateway settle endpoint."""
    api_key = requires_api_key("circle")

    from omniclaw.seller import create_facilitator

    facilitator = create_facilitator(provider="circle", api_key=api_key, environment="testnet")

    try:
        result = await facilitator.settle(TEST_PAYLOAD, TEST_REQUIREMENTS)

        assert hasattr(result, "success")
        assert hasattr(result, "transaction")

        print(f"\nCircle settle result: success={result.success}, error={result.error_reason}")

    finally:
        await facilitator.close()


@pytest.mark.asyncio
async def test_circle_urls():
    """Verify Circle Gateway URLs."""
    api_key = requires_api_key("circle")

    from omniclaw.seller import create_facilitator

    f_testnet = create_facilitator(provider="circle", api_key=api_key, environment="testnet")
    assert f_testnet.base_url == "https://gateway-api-testnet.circle.com"
    await f_testnet.close()

    f_mainnet = create_facilitator(provider="circle", api_key=api_key, environment="mainnet")
    assert f_mainnet.base_url == "https://gateway-api.circle.com"
    await f_mainnet.close()

    print("\nCircle Gateway URLs verified successfully")


# =============================================================================
# Test All Facilitators Together
# =============================================================================


@pytest.mark.asyncio
async def test_all_facilitators_interface():
    """Verify all facilitators have the correct interface."""
    providers = ["coinbase", "ordern", "rbx", "thirdweb", "circle"]

    results = {}

    for provider in providers:
        api_key = get_api_key(provider)
        if not api_key:
            print(f"\nSkipping {provider} - no API key")
            continue

        from omniclaw.seller import create_facilitator

        facilitator = create_facilitator(provider=provider, api_key=api_key, environment="testnet")

        # Verify interface
        assert hasattr(facilitator, "name")
        assert hasattr(facilitator, "base_url")
        assert hasattr(facilitator, "environment")
        assert hasattr(facilitator, "verify")
        assert hasattr(facilitator, "settle")
        assert hasattr(facilitator, "get_supported_networks")
        assert hasattr(facilitator, "close")

        results[provider] = "OK"

        await facilitator.close()

    print(f"\nFacilitators tested: {results}")

    # Skip if no facilitators could be tested (no API keys in CI)
    if len(results) == 0:
        pytest.skip("No facilitators were tested - no API keys available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
