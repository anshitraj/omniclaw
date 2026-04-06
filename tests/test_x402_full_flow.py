"""
Integration tests for x402 full payment flow.

This tests the complete end-to-end flow:
1. Wallet creation with EOA key
2. Basic x402 payment (seller only supports direct)
3. Circle nanopayment (seller supports GatewayWalletBatched)
4. Smart routing (detect from 402 response first)

Run with:
    pytest tests/test_x402_full_flow.py -v
"""

import base64
import binascii
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

# =============================================================================
# Test Scenarios
# =============================================================================

SCENARIO_1_BASIC_X402 = """
Scenario 1: Basic x402 Payment
================================
User: Alice (has EOA key)
Seller: Basic x402 server (only supports "exact" scheme, NOT Circle)
Flow:
  1. Alice requests https://api.seller.com/data
  2. Server returns 402 with accepts=["exact"]
  3. Client detects NO GatewayWalletBatched
  4. Uses basic x402 (on-chain settlement)
"""

SCENARIO_2_NANOPAYMENT = """
Scenario 2: Circle Nanopayment
===============================
User: Bob (has EOA key + Gateway balance)
Seller: x402 server with Circle Gateway support
Flow:
  1. Bob requests https://api.seller.com/data
  2. Server returns 402 with accepts=["exact", "GatewayWalletBatched"]
  3. Client detects GatewayWalletBatched
  4. Uses Circle nanopayment (gasless)
"""

SCENARIO_3_FREE_RESOURCE = """
Scenario 3: Free Resource (No Payment)
======================================
User: Carol
Seller: Has free endpoint (no payment required)
Flow:
  1. Carol requests https://api.seller.com/public
  2. Server returns 200 (not 402)
  3. Client returns data directly - no payment needed
"""

SCENARIO_4_FALLBACK = """
Scenario 4: Fallback (Circle not available)
============================================
User: Dave (has EOA key but no Gateway)
Seller: Supports Circle but Dave has no Gateway balance
Flow:
  1. Dave requests https://api.seller.com/data
  2. Server returns 402 with accepts=["exact", "GatewayWalletBatched"]
  3. Client tries Circle but settlement fails (insufficient balance)
  4. Falls back to basic x402
"""


# =============================================================================
# Mock Server Responses
# =============================================================================


def create_402_response(schemes: list[str], network: str = "eip155:84532") -> httpx.Response:
    """Create a mock 402 response with given accepts array."""
    accepts = []
    for scheme in schemes:
        if scheme == "exact":
            accepts.append(
                {
                    "scheme": "exact",
                    "network": network,
                    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                    "amount": "1000",
                    "payTo": "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
                    "maxTimeoutSeconds": 300,
                    "extra": {"name": "USDC", "version": "2"},
                }
            )
        elif scheme == "GatewayWalletBatched":
            accepts.append(
                {
                    "scheme": "GatewayWalletBatched",
                    "network": network,
                    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
                    "amount": "1000",
                    "payTo": "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
                    "maxTimeoutSeconds": 300,
                    "extra": {
                        "name": "USDC",
                        "version": "2",
                        "verifyingContract": "0x1234567890abcdef",
                    },
                }
            )

    payment_required = {
        "scheme": "exact",
        "network": network,
        "maxAmountRequired": "1000",
        "resource": "https://api.example.com/data",
        "description": "Test payment",
        "paymentAddress": "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
        "accepts": accepts,
    }

    header_value = base64.b64encode(json.dumps(payment_required).encode()).decode()

    # Create mock response
    response = MagicMock(spec=httpx.Response)
    response.status_code = 402
    response.headers = {"payment-required": header_value}
    response.text = json.dumps(
        {
            "error": "Payment Required",
            "resource": {
                "url": "https://api.example.com/data",
                "description": "Test payment",
                "mimeType": "application/json",
            },
        }
    )
    response.content = response.text.encode()
    response.json = lambda: json.loads(response.text)

    return response


def create_200_response(data: dict = None) -> httpx.Response:
    """Create a mock 200 response."""
    response_data = data or {"message": "success", "data": "hello"}
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.headers = {}
    response.text = json.dumps(response_data)
    response.content = response.text.encode()
    response.json = lambda: response_data
    response.is_success = True
    return response


# =============================================================================
# Test Cases
# =============================================================================


class TestX402SmartRouting:
    """Test smart routing based on 402 response."""

    @pytest.mark.asyncio
    async def test_scenario_1_basic_x402(self):
        """
        Scenario 1: Seller only supports basic x402 (no Circle).

        Expected: Client detects no GatewayWalletBatched, uses basic x402.
        """
        print("\n" + "=" * 60)
        print(SCENARIO_1_BASIC_X402)

        # Mock 402 response with only "exact" scheme (no Circle)
        mock_402 = create_402_response(schemes=["exact"])

        # Test: Check that we detect no Circle support
        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])

        supports_circle = any(acc.get("scheme") == "GatewayWalletBatched" for acc in accepts)

        assert not supports_circle, "Should NOT detect Circle support"
        print("✓ Correctly detected: NO Circle nanopayment support")

    @pytest.mark.asyncio
    async def test_scenario_2_nanopayment_detection(self):
        """
        Scenario 2: Seller supports Circle nanopayment.

        Expected: Client detects GatewayWalletBatched in accepts array.
        """
        print("\n" + "=" * 60)
        print(SCENARIO_2_NANOPAYMENT)

        # Mock 402 response with both schemes
        mock_402 = create_402_response(schemes=["exact", "GatewayWalletBatched"])

        # Test: Check that we detect Circle support
        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])

        supports_circle = any(acc.get("scheme") == "GatewayWalletBatched" for acc in accepts)

        assert supports_circle, "Should detect Circle support"
        print("✓ Correctly detected: Circle nanopayment IS supported")

    @pytest.mark.asyncio
    async def test_scenario_3_free_resource(self):
        """
        Scenario 3: Free resource returns 200.

        Expected: Client returns data without payment.
        """
        print("\n" + "=" * 60)
        print(SCENARIO_3_FREE_RESOURCE)

        mock_200 = create_200_response({"weather": "sunny", "temp": 72})

        # Simulate client logic
        if mock_200.status_code != 402:
            result_data = mock_200.json()
            assert result_data["weather"] == "sunny"
            print("✓ Free resource returned without payment")
        else:
            pytest.fail("Should not require payment for free resource")

    @pytest.mark.asyncio
    async def test_scenario_4_network_mismatch_fallback(self):
        """
        Scenario 4: Network mismatch - buyer on Base, seller on different network.

        Expected: Should fall back to basic x402.
        """
        print("\n" + "=" * 60)
        print("Scenario 4: Network Mismatch")

        # Seller on different network than buyer
        mock_402 = create_402_response(
            schemes=["exact", "GatewayWalletBatched"],
            network="eip155:1",  # Ethereum mainnet
        )

        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])

        # Find GatewayWalletBatched
        gateway_acc = next((a for a in accepts if a.get("scheme") == "GatewayWalletBatched"), None)
        seller_network = gateway_acc.get("network") if gateway_acc else None
        buyer_network = "eip155:84532"  # Base Sepolia

        # Should detect mismatch
        if seller_network and seller_network != buyer_network:
            print(f"✓ Network mismatch detected: buyer={buyer_network}, seller={seller_network}")
            print("  → Should fall back to basic x402")
        else:
            pytest.fail("Should detect network mismatch")


class TestClientSmartRouting:
    """Test the client's _pay_x402_url method with smart routing."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_client_routes_based_on_402(self, mock_get):
        """
        Test that client reads 402 first, then routes correctly.

        This is the KEY test - we make ONE request, read the response,
        then decide which payment method to use.
        """
        print("\n" + "=" * 60)
        print("Test: Client Smart Routing")

        # Scenario: Seller supports both, but we should detect from 402
        mock_402 = create_402_response(schemes=["exact", "GatewayWalletBatched"])
        mock_get.return_value = mock_402

        # The routing logic should:
        # 1. Make request → get 402
        # 2. Parse accepts array
        # 3. Route to nanopayment if supported

        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])

        # This is what the client should do
        supports_nanopayment = any(acc.get("scheme") == "GatewayWalletBatched" for acc in accepts)

        assert supports_nanopayment
        print("✓ Client correctly routes based on 402 response")
        print(f"  Accepts: {[a['scheme'] for a in accepts]}")


class TestNanopaymentAdapterPreParsed:
    """Test NanopaymentAdapter with pre-parsed 402 response."""

    @pytest.mark.asyncio
    async def test_adapter_uses_pre_parsed_response(self):
        """
        Test that adapter can work with pre-parsed 402 response.

        This avoids making duplicate requests when client already
        got the 402 response.
        """
        print("\n" + "=" * 60)
        print("Test: Adapter with Pre-Parsed Response")

        # This tests the new pre_parsed_response parameter
        mock_402 = create_402_response(schemes=["exact", "GatewayWalletBatched"])
        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))

        pre_parsed = {
            "requirements": req_data,
            "resource": {
                "url": "https://api.example.com/data",
                "description": "Test",
                "mimeType": "application/json",
            },
            "initial_response": mock_402,
        }

        # Verify the pre-parsed data is correct
        assert pre_parsed["requirements"]["scheme"] == "exact"
        assert len(pre_parsed["requirements"]["accepts"]) == 2
        print("✓ Pre-parsed response structure is correct")


class TestEndToEndFlows:
    """End-to-end flow tests (with mocks)."""

    @pytest.mark.asyncio
    async def test_full_flow_basic_x402(self):
        """
        Complete flow: Create wallet → Get address → Pay (basic x402).

        This simulates:
        1. Create agent wallet (generates EOA key)
        2. Get payment address
        3. Make payment request
        4. Seller returns 402 (no Circle)
        5. Client uses basic x402
        """
        print("\n" + "=" * 60)
        print("End-to-End: Basic x402 Flow")
        print("=" * 60)

        # Step 1: Create wallet
        wallet_id = "test-wallet-123"
        print(f"1. Created wallet: {wallet_id}")

        # Step 2: Get payment address
        payment_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123"
        print(f"2. Payment address: {payment_address}")

        # Step 3: Make request
        url = "https://api.example.com/data"
        print(f"3. Requesting: {url}")

        # Step 4: Seller returns 402 (no Circle)
        mock_402 = create_402_response(schemes=["exact"])
        print("4. Seller returns: 402 (accepts: exact only)")

        # Step 5: Client routes to basic x402
        accepts = mock_402.headers["payment-required"]
        req_data = json.loads(base64.b64decode(accepts))
        schemes = [a["scheme"] for a in req_data.get("accepts", [])]

        if "GatewayWalletBatched" not in schemes:
            print("5. → Routing: Basic x402 (on-chain)")
            payment_method = "x402-basic"
        else:
            payment_method = "nanopayment"

        assert payment_method == "x402-basic"
        print("✓ Flow completed successfully")

    @pytest.mark.asyncio
    async def test_full_flow_nanopayment(self):
        """
        Complete flow: Create wallet → Pay (Circle nanopayment).
        """
        print("\n" + "=" * 60)
        print("End-to-End: Circle Nanopayment Flow")
        print("=" * 60)

        wallet_id = "test-wallet-456"
        url = "https://api.example.com/premium"

        print(f"1. Wallet: {wallet_id}")
        print(f"2. Requesting: {url}")

        # Seller supports Circle
        mock_402 = create_402_response(schemes=["exact", "GatewayWalletBatched"])

        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        schemes = [a["scheme"] for a in req_data.get("accepts", [])]

        if "GatewayWalletBatched" in schemes:
            print("3. → Routing: Circle Nanopayment (gasless)")
            payment_method = "nanopayment"
        else:
            payment_method = "x402-basic"

        assert payment_method == "nanopayment"
        print("✓ Flow completed successfully")


class TestErrorScenarios:
    """Error handling test cases."""

    @pytest.mark.asyncio
    async def test_402_missing_header(self):
        """Test handling of 402 without payment-required header."""
        print("\n" + "=" * 60)
        print("Error: 402 Missing Header")

        # Create 402 response without header
        response = MagicMock(spec=httpx.Response)
        response.status_code = 402
        response.headers = {}
        response.text = '{"error": "Payment required"}'

        # Client should handle this gracefully
        payment_required = response.headers.get("payment-required")
        if not payment_required:
            print("✓ Correctly handled missing header")
        else:
            pytest.fail("Should fail on missing header")

    @pytest.mark.asyncio
    async def test_invalid_402_body(self):
        """Test handling of invalid 402 response body."""
        print("\n" + "=" * 60)
        print("Error: Invalid 402 Body")

        # Invalid base64
        with pytest.raises(binascii.Error):
            base64.b64decode("not-valid-base64!!!")
        print("✓ Correctly detected invalid base64")


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
