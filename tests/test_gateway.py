"""
Tests for GatewayAdapter (Cross-Chain CCTP).

Tests the adapter's interface, routing logic, simulate(), and error handling
with mocked Circle API (no real blockchain calls).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omniclaw.core.types import (
    Network,
    PaymentMethod,
    PaymentStatus,
)
from omniclaw.protocols.gateway import GatewayAdapter


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.network = Network.ETH_SEPOLIA
    return cfg


@pytest.fixture
def wallet_service():
    ws = MagicMock()
    ws.get_usdc_balance_amount.return_value = Decimal("100.00")
    ws.list_wallets.return_value = []
    return ws


@pytest.fixture
def adapter(config, wallet_service):
    return GatewayAdapter(config, wallet_service)


class TestGatewaySupports:
    """Test routing detection."""

    def test_supports_when_destination_chain_provided(self, adapter):
        assert (
            adapter.supports(
                "0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
                destination_chain=Network.ARB_SEPOLIA,
            )
            is True
        )

    def test_does_not_support_invalid_recipient(self, adapter):
        assert adapter.supports("0xabc", destination_chain=Network.ARB_SEPOLIA) is False

    def test_does_not_support_without_destination_chain(self, adapter):
        assert adapter.supports("0xabc") is False

    def test_method_is_crosschain(self, adapter):
        assert adapter.method == PaymentMethod.CROSSCHAIN

    def test_priority(self, adapter):
        assert adapter.get_priority() == 30


class TestGatewayExecute:
    """Test execute() error paths."""

    @pytest.mark.asyncio
    async def test_missing_destination_chain(self, adapter):
        """Execute without destination_chain returns failure."""
        result = await adapter.execute(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("10.00"),
        )
        assert result.success is False
        assert "destination_chain" in result.error

    @pytest.mark.asyncio
    async def test_same_chain_transfer_success(self, adapter, wallet_service):
        """Same-chain transfers delegate to wallet_service.transfer()."""
        mock_tx = MagicMock()
        mock_tx.id = "tx-123"
        mock_tx.tx_hash = "0xhash"
        wallet_service.transfer = AsyncMock(return_value=mock_tx)

        result = await adapter.execute(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("10.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
        )
        assert result.success is False
        assert result.status == PaymentStatus.PENDING_SETTLEMENT
        assert result.metadata["same_chain"] is True
        wallet_service.transfer.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_chain_derives_deterministic_idempotency_key(self, adapter, wallet_service):
        """Missing idempotency_key should be deterministic for same request."""
        mock_tx = MagicMock()
        mock_tx.id = "tx-123"
        mock_tx.tx_hash = "0xhash"
        wallet_service.transfer = AsyncMock(return_value=mock_tx)

        await adapter.execute(
            wallet_id="w1",
            recipient="0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
            amount=Decimal("10.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
            purpose="invoice-1",
        )
        first_key = wallet_service.transfer.await_args.kwargs["idempotency_key"]

        await adapter.execute(
            wallet_id="w1",
            recipient="0x742d35Cc6634C0532925a3b844Bc9e7595f1E123",
            amount=Decimal("10.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
            purpose="invoice-1",
        )
        second_key = wallet_service.transfer.await_args.kwargs["idempotency_key"]

        assert first_key == second_key

    @pytest.mark.asyncio
    async def test_same_chain_transfer_failure(self, adapter, wallet_service):
        """Same-chain transfer exception returns failure result."""
        wallet_service.transfer.side_effect = Exception("insufficient balance")

        result = await adapter.execute(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("999.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
        )
        assert result.success is False
        assert "Same-chain transfer failed" in result.error

    @pytest.mark.asyncio
    async def test_cross_chain_cctp_unsupported_source(self, adapter):
        """CCTP with unsupported source network fails gracefully."""
        with patch("omniclaw.protocols.gateway.GatewayAdapter._execute_cctp_transfer") as mock_cctp:
            mock_cctp.side_effect = Exception("CCTP not configured")

            result = await adapter.execute(
                wallet_id="w1",
                recipient="0xabc",
                amount=Decimal("10.00"),
                source_network=Network.ETH_SEPOLIA,
                destination_chain=Network.ARB_SEPOLIA,
            )
            assert result.success is False
            assert "Cross-chain transfer failed" in result.error


class TestGatewaySimulate:
    """Test simulate() for pre-flight checks."""

    @pytest.mark.asyncio
    async def test_simulate_missing_destination(self, adapter):
        """Simulate without destination_chain reports failure."""
        result = await adapter.simulate(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("10.00"),
        )
        assert result["would_succeed"] is False
        assert "destination_chain" in result["reason"]

    @pytest.mark.asyncio
    async def test_simulate_same_chain_sufficient_balance(self, adapter, wallet_service):
        """Same-chain simulate with sufficient balance succeeds."""
        result = await adapter.simulate(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("50.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
        )
        assert result["would_succeed"] is True
        assert result["is_same_chain"] is True

    @pytest.mark.asyncio
    async def test_simulate_same_chain_insufficient_balance(self, adapter, wallet_service):
        """Same-chain simulate with insufficient balance fails."""
        result = await adapter.simulate(
            wallet_id="w1",
            recipient="0xabc",
            amount=Decimal("200.00"),
            source_network=Network.ETH_SEPOLIA,
            destination_chain=Network.ETH_SEPOLIA,
        )
        assert result["would_succeed"] is False
        assert "Insufficient" in result["reason"]

    @pytest.mark.asyncio
    async def test_simulate_cross_chain_supported(self, adapter):
        """Cross-chain simulate with supported networks succeeds."""
        with patch("omniclaw.core.cctp_constants.is_cctp_supported", return_value=True):
            result = await adapter.simulate(
                wallet_id="w1",
                recipient="0xabc",
                amount=Decimal("10.00"),
                source_network=Network.ETH_SEPOLIA,
                destination_chain=Network.ARB_SEPOLIA,
            )
            assert result["would_succeed"] is True
            assert result["is_same_chain"] is False


class TestGetExecutorWallet:
    """Test executor wallet lookup for agent-side minting."""

    @pytest.mark.asyncio
    async def test_no_wallets_returns_none(self, adapter, wallet_service):
        """Returns None when no wallets exist on target network."""
        wallet_service.list_wallets.return_value = []
        result = await adapter._get_executor_wallet(Network.ARB_SEPOLIA)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_live_wallet(self, adapter, wallet_service):
        """Returns the first LIVE wallet on the target network."""
        mock_wallet = MagicMock()
        mock_wallet.id = "w-arb-1"
        mock_wallet.state = "LIVE"
        wallet_service.list_wallets.return_value = [mock_wallet]

        result = await adapter._get_executor_wallet(Network.ARB_SEPOLIA)
        assert result.id == "w-arb-1"

    @pytest.mark.asyncio
    async def test_skips_non_live_wallets(self, adapter, wallet_service):
        """Filters out non-LIVE wallets."""
        frozen = MagicMock()
        frozen.state = "FROZEN"
        live = MagicMock()
        live.id = "w-live"
        live.state = "LIVE"
        wallet_service.list_wallets.return_value = [frozen, live]

        result = await adapter._get_executor_wallet(Network.ARB_SEPOLIA)
        assert result.id == "w-live"

    @pytest.mark.asyncio
    async def test_handles_list_error(self, adapter, wallet_service):
        """Returns None on wallet listing error."""
        wallet_service.list_wallets.side_effect = Exception("API error")
        result = await adapter._get_executor_wallet(Network.ARB_SEPOLIA)
        assert result is None


class TestCCTPFeeResolution:
    """Test Iris fee conversion from bps to token units."""

    @pytest.mark.asyncio
    async def test_resolve_cctp_max_fee_converts_bps_to_units(self, adapter):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [{"finalityThreshold": 1000, "minimumFee": 13}]

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *args, **kwargs):
                return mock_response

        with patch("omniclaw.protocols.gateway.httpx.AsyncClient", return_value=_Client()):
            fee = await adapter._resolve_cctp_max_fee(
                source_network=Network.ETH_SEPOLIA,
                source_domain=0,
                dest_domain=3,
                finality_threshold=1000,
                amount_units=1_000_000,  # 1 USDC
                fallback_fee=0,
            )

        assert fee == 1300  # 13 bps of 1,000,000

    @pytest.mark.asyncio
    async def test_resolve_cctp_max_fee_respects_fallback_floor(self, adapter):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [{"finalityThreshold": 1000, "minimumFee": 1}]

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *args, **kwargs):
                return mock_response

        with patch("omniclaw.protocols.gateway.httpx.AsyncClient", return_value=_Client()):
            fee = await adapter._resolve_cctp_max_fee(
                source_network=Network.ETH_SEPOLIA,
                source_domain=0,
                dest_domain=3,
                finality_threshold=1000,
                amount_units=100_000,  # 0.1 USDC
                fallback_fee=200,  # higher than computed 10
            )

        assert fee == 200
