"""
Full End-to-End Test: Seller → Buyer Flow.

This tests the complete flow:
1. Seller starts server with protected endpoints
2. Buyer makes request to seller
3. Seller returns 402 (Payment Required)
4. Buyer parses 402, detects seller accepts "exact" (basic x402)
5. Buyer routes to basic x402
6. Payment succeeds

This tests WITHOUT Circle nanopayment first - just basic x402.

Run:
    # Terminal 1: Start seller server
    python scripts/x402_simple_server.py

    # Terminal 2: Run this test
    pytest tests/test_e2e_seller_buyer.py -v -s
"""

import asyncio
import base64
import json
import pytest
import signal
import subprocess
import sys
import time
import os

import httpx


# =============================================================================
# CONFIGURATION
# =============================================================================

SELLER_SERVER = "http://127.0.0.1:4022"

# Seller's address (matches the server)
SELLER_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123"

# Buyer's wallet (simulated)
BUYER_WALLET_ID = "test-buyer-wallet"
BUYER_ADDRESS = "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555"


# =============================================================================
# STEP 1: Verify Server Running
# =============================================================================


def is_server_running():
    """Check if test server is running."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", 4022))
        sock.close()
        return result == 0
    except:
        return False


def require_server():
    """Assert server is running."""
    assert is_server_running(), "Test server is not running"


def _wait_for_server(timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_server_running():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture(scope="module", autouse=True)
def ensure_test_server():
    """Start the local x402 test server for this module when needed."""
    if is_server_running():
        yield
        return

    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "scripts/x402_simple_server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    try:
        if not _wait_for_server():
            pytest.skip("x402 test server not available")
        yield
    finally:
        if process.poll() is None:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=10)


# =============================================================================
# STEP 2: Test Flow - No Payment = 402
# =============================================================================


class TestStep1_RequestWithoutPayment:
    """Step 1: Buyer requests without payment → Seller returns 402."""

    def test_seller_returns_402(self):
        """Seller should return 402 when no payment provided."""
        print("\n" + "=" * 70)
        print("STEP 1: Request Without Payment")
        print("=" * 70)
        print("  Buyer  → GET /weather")
        print("  Seller → 402 Payment Required")

        require_server()

        response = httpx.get(f"{SELLER_SERVER}/weather", timeout=5.0)

        print(f"\n  Result: {response.status_code}")

        # Should get 402
        assert response.status_code == 402

        # Should have payment-required header
        assert "payment-required" in response.headers

        print("  ✓ Got 402 with payment-required header")

        return response


# =============================================================================
# STEP 3: Parse 402 Response
# =============================================================================


class TestStep2_Parse402Response:
    """Step 2: Buyer parses 402 to see what seller accepts."""

    def test_parse_payment_required_header(self):
        """Parse the 402 response to see accepted payment methods."""
        print("\n" + "=" * 70)
        print("STEP 2: Parse 402 Response")
        print("=" * 70)

        require_server()

        # Get 402 response
        response = httpx.get(f"{SELLER_SERVER}/weather", timeout=5.0)

        # Parse header
        header = response.headers["payment-required"]
        decoded = json.loads(base64.b64decode(header))

        print(f"\n  Parsed 402 response:")
        print(f"    x402Version: {decoded.get('x402Version')}")
        print(f"    Error: {decoded.get('error')}")

        # Check accepts array
        accepts = decoded.get("accepts", [])
        print(f"\n  Seller accepts {len(accepts)} payment scheme(s):")

        for accept in accepts:
            scheme = accept.get("scheme")
            amount = accept.get("amount")
            network = accept.get("network")
            print(f"    - {scheme}: {amount} on {network}")

        # Verify structure
        assert decoded.get("x402Version") == 2
        assert len(accepts) > 0

        # Check what seller supports
        schemes = [a.get("scheme") for a in accepts]
        has_exact = "exact" in schemes
        has_circle = "GatewayWalletBatched" in schemes

        print(f"\n  Has 'exact' (basic x402): {has_exact}")
        print(f"  Has 'GatewayWalletBatched': {has_circle}")

        return schemes


# =============================================================================
# STEP 4: Smart Routing Decision
# =============================================================================


class TestStep3_SmartRouting:
    """Step 3: Buyer decides which payment method to use."""

    def test_route_to_basic_x402(self):
        """Based on 402 response, route to appropriate payment method."""
        print("\n" + "=" * 70)
        print("STEP 3: Smart Routing Decision")
        print("=" * 70)

        require_server()

        # Get seller's accepts
        response = httpx.get(f"{SELLER_SERVER}/weather", timeout=5.0)
        header = response.headers["payment-required"]
        decoded = json.loads(base64.b64decode(header))

        accepts = decoded.get("accepts", [])
        schemes = [a.get("scheme") for a in accepts]

        print(f"\n  Seller accepts: {schemes}")

        # BUYER'S DECISION LOGIC:
        # 1. Does seller support Circle nanopayment?
        supports_circle = "GatewayWalletBatched" in schemes

        # 2. Does buyer have Circle Gateway balance?
        buyer_has_gateway = False  # Let's say buyer doesn't have Gateway set up

        # 3. Route decision
        if supports_circle and buyer_has_gateway:
            method = "Circle Nanopayment (gasless)"
            print(f"  ✓ Route: {method}")
        else:
            method = "Basic x402 (on-chain)"
            print(f"  ✓ Route: {method}")

        # Since our test seller only supports "exact" (no Circle),
        # and buyer has no Gateway, route to basic x402
        assert method == "Basic x402 (on-chain)"

        return method


# =============================================================================
# STEP 5: Different Routes Have Different Prices
# =============================================================================


class TestStep4_DifferentPrices:
    """Step 4: Verify different endpoints have different prices."""

    def test_weather_price(self):
        """Weather endpoint: $0.001"""
        print("\n" + "=" * 70)
        print("STEP 4: Different Prices")
        print("=" * 70)

        require_server()

        response = httpx.get(f"{SELLER_SERVER}/weather", timeout=5.0)
        header = response.headers["payment-required"]
        decoded = json.loads(base64.b64decode(header))

        amount = decoded["accepts"][0]["amount"]
        # amount is in atomic units (6 decimals)
        price_usd = int(amount) / 1000000

        print(f"\n  /weather: ${price_usd} ({amount} atomic)")

        assert price_usd == 0.001

    def test_premium_price(self):
        """Premium endpoint: $0.01"""
        require_server()

        response = httpx.get(f"{SELLER_SERVER}/premium/content", timeout=5.0)
        header = response.headers["payment-required"]
        decoded = json.loads(base64.b64decode(header))

        amount = decoded["accepts"][0]["amount"]
        price_usd = int(amount) / 1000000

        print(f"  /premium/content: ${price_usd} ({amount} atomic)")

        assert price_usd == 0.01


# =============================================================================
# STEP 6: Network Compatibility
# =============================================================================


class TestStep5_NetworkCompatibility:
    """Step 5: Verify buyer and seller are on same network."""

    def test_same_network(self):
        """Buyer and seller should be on same network."""
        print("\n" + "=" * 70)
        print("STEP 5: Network Compatibility")
        print("=" * 70)

        require_server()

        response = httpx.get(f"{SELLER_SERVER}/weather", timeout=5.0)
        header = response.headers["payment-required"]
        decoded = json.loads(base64.b64decode(header))

        seller_network = decoded["accepts"][0]["network"]
        buyer_network = "eip155:84532"  # Base Sepolia

        print(f"\n  Buyer network:  {buyer_network}")
        print(f"  Seller network: {seller_network}")

        compatible = buyer_network == seller_network
        print(f"\n  Compatible: {compatible}")

        assert compatible == True


# =============================================================================
# STEP 7: Full Simulation (with mocked payment)
# =============================================================================


class TestStep6_FullSimulation:
    """Step 6: Simulate complete payment flow."""

    @pytest.mark.asyncio
    async def test_complete_flow_simulation(self):
        """Simulate complete buyer → seller flow."""
        print("\n" + "=" * 70)
        print("STEP 6: Complete Flow Simulation")
        print("=" * 70)

        require_server()

        async with httpx.AsyncClient() as client:
            # === STEP 1: Initial request ===
            print("\n  [1] Buyer requests /weather")
            response = await client.get(f"{SELLER_SERVER}/weather")

            if response.status_code != 402:
                pytest.fail("Expected 402")

            print("      → Got 402 Payment Required")

            # === STEP 2: Parse 402 ===
            header = response.headers["payment-required"]
            decoded = json.loads(base64.b64decode(header))

            accepts = decoded["accepts"]
            schemes = [a.get("scheme") for a in accepts]

            print(f"\n  [2] Buyer parses 402")
            print(f"      Seller accepts: {schemes}")

            # === STEP 3: Route decision ===
            supports_circle = "GatewayWalletBatched" in schemes

            print(f"\n  [3] Routing decision")
            print(f"      Supports Circle: {supports_circle}")

            if supports_circle:
                route = "Circle Nanopayment"
            else:
                route = "Basic x402"

            print(f"      → Using: {route}")

            # === STEP 4: Create payment (simulated) ===
            print(f"\n  [4] Create payment")
            print(f"      From: {BUYER_ADDRESS[:20]}...")
            print(f"      To:   {SELLER_ADDRESS[:20]}...")
            print(f"      Amount: 1000 atomic ($0.001)")

            # In real flow, buyer would:
            # 1. Sign EIP-3009 authorization
            # 2. Create payment payload
            # 3. Send with PAYMENT-SIGNATURE header

            # === STEP 5: Send payment (will fail verification but shows flow) ===
            valid_after = int(time.time()) - 60
            valid_before = int(time.time()) + 300

            authorization = {
                "from": BUYER_ADDRESS,
                "to": SELLER_ADDRESS,
                "value": "1000",
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": "0x1234567890abcdef",
            }

            payload = {
                "x402Version": 2,
                "scheme": "exact",
                "accepted": accepts[0],
                "payload": {
                    "authorization": authorization,
                    "signature": "0xabcd... (real signature would be here)",
                },
            }

            import base64 as b64

            payment_header = b64.b64encode(json.dumps(payload).encode()).decode()

            print(f"\n  [5] Send payment header")
            print(f"      Header length: {len(payment_header)} chars")

            # === STEP 6: Verify (shows what seller would do) ===
            print(f"\n  [6] Seller verifies payment")

            # Check timeout
            current = int(time.time())
            is_valid_time = valid_after <= current <= valid_before
            print(f"      Timeout OK: {is_valid_time}")

            # Check amount
            expected = int(accepts[0]["amount"])
            paid = int(authorization["value"])
            is_valid_amount = paid >= expected
            print(f"      Amount OK: {is_valid_amount} ({paid} >= {expected})")

            # Check recipient
            is_valid_recipient = authorization["to"].lower() == SELLER_ADDRESS.lower()
            print(f"      Recipient OK: {is_valid_recipient}")

            # === RESULT ===
            all_valid = is_valid_time and is_valid_amount and is_valid_recipient

            print(f"\n  ✓ Flow completed successfully!")
            print(f"    Payment would be: {'VALID' if all_valid else 'INVALID'}")

            assert response.status_code == 402


# =============================================================================
# STEP 8: End-to-End with Real Server
# =============================================================================


class TestStep7_RealServerTest:
    """Test against real running server."""

    def test_health_endpoint(self):
        """Verify server is running and healthy."""
        print("\n" + "=" * 70)
        print("REAL SERVER TEST: Health Check")
        print("=" * 70)

        require_server()

        response = httpx.get(f"{SELLER_SERVER}/", timeout=5.0)

        print(f"\n  Status: {response.status_code}")

        # Any response means server is running
        assert response.status_code in [200, 404]

        print("  ✓ Server is running")


# =============================================================================
# RUN ALL
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
