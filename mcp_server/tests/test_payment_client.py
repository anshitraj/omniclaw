from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.payments.omniclaw_client import OmniclawPaymentClient


@pytest.fixture
def mock_sdk_client():
    with patch("app.payments.omniclaw_client.OmniClaw") as sdk_cls:
        sdk_instance = MagicMock()
        sdk_cls.return_value = sdk_instance
        yield sdk_instance


@pytest.fixture
def payment_client(mock_sdk_client):
    client = OmniclawPaymentClient()
    client._client = mock_sdk_client
    return client


@pytest.mark.asyncio
async def test_get_wallet_balance(payment_client, mock_sdk_client):
    mock_sdk_client.get_balance = AsyncMock(return_value=Decimal("42.5"))

    result = await payment_client.get_wallet_usdc_balance("wallet-1")

    assert result == {
        "wallet_id": "wallet-1",
        "currency": "USDC",
        "usdc_balance": "42.5",
    }


@pytest.mark.asyncio
async def test_execute_payment(payment_client, mock_sdk_client):
    payment_result = MagicMock(
        success=True,
        transaction_id="tx-1",
        blockchain_tx="0xabc",
        amount=Decimal("12.3"),
        recipient="0xdef",
        method=MagicMock(value="transfer"),
        status=MagicMock(value="completed"),
        guards_passed=[],
        error=None,
        metadata={},
        resource_data=None,
    )
    payment_result.to_dict.return_value = {
        "success": True,
        "transaction_id": "tx-1",
        "blockchain_tx": "0xabc",
        "amount": "12.3",
        "recipient": "0xdef",
        "method": "transfer",
        "status": "completed",
        "guards_passed": [],
        "error": None,
        "metadata": {},
        "resource_data": None,
    }
    mock_sdk_client.pay = AsyncMock(return_value=payment_result)

    with patch("omniclaw.core.types.FeeLevel"), patch("omniclaw.core.types.PaymentStrategy"):
        result = await payment_client.execute_payment(
            wallet_id="wallet-1",
            recipient="0xdef",
            amount="12.3",
        )

    assert result["success"] is True
    assert result["transaction_id"] == "tx-1"


@pytest.mark.asyncio
async def test_list_guards(payment_client, mock_sdk_client):
    mock_sdk_client.guards.list_wallet_guard_names = AsyncMock(return_value=["budget", "recipient"])

    result = await payment_client.list_guards("wallet-1")

    assert result["wallet_id"] == "wallet-1"
    assert result["guards"] == ["budget", "recipient"]


@pytest.mark.asyncio
async def test_trust_policy_roundtrip(payment_client, mock_sdk_client):
    mock_sdk_client.trust = MagicMock()
    mock_sdk_client.trust.get_policy.return_value = MagicMock(policy_id="default")

    set_result = await payment_client.trust_set_policy("wallet-1", "permissive")
    get_result = await payment_client.trust_get_policy("wallet-1")

    assert set_result["wallet_id"] == "wallet-1"
    assert "policy" in get_result
