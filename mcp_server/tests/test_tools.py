from unittest.mock import AsyncMock, patch

import pytest
from app.mcp.fastmcp_server import (
    check_balance,
    create_agent_wallet,
    create_payment_intent,
    detect_payment_method,
    pay,
)


@pytest.fixture
def mock_client():
    with patch("app.mcp.fastmcp_server.OmniclawPaymentClient.get_instance") as mock_get:
        client = AsyncMock()
        mock_get.return_value = client
        yield client


@pytest.mark.asyncio
async def test_create_agent_wallet_tool(mock_client):
    mock_client.create_agent_wallet.return_value = {
        "wallet_set": {"id": "set-1"},
        "wallet": {"id": "wallet-1"},
    }

    result = await create_agent_wallet(agent_name="agent-alpha")

    assert result["status"] == "success"
    assert result["wallet"]["id"] == "wallet-1"
    mock_client.create_agent_wallet.assert_called_once()


@pytest.mark.asyncio
async def test_check_balance_tool(mock_client):
    mock_client.get_wallet_usdc_balance.return_value = {
        "wallet_id": "wallet-1",
        "currency": "USDC",
        "usdc_balance": "55.2",
    }

    result = await check_balance(wallet_id="wallet-1")

    assert result["status"] == "success"
    assert result["usdc_balance"] == "55.2"


@pytest.mark.asyncio
async def test_pay_tool(mock_client):
    mock_client.execute_payment.return_value = {
        "success": True,
        "status": "completed",
        "transaction_id": "tx-123",
    }

    result = await pay(wallet_id="wallet-1", recipient="0xabc", amount="10")

    assert result["status"] == "success"
    assert result["payment"]["transaction_id"] == "tx-123"


@pytest.mark.asyncio
async def test_create_payment_intent_tool(mock_client):
    mock_client.create_payment_intent.return_value = {
        "id": "intent-1",
        "status": "requires_confirmation",
        "amount": "10",
    }

    result = await create_payment_intent(
        wallet_id="wallet-1",
        recipient="0xabc",
        amount="10",
        purpose="invoice",
    )

    assert result["status"] == "success"
    assert result["intent"]["id"] == "intent-1"


@pytest.mark.asyncio
async def test_detect_payment_method_tool(mock_client):
    mock_client.detect_method.return_value = {
        "recipient": "0xabc",
        "payment_method": "transfer",
    }

    result = await detect_payment_method(recipient="0xabc")

    assert result["status"] == "success"
    assert result["payment_method"] == "transfer"
