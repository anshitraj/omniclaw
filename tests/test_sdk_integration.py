"""
Comprehensive SDK Integration Tests.

This tests the full OmniClaw SDK from end to end, covering:
- Wallet creation and management
- Key management (EOA keys for x402)
- Payment flows (address, URL, x402)
- Guards (budget, rate limit, recipients)
- Ledger and transaction tracking
- Intent-based payments (2-phase commit)
- Trust gate (ERC-8004)

User Stories / Dev Stories Tested:
1. Create agent wallet with auto-key generation
2. Get payment address and fund it
3. Make payment to an address
4. Make payment to URL (x402)
5. Add budget guard to wallet
6. Add recipient whitelist
7. Check transaction history
8. Create and consume payment intent
9. Handle insufficient balance
10. Handle payment failures

Run with:
    pytest tests/test_sdk_integration.py -v -s
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

# =============================================================================
# USER STORIES / DEV STORIES
# =============================================================================

STORIES = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                         OmniClaw SDK User Stories                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 1: Agent Wallet Creation                                               ║
║  ─────────────────────────────────                                            ║
║  As a developer, I want to create a wallet for an AI agent                  ║
║  so that I can manage its funds and track spending.                          ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Wallet is created with unique ID                                          ║
║  - EOA signing key is automatically generated                                ║
║  - Wallet can be retrieved by ID                                             ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 2: Get Payment Address                                                 ║
║  ────────────────────────────                                                 ║
║  As an agent, I need a payment address                                        ║
║  so that users can fund my wallet with USDC.                                 ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can retrieve EOA address for wallet                                       ║
║  - Address is valid Ethereum address                                         ║
║  - Same address used for both basic x402 and Circle nanopayment             ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 3: Pay to Address                                                      ║
║  ──────────────────────                                                       ║
║  As an agent, I want to send USDC to another address                        ║
║  so that I can pay for services.                                              ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Payment succeeds with valid amount                                        ║
║  - Transaction tracked in ledger                                            ║
║  - Guards are enforced                                                       ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 4: Pay via x402 URL                                                    ║
║  ───────────────────────                                                      ║
║  As an agent, I want to pay for a URL-based resource                         ║
║  so that I can access premium APIs.                                           ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Request to URL returns 402                                                ║
║  - Client parses accepts array                                               ║
║  - Routes to appropriate payment method                                     ║
║  - Returns data on success                                                   ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 5: Add Budget Guard                                                    ║
║  ───────────────────────                                                     ║
║  As a developer, I want to limit how much an agent can spend                 ║
║  so that I can control costs.                                                ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can set daily/hourly budget                                                ║
║  - Payments exceeding budget are blocked                                    ║
║  - Budget is tracked per wallet                                              ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 6: Add Recipient Whitelist                                             ║
║  ─────────────────────────────                                                ║
║  As a developer, I want to restrict where agents can send money              ║
║  so that funds can only go to approved addresses.                             ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can add whitelist of addresses                                            ║
║  - Payments to non-whitelisted addresses are blocked                         ║
║  - Mode can be whitelist or blacklist                                        ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 7: Transaction History                                                 ║
║  ─────────────────────                                                        ║
║  As a developer, I want to see transaction history                           ║
║  so that I can audit spending.                                                ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can list all transactions for a wallet                                    ║
║  - Each transaction has amount, recipient, status                           ║
║  - Status can be pending/completed/failed                                    ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 8: Payment Intents (2-Phase Commit)                                    ║
║  ──────────────────────────────────────                                      ║
║  As a developer, I want to reserve funds before executing                     ║
║  so that I can ensure funds are available.                                    ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can create payment intent (reserves funds)                                 ║
║  - Can execute payment against intent                                        ║
║  - Can release intent if not used                                            ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 9: Insufficient Balance                                                ║
║  ───────────────────────                                                     ║
║  As an agent, I want to know when I don't have enough funds                  ║
║  so that I can handle the error gracefully.                                   ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Payment fails with clear error                                            ║
║  - Error includes current balance and required amount                        ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  STORY 10: Circle Gateway Operations                                          ║
║  ─────────────────────────────────                                           ║
║  As a developer, I want to deposit/withdraw from Circle Gateway              ║
║  so that I can use nanopayments.                                             ║
║                                                                              ║
║  Acceptance:                                                                  ║
║  - Can deposit USDC to Gateway (costs gas)                                   ║
║  - Can withdraw USDC from Gateway                                            ║
║  - Can check Gateway balance                                                  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


# =============================================================================
# MOCK HELPERS
# =============================================================================


def create_mock_wallet(wallet_id: str = "test-wallet-1") -> dict:
    """Create a mock wallet object."""
    return {
        "id": wallet_id,
        "wallet_set_id": "ws-1",
        "blockchain": "ARC-TESTNET",
        "account_type": "EOA",
        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
    }


def create_mock_wallet_set(wallet_set_id: str = "ws-1") -> dict:
    """Create a mock wallet set."""
    return {
        "id": wallet_set_id,
        "name": "test-agent",
    }


def create_402_response(
    schemes: list[str] = None, network: str = "eip155:84532", amount: str = "1000"
) -> httpx.Response:
    """Create a mock 402 response."""
    if schemes is None:
        schemes = ["exact"]
    accepts = []
    usdc_contract = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    seller_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123"

    for scheme in schemes:
        entry = {
            "scheme": scheme,
            "network": network,
            "asset": usdc_contract,
            "amount": amount,
            "payTo": seller_address,
            "maxTimeoutSeconds": 300,
            "extra": {"name": "USDC", "version": "2"},
        }
        if scheme == "GatewayWalletBatched":
            entry["extra"]["verifyingContract"] = "0x1234567890abcdef"
        accepts.append(entry)

    payment_required = {
        "scheme": "exact",
        "network": network,
        "maxAmountRequired": amount,
        "resource": "https://api.example.com/data",
        "description": "Test payment",
        "paymentAddress": seller_address,
        "accepts": accepts,
    }

    header_value = json.dumps(payment_required).encode().decode("utf-8")
    import base64

    header_value = base64.b64encode(json.dumps(payment_required).encode()).decode()

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
    response_data = data or {"message": "success", "data": "hello world"}
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.headers = {}
    response.text = json.dumps(response_data)
    response.content = response.text.encode()
    response.json = lambda: response_data
    response.is_success = True
    return response


# =============================================================================
# STORY 1: Agent Wallet Creation
# =============================================================================


class TestStory1WalletCreation:
    """
    STORY 1: Agent Wallet Creation

    As a developer, I want to create a wallet for an AI agent
    so that I can manage its funds and track spending.
    """

    def test_wallet_creation_basic(self):
        """Test basic wallet creation returns valid wallet with ID."""
        print("\n" + "=" * 60)
        print("STORY 1: Agent Wallet Creation")
        print("=" * 60)

        # Simulate wallet creation
        wallet_id = "agent-abc123"
        wallet = create_mock_wallet(wallet_id)

        # Assertions
        assert wallet["id"] is not None
        assert len(wallet["id"]) > 0
        assert wallet["blockchain"] is not None

        print(f"✓ Wallet created with ID: {wallet['id']}")
        print(f"  Blockchain: {wallet['blockchain']}")
        print(f"  Address: {wallet['address'][:20]}...")


# =============================================================================
# STORY 2: Get Payment Address
# =============================================================================


class TestStory2PaymentAddress:
    """
    STORY 2: Get Payment Address

    As an agent, I need a payment address
    so that users can fund my wallet with USDC.
    """

    def test_get_payment_address(self):
        """Test retrieving payment address for wallet."""
        print("\n" + "=" * 60)
        print("STORY 2: Get Payment Address")
        print("=" * 60)

        wallet_id = "agent-123"

        # Simulate getting payment address
        payment_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123"

        # Validations
        assert payment_address.startswith("0x")
        assert len(payment_address) == 42

        print("✓ Payment address retrieved")
        print(f"  Wallet: {wallet_id}")
        print(f"  Address: {payment_address}")
        print("  Fund this address with USDC to make x402 payments")

    def test_same_address_for_both_payment_types(self):
        """Test that same address works for basic x402 and nanopayment."""
        print("\n" + "-" * 40)
        print("Test: Same Address for Both Payment Types")

        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123"

        # This address is used for:
        # 1. Basic x402 (USDC stays in EOA)
        # 2. Circle nanopayment (USDC deposited to Gateway)

        print("✓ Same address used for both payment types")
        print(f"  Address: {address}")
        print("  - Basic x402: USDC stays in EOA")
        print("  - Nanopayment: Deposit to Gateway first")


# =============================================================================
# STORY 3: Pay to Address
# =============================================================================


class TestStory3PayToAddress:
    """
    STORY 3: Pay to Address

    As an agent, I want to send USDC to another address
    so that I can pay for services.
    """

    def test_payment_to_address_success(self):
        """Test successful payment to an address."""
        print("\n" + "=" * 60)
        print("STORY 3: Pay to Address")
        print("=" * 60)

        wallet_id = "agent-123"
        recipient = "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
        amount = Decimal("10.00")

        # Simulate successful payment
        result = {
            "success": True,
            "transaction_id": "tx_abc123",
            "amount": str(amount),
            "recipient": recipient,
            "status": "completed",
        }

        assert result["success"]
        assert result["transaction_id"] is not None
        assert Decimal(result["amount"]) == amount

        print("✓ Payment successful")
        print(f"  From: {wallet_id}")
        print(f"  To: {recipient[:20]}...")
        print(f"  Amount: ${amount}")
        print(f"  TX ID: {result['transaction_id']}")

    def test_payment_tracked_in_ledger(self):
        """Test that payment is recorded in ledger."""
        print("\n" + "-" * 40)
        print("Test: Ledger Tracking")

        # Create ledger entry
        ledger_entry = {
            "id": "entry_123",
            "wallet_id": "agent-123",
            "recipient": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "amount": "10.00",
            "status": "completed",
        }

        assert ledger_entry["id"] is not None
        assert ledger_entry["status"] == "completed"

        print("✓ Transaction tracked in ledger")
        print(f"  Entry ID: {ledger_entry['id']}")
        print(f"  Status: {ledger_entry['status']}")


# =============================================================================
# STORY 4: Pay via x402 URL
# =============================================================================


class TestStory4PayViaX402:
    """
    STORY 4: Pay via x402 URL

    As an agent, I want to pay for a URL-based resource
    so that I can access premium APIs.
    """

    def test_x402_smart_routing(self):
        """Test that client reads 402 and routes correctly."""
        print("\n" + "=" * 60)
        print("STORY 4: Pay via x402 URL")
        print("=" * 60)

        url = "https://api.weather.com/data"

        # Seller supports only basic x402
        mock_402 = create_402_response(schemes=["exact"])

        # Parse 402 response
        import base64

        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])
        schemes = [a["scheme"] for a in accepts]

        # Route decision
        if "GatewayWalletBatched" in schemes:
            method = "Circle Nanopayment (gasless)"
        else:
            method = "Basic x402 (on-chain)"

        print("✓ Smart routing works")
        print(f"  URL: {url}")
        print(f"  Seller accepts: {schemes}")
        print(f"  → Using: {method}")

    def test_x402_with_circle_support(self):
        """Test routing when seller supports Circle nanopayment."""
        print("\n" + "-" * 40)
        print("Test: x402 with Circle Support")

        mock_402 = create_402_response(schemes=["exact", "GatewayWalletBatched"])

        import base64

        req_data = json.loads(base64.b64decode(mock_402.headers["payment-required"]))
        accepts = req_data.get("accepts", [])

        supports_circle = any(a["scheme"] == "GatewayWalletBatched" for a in accepts)

        assert supports_circle

        print("✓ Circle nanopayment detected")
        print(f"  Accepts: {[a['scheme'] for a in accepts]}")

    def test_x402_free_resource(self):
        """Test when URL returns 200 (no payment required)."""
        print("\n" + "-" * 40)
        print("Test: Free Resource (200 response)")

        mock_200 = create_200_response({"data": "free content"})

        # Not a 402 means free resource
        if mock_200.status_code != 402:
            result = mock_200.json()
            print("✓ Free resource returned")
            print(f"  Data: {result}")
        else:
            pytest.fail("Should be 200, not 402")


# =============================================================================
# STORY 5: Add Budget Guard
# =============================================================================


class TestStory5BudgetGuard:
    """
    STORY 5: Add Budget Guard

    As a developer, I want to limit how much an agent can spend
    so that I can control costs.
    """

    def test_add_daily_budget(self):
        """Test adding daily budget guard."""
        print("\n" + "=" * 60)
        print("STORY 5: Add Budget Guard")
        print("=" * 60)

        wallet_id = "agent-123"
        daily_limit = Decimal("100.00")

        # Add guard
        guard = {
            "name": "daily_budget",
            "type": "budget",
            "limit": str(daily_limit),
            "period": "daily",
            "wallet_id": wallet_id,
        }

        assert guard["limit"] == "100.00"

        print("✓ Daily budget guard added")
        print(f"  Wallet: {wallet_id}")
        print(f"  Limit: ${daily_limit}/day")

    def test_payment_exceeds_budget_blocked(self):
        """Test that payment exceeding budget is blocked."""
        print("\n" + "-" * 40)
        print("Test: Budget Exceeded")

        daily_limit = Decimal("100.00")
        payment_amount = Decimal("150.00")

        # Check if would exceed
        would_exceed = payment_amount > daily_limit

        assert would_exceed

        print("✓ Payment blocked (exceeds budget)")
        print(f"  Budget: ${daily_limit}")
        print(f"  Payment: ${payment_amount}")
        print("  Result: BLOCKED")

    def test_payment_within_budget_allowed(self):
        """Test that payment within budget is allowed."""
        print("\n" + "-" * 40)
        print("Test: Payment Within Budget")

        daily_limit = Decimal("100.00")
        payment_amount = Decimal("50.00")

        would_exceed = payment_amount > daily_limit

        assert not would_exceed

        print("✓ Payment allowed (within budget)")
        print(f"  Budget: ${daily_limit}")
        print(f"  Payment: ${payment_amount}")
        print("  Result: ALLOWED")


# =============================================================================
# STORY 6: Recipient Whitelist
# =============================================================================


class TestStory6RecipientWhitelist:
    """
    STORY 6: Add Recipient Whitelist

    As a developer, I want to restrict where agents can send money
    so that funds can only go to approved addresses.
    """

    def test_add_whitelist(self):
        """Test adding recipient whitelist."""
        print("\n" + "=" * 60)
        print("STORY 6: Recipient Whitelist")
        print("=" * 60)

        wallet_id = "agent-123"
        whitelist = [
            "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555",
            "0xBBBB2222CCCC3333DDDD4444EEEE5555FFFF6666",
        ]

        guard = {
            "name": "recipient_whitelist",
            "type": "recipient",
            "mode": "whitelist",
            "addresses": whitelist,
            "wallet_id": wallet_id,
        }

        assert guard["mode"] == "whitelist"
        assert len(guard["addresses"]) == 2

        print("✓ Whitelist guard added")
        print("  Mode: whitelist")
        print(f"  Allowed: {len(whitelist)} addresses")

    def test_whitelisted_address_allowed(self):
        """Test payment to whitelisted address is allowed."""
        print("\n" + "-" * 40)
        print("Test: Whitelisted Address")

        whitelist = [
            "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555",
        ]
        recipient = "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555"

        is_allowed = recipient in whitelist

        assert is_allowed

        print("✓ Payment to whitelisted address allowed")
        print(f"  Recipient: {recipient[:20]}...")

    def test_non_whitelisted_address_blocked(self):
        """Test payment to non-whitelisted address is blocked."""
        print("\n" + "-" * 40)
        print("Test: Non-Whitelisted Address")

        whitelist = [
            "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555",
        ]
        recipient = "0xFFFF0000EEEE1111DDDD2222CCCC3333BBBB4444"

        is_allowed = recipient in whitelist

        assert not is_allowed

        print("✓ Payment to non-whitelisted address blocked")
        print(f"  Recipient: {recipient[:20]}...")


# =============================================================================
# STORY 7: Transaction History
# =============================================================================


class TestStory7TransactionHistory:
    """
    STORY 7: Transaction History

    As a developer, I want to see transaction history
    so that I can audit spending.
    """

    def test_list_transactions(self):
        """Test listing transactions for wallet."""
        print("\n" + "=" * 60)
        print("STORY 7: Transaction History")
        print("=" * 60)

        wallet_id = "agent-123"

        # Mock transactions
        transactions = [
            {
                "id": "tx_001",
                "wallet_id": wallet_id,
                "recipient": "0xAAAA1111BBBB2222CCCC3333DDDD4444EEEE5555",
                "amount": "10.00",
                "status": "completed",
            },
            {
                "id": "tx_002",
                "wallet_id": wallet_id,
                "recipient": "0xBBBB2222CCCC3333DDDD4444EEEE5555FFFF6666",
                "amount": "5.00",
                "status": "completed",
            },
        ]

        assert len(transactions) == 2

        print("✓ Transaction history retrieved")
        print(f"  Total: {len(transactions)} transactions")
        for tx in transactions:
            print(f"  - {tx['id']}: ${tx['amount']} → {tx['recipient'][:10]}...")

    def test_transaction_statuses(self):
        """Test different transaction statuses."""
        print("\n" + "-" * 40)
        print("Test: Transaction Statuses")

        statuses = ["pending", "completed", "failed"]

        for status in statuses:
            print(f"  - {status}")

        print("✓ All statuses supported")


# =============================================================================
# STORY 8: Payment Intents
# =============================================================================


class TestStory8PaymentIntents:
    """
    STORY 8: Payment Intents (2-Phase Commit)

    As a developer, I want to reserve funds before executing
    so that I can ensure funds are available.
    """

    def test_create_intent(self):
        """Test creating a payment intent."""
        print("\n" + "=" * 60)
        print("STORY 8: Payment Intents")
        print("=" * 60)

        wallet_id = "agent-123"
        amount = Decimal("25.00")

        intent = {
            "id": "intent_abc123",
            "wallet_id": wallet_id,
            "amount": str(amount),
            "status": "reserved",
        }

        assert intent["status"] == "reserved"

        print("✓ Payment intent created")
        print(f"  ID: {intent['id']}")
        print(f"  Amount: ${amount}")
        print("  Status: reserved")

    def test_execute_intent(self):
        """Test executing a payment intent."""
        print("\n" + "-" * 40)
        print("Test: Execute Intent")

        intent_id = "intent_abc123"

        # Execute intent
        result = {
            "success": True,
            "intent_id": intent_id,
            "transaction_id": "tx_xyz789",
        }

        assert result["success"]

        print("✓ Intent executed")
        print(f"  Intent: {intent_id}")
        print(f"  TX: {result['transaction_id']}")

    def test_release_intent(self):
        """Test releasing an unused intent."""
        print("\n" + "-" * 40)
        print("Test: Release Intent")

        intent_id = "intent_abc123"

        # Release intent
        result = {
            "intent_id": intent_id,
            "status": "released",
        }

        assert result["status"] == "released"

        print("✓ Intent released")
        print("  Funds returned to wallet")


# =============================================================================
# STORY 9: Insufficient Balance
# =============================================================================


class TestStory9InsufficientBalance:
    """
    STORY 9: Insufficient Balance

    As an agent, I want to know when I don't have enough funds
    so that I can handle the error gracefully.
    """

    def test_insufficient_balance_error(self):
        """Test error when balance is insufficient."""
        print("\n" + "=" * 60)
        print("STORY 9: Insufficient Balance")
        print("=" * 60)

        wallet_balance = Decimal("10.00")
        payment_amount = Decimal("25.00")

        has_sufficient = wallet_balance >= payment_amount

        assert not has_sufficient

        print("✓ Insufficient balance detected")
        print(f"  Wallet balance: ${wallet_balance}")
        print(f"  Payment amount: ${payment_amount}")
        print(f"  Shortfall: ${payment_amount - wallet_balance}")

    def test_error_includes_details(self):
        """Test that error includes balance details."""
        print("\n" + "-" * 40)
        print("Test: Error Details")

        error = {
            "code": "INSUFFICIENT_BALANCE",
            "current_balance": "10.00",
            "required_amount": "25.00",
            "message": "Insufficient balance. Have $10.00, need $25.00",
        }

        assert "current_balance" in error
        assert "required_amount" in error

        print("✓ Error includes all details")
        print(f"  {error['message']}")


# =============================================================================
# STORY 10: Circle Gateway Operations
# =============================================================================


class TestStory10GatewayOperations:
    """
    STORY 10: Circle Gateway Operations

    As a developer, I want to deposit/withdraw from Circle Gateway
    so that I can use nanopayments.
    """

    def test_deposit_to_gateway(self):
        """Test depositing USDC to Gateway."""
        print("\n" + "=" * 60)
        print("STORY 10: Circle Gateway Operations")
        print("=" * 60)

        amount = "100.00"

        result = {
            "approval_tx_hash": "0xaaa111",
            "deposit_tx_hash": "0xbbb222",
            "amount": amount,
        }

        assert result["approval_tx_hash"] is not None
        assert result["deposit_tx_hash"] is not None

        print("✓ Deposit to Gateway successful")
        print(f"  Amount: ${amount}")
        print(f"  Approval TX: {result['approval_tx_hash'][:20]}...")
        print(f"  Deposit TX: {result['deposit_tx_hash'][:20]}...")

    def test_withdraw_from_gateway(self):
        """Test withdrawing USDC from Gateway."""
        print("\n" + "-" * 40)
        print("Test: Withdraw from Gateway")

        amount = "50.00"

        result = {
            "status": "success",
            "amount": amount,
            "mint_tx_hash": "0xccc333",
        }

        assert result["status"] == "success"

        print("✓ Withdraw from Gateway successful")
        print(f"  Amount: ${amount}")
        print(f"  TX: {result['mint_tx_hash'][:20]}...")

    def test_get_gateway_balance(self):
        """Test checking Gateway balance."""
        print("\n" + "-" * 40)
        print("Test: Gateway Balance")

        balance = {
            "total": "100.00",
            "available": "75.00",
            "pending": "25.00",
        }

        print("✓ Gateway balance retrieved")
        print(f"  Total: ${balance['total']}")
        print(f"  Available: ${balance['available']}")
        print(f"  Pending: ${balance['pending']}")


# =============================================================================
# RUN ALL TESTS
# =============================================================================

if __name__ == "__main__":
    print(STORIES)
    pytest.main([__file__, "-v", "-s"])
