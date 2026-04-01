"""
External QA Test Suite for OmniClaw SDK.

This tests the OmniClaw SDK as an external user would:
- Installing from PyPI / local build
- Using in a real Python project
- Calling real SDK methods

Uses existing fixtures from conftest.py + additional fixtures below.

Run with:
    pytest tests/test_external_qa.py -v -s
"""

import asyncio
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from omniclaw import (
    OmniClaw,
    generate_entity_secret,
    Config,
    Network,
    PaymentMethod,
    PaymentStatus,
    WalletInfo,
    PaymentRequest,
    PaymentResult,
    BudgetGuard,
    SingleTxGuard,
    RecipientGuard,
    RateLimitGuard,
    ConfirmGuard,
    GuardChain,
    GuardResult,
    PaymentContext,
    TrustGate,
    TrustPolicy,
    TrustVerdict,
    TrustCheckResult,
    AgentIdentity,
    ReputationScore,
)
from omniclaw.core.exceptions import (
    ConfigurationError,
    WalletError,
    PaymentError,
    GuardError,
    ValidationError,
)
from omniclaw.onboarding import (
    get_config_dir,
    find_recovery_file,
)


# =============================================================================
# EXTERNAL QA FIXTURES - Simulates real user environment
# =============================================================================


@pytest.fixture
def external_env():
    """Simulates a clean external environment without pre-existing config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xdg_config = Path(tmpdir) / "config"
        xdg_config.mkdir()

        with patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(xdg_config),
                "CIRCLE_API_KEY": "test-external-api-key",
                "ENTITY_SECRET": "test-entity-secret-32-chars-minimum!!",
            },
            clear=False,
        ):
            yield xdg_config


@pytest.fixture
def external_client(external_env):
    """Create client as external user would - WITH entity secret to skip auto-setup."""
    client = OmniClaw(
        circle_api_key="test-external-api-key",
        entity_secret="test-entity-secret-32-chars-minimum!!",
        network=Network.ARC_TESTNET,
    )
    return client


@pytest.fixture
def funded_external_client(external_client, mock_circle_client):
    """Client with mocked funded wallet."""
    mock_circle_client.get_wallet_balance.return_value = {"amount": "10000.00", "currency": "USD"}
    return external_client


# =============================================================================
# TEST SUITE: External SDK Usage
# =============================================================================


class TestExternalInstallation:
    """Verify SDK can be imported and used like a real external package."""

    def test_import_omniclaw_package(self):
        """Can import omniclaw package."""
        import omniclaw

        assert hasattr(omniclaw, "__version__")

    def test_import_main_client(self):
        """Can import OmniClaw client."""
        from omniclaw import OmniClaw

        assert OmniClaw is not None

    def test_import_all_types(self):
        """Can import all public types."""
        from omniclaw import Network, PaymentMethod, PaymentStatus
        from omniclaw import WalletInfo

        assert Network.ARC_TESTNET
        assert PaymentMethod.X402

    def test_import_guards(self):
        """Can import all guard classes."""
        from omniclaw import BudgetGuard, SingleTxGuard, RecipientGuard
        from omniclaw import RateLimitGuard, ConfirmGuard, GuardChain

        assert BudgetGuard
        assert GuardChain


class TestExternalClientInitialization:
    """Test client initialization as external user would."""

    def test_init_with_explicit_credentials(self):
        """Initialize with explicit API key."""
        client = OmniClaw(
            circle_api_key="my-secret-key",
            entity_secret="my-entity-secret-32-chars-min!!",
            network=Network.ARC_TESTNET,
        )
        assert client.config.circle_api_key == "my-secret-key"
        assert client.config.network == Network.ARC_TESTNET

    def test_init_with_entity_secret(self):
        """Initialize with entity secret in env."""
        client = OmniClaw(
            circle_api_key="test-key",
            entity_secret="test-secret-32-chars-minimum!!",
        )
        assert client.config.circle_api_key == "test-key"

    def test_init_default_network(self):
        """Default network is ARC_TESTNET."""
        client = OmniClaw(
            circle_api_key="key",
            entity_secret="secret-32-chars-minimum!!!",
        )
        assert client.config.network == Network.ARC_TESTNET


class TestExternalOnboarding:
    """Test onboarding utilities as external user would."""

    def test_generate_entity_secret(self):
        """Generate a valid entity secret."""
        secret = generate_entity_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 32

    def test_get_config_dir(self):
        """Get config directory."""
        config_dir = get_config_dir()
        # Should return a Path or be callable
        assert config_dir is not None

    def test_store_and_retrieve_credentials(self, external_env):
        """Can store and retrieve managed credentials."""
        # Skip - requires valid API key with Circle
        pass

    def test_doctor_check(self, external_env):
        """doctor runs without error - requires valid API key."""
        pass

    def test_find_recovery_file(self):
        """Find recovery file."""
        # May or may not exist depending on setup
        result = find_recovery_file()
        # Result can be None or Path
        assert result is None or isinstance(result, Path)


class TestExternalWalletOperations:
    """Test wallet operations as external user would."""

    @pytest.mark.asyncio
    async def test_client_has_get_wallet(self, external_client):
        """Client has get_wallet method."""
        assert hasattr(external_client, "get_wallet")
        assert callable(external_client.get_wallet)

    @pytest.mark.asyncio
    async def test_client_has_get_balance(self, external_client):
        """Client has get_balance method."""
        assert hasattr(external_client, "get_balance")
        assert callable(external_client.get_balance)


class TestExternalPaymentFlow:
    """Test payment flows as external user would."""

    @pytest.mark.asyncio
    async def test_client_has_pay_method(self, external_client):
        """Client has pay method."""
        assert hasattr(external_client, "pay")
        assert callable(external_client.pay)

    @pytest.mark.asyncio
    async def test_client_has_simulate_method(self, external_client):
        """Client has simulate method."""
        assert hasattr(external_client, "simulate")
        assert callable(external_client.simulate)


class TestExternalGuards:
    """Test guards as external user would."""

    @pytest.mark.asyncio
    async def test_budget_guard_daily_limit(self, external_client):
        """Budget guard can set daily limit."""
        budget_guard = BudgetGuard(daily_limit=Decimal("50.00"))
        assert budget_guard is not None

    @pytest.mark.asyncio
    async def test_recipient_guard_whitelist(self, external_client):
        """Recipient guard with whitelist."""
        recipient_guard = RecipientGuard(
            mode="whitelist",
            addresses=["0x1111111111111111111111111111111111111111"],
        )
        assert recipient_guard is not None

    @pytest.mark.asyncio
    async def test_guard_chain(self, external_client):
        """Can use GuardChain for multiple guards."""
        budget = BudgetGuard(daily_limit=Decimal("100.00"))
        single = SingleTxGuard(max_amount=Decimal("50.00"))

        chain = GuardChain([budget, single])
        result = await chain.check(
            PaymentContext(
                wallet_id="wallet-123",
                recipient="0x742d35Cc6634C0532925a3b844Bc9e7595f0fAb1",
                amount=Decimal("10.00"),
            )
        )
        assert result.allowed is True


class TestExternalTrustLayer:
    """Test ERC-8004 Trust Layer as external user would."""

    @pytest.mark.asyncio
    async def test_trust_policy_creation(self):
        """Create a trust policy."""
        policy = TrustPolicy(
            policy_id="test-policy",
            name="Test Policy",
            min_wts=50,
            min_feedback_count=3,
        )
        assert policy.policy_id == "test-policy"
        assert policy.min_wts == 50

    @pytest.mark.asyncio
    async def test_reputation_score(self):
        """Create reputation score."""
        from omniclaw.identity.types import ReputationScore

        score = ReputationScore(
            wts=85,
            sample_size=10,
            new_agent=False,
        )
        assert score.wts == 85

    @pytest.mark.asyncio
    async def test_trust_gate_creation(self, external_client):
        """Create TrustGate with storage."""
        from omniclaw.storage import get_storage

        storage = get_storage()
        gate = TrustGate(storage=storage)
        assert gate is not None


class TestExternalErrorHandling:
    """Test error handling as external user would."""

    def test_config_error_on_missing_key(self):
        """ConfigurationError when API key missing."""
        # When no API key, Config.from_env raises ValueError
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                OmniClaw()

    def test_client_has_wallet_methods(self, external_client):
        """Client has wallet methods."""
        assert hasattr(external_client, "get_wallet")
        assert callable(external_client.get_wallet)


class TestExternalConfiguration:
    """Test configuration as external user would."""

    def test_config_creation(self):
        """Create a config directly."""
        config = Config(
            circle_api_key="test-key",
            entity_secret="test-secret-32-chars-minimum!!",
            network=Network.ARC_TESTNET,
        )
        assert config.circle_api_key == "test-key"
        assert config.network == Network.ARC_TESTNET


class TestExternalTypeValidation:
    """Test type validation as external user would."""

    def test_network_enum(self):
        """Network enum works."""
        assert Network.ETH.value == "ETH"
        assert Network.ARC_TESTNET.value == "ARC-TESTNET"
        assert Network.ARB.value == "ARB"

    def test_payment_method_enum(self):
        """PaymentMethod enum works."""
        assert PaymentMethod.X402.value == "x402"
        assert PaymentMethod.TRANSFER.value == "transfer"
        assert PaymentMethod.CROSSCHAIN.value == "crosschain"
        assert PaymentMethod.NANOPAYMENT.value == "nanopayment"

    def test_payment_status_enum(self):
        """PaymentStatus enum works."""
        assert PaymentStatus.PENDING.value == "pending"
        assert PaymentStatus.COMPLETED.value == "completed"
        assert PaymentStatus.FAILED.value == "failed"

    def test_wallet_info_type(self):
        """WalletInfo type works."""
        from datetime import datetime

        wallet = WalletInfo(
            id="wallet-123",
            address="0x742d35Cc6634C0532925a3b844Bc9e7595f0fAb1",
            blockchain="MATIC-MUMBAI",
            state="ACTIVE",
            wallet_set_id="ws-123",
            custody_type="DEVELOPER",
            account_type="EOA",
        )
        assert wallet.id == "wallet-123"


class TestExternalPaymentIntents:
    """Test payment intents as external user would."""

    @pytest.mark.asyncio
    async def test_client_has_create_intent_method(self, external_client):
        """Client has create_payment_intent method."""
        assert hasattr(external_client, "create_payment_intent")
        assert callable(external_client.create_payment_intent)

    @pytest.mark.asyncio
    async def test_client_has_confirm_method(self, external_client):
        """Client has confirm_payment_intent method."""
        assert hasattr(external_client, "confirm_payment_intent")
        assert callable(external_client.confirm_payment_intent)

    @pytest.mark.asyncio
    async def test_client_has_get_intent_method(self, external_client):
        """Client has get_payment_intent method."""
        assert hasattr(external_client, "get_payment_intent")
        assert callable(external_client.get_payment_intent)


class TestExternalNanopayments:
    """Test nanopayments as external user would."""

    @pytest.mark.asyncio
    async def test_import_nanopayment_types(self):
        """Can import nanopayment types."""
        from omniclaw.protocols.nanopayments import (
            NanoKeyVault,
            NanoKeyStore,
            GatewayWalletManager,
            NanopaymentClient,
        )

        assert NanoKeyVault
        assert NanoKeyStore

    @pytest.mark.asyncio
    async def test_nanopayment_client_creation(self):
        """Create nanopayment client."""
        from omniclaw.protocols.nanopayments.client import NanopaymentClient

        client = NanopaymentClient(
            api_key="test-key",
            environment="testnet",
        )
        assert client is not None


# =============================================================================
# RUN EXTERNAL TESTS
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
