"""API routes for agent server."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from omniclaw.agent.auth import AuthenticatedAgent, TokenAuth
from omniclaw.agent.models import (
    AddressResponse,
    BalanceResponse,
    CanPayResponse,
    CreateIntentRequest,
    HealthResponse,
    IntentResponse,
    ListTransactionsResponse,
    ListWalletsResponse,
    PayRequest,
    PayResponse,
    SimulateRequest,
    SimulateResponse,
    TransactionInfo,
    WalletInfo,
    X402PayRequest,
    X402VerifyRequest,
)
from omniclaw.agent.policy import PolicyManager, WalletManager
from omniclaw.core.logging import get_logger
from omniclaw.guards.confirmations import ConfirmationStore

if TYPE_CHECKING:
    from omniclaw import OmniClaw

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agent"])


async def get_policy_manager(request: Request) -> PolicyManager:
    return request.app.state.policy_mgr


async def get_wallet_manager(request: Request) -> WalletManager:
    return request.app.state.wallet_mgr


async def get_token_auth(request: Request) -> TokenAuth:
    return request.app.state.auth


async def get_omniclaw_client(request: Request) -> OmniClaw:
    return request.app.state.client


security = HTTPBearer()


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth: TokenAuth = Depends(get_token_auth),
) -> AuthenticatedAgent:
    return await auth.authenticate(credentials)


async def require_owner(request: Request) -> None:
    """Require owner token for privileged actions."""
    expected = os.environ.get("OMNICLAW_OWNER_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="OMNICLAW_OWNER_TOKEN not configured")
    provided = request.headers.get("X-Omniclaw-Owner-Token")
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid owner token")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.get("/address", response_model=AddressResponse)
async def get_address(
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    eoa_address = client._nano_adapter.address if client._nano_adapter else None
    circle_address = await wallet_mgr.get_wallet_address(agent.wallet_id)
    address = eoa_address or circle_address

    if not address:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet_cfg = policy_mgr.get_wallet_config(agent.wallet_id)
    alias = wallet_cfg.get("alias") or agent.wallet_id.replace("pending-", "")

    return AddressResponse(
        wallet_id=agent.wallet_id,
        alias=alias,
        address=address,
        eoa_address=eoa_address,
        circle_wallet_address=circle_address,
    )


@router.get("/nano-address")
async def get_nano_address(
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """Get or create nanopayment address for this agent."""
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    try:
        # Direct private key mode - return EOA address
        if client._nano_adapter:
            nano_addr = client._nano_adapter.address
        else:
            raise HTTPException(
                status_code=500,
                detail="Nanopayments not initialized (direct key required)",
            )

        return {"address": nano_addr, "wallet_id": agent.wallet_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get nano address: {e}") from e


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    agent: AuthenticatedAgent = Depends(get_current_agent),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    if client._nano_adapter:
        gateway_balance = await client.get_gateway_balance(agent.wallet_id)
        available = gateway_balance.available_decimal
        total = gateway_balance.total_decimal
        reserved = None
    else:
        balance = await wallet_mgr.get_wallet_balance(agent.wallet_id)
        if balance is None:
            raise HTTPException(status_code=404, detail="Wallet not found")
        available = str(balance)
        total = None
        reserved = None

    return BalanceResponse(
        wallet_id=agent.wallet_id,
        available=available,
        total=total,
        reserved=reserved,
    )


@router.get("/balance-detail")
async def get_detailed_balance(
    agent: AuthenticatedAgent = Depends(get_current_agent),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """Get detailed balance including Gateway on-chain balance."""
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    eoa_address = client._nano_adapter.address if client._nano_adapter else None
    circle_address = await wallet_mgr.get_wallet_address(agent.wallet_id)
    circle_balance = await wallet_mgr.get_wallet_balance(agent.wallet_id)
    gateway_balance = (
        await client.get_gateway_balance(agent.wallet_id) if client._nano_adapter else None
    )

    return {
        "wallet_id": agent.wallet_id,
        "eoa_address": eoa_address,
        "gateway_balance": gateway_balance.available_decimal if gateway_balance else "0",
        "gateway_balance_atomic": gateway_balance.available if gateway_balance else 0,
        "gateway_total_atomic": gateway_balance.total if gateway_balance else 0,
        "circle_wallet_address": circle_address,
        "circle_wallet_balance": str(circle_balance) if circle_balance is not None else "0",
    }


@router.post("/deposit")
async def deposit_to_gateway(
    amount: str = ...,
    check_gas: bool = False,
    skip_if_insufficient_gas: bool = True,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """
    Deposit USDC to Gateway wallet from EOA.

    This moves USDC from the agent's EOA into their Gateway balance.
    Required before making/receiving nanopayments.

    Args:
        amount: Amount in USDC (e.g., "10.00")
        check_gas: Check gas balance before deposit
        skip_if_insufficient_gas: Skip if not enough gas for deposit tx
    """
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    try:
        result = await client.deposit_to_gateway(
            wallet_id=agent.wallet_id,
            amount_usdc=amount,
            check_gas=check_gas,
            skip_if_insufficient_gas=skip_if_insufficient_gas,
        )

        return {
            "success": result.deposit_tx_hash is not None,
            "amount_deposited": result.formatted_amount,
            "approval_tx_hash": result.approval_tx_hash,
            "deposit_tx_hash": result.deposit_tx_hash,
            "message": "Deposited to Gateway" if result.deposit_tx_hash else "Deposit failed",
        }
    except Exception as e:
        import traceback

        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}") from e


@router.post("/withdraw")
async def withdraw_from_gateway(
    amount: str = ...,
    destination_chain: str | None = None,
    recipient: str | None = None,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """
    Withdraw USDC from Gateway wallet via Circle API.

    Args:
        amount: Amount in USDC (e.g., "1.00")
        destination_chain: Optional CAIP-2 chain for cross-chain withdrawal
        recipient: Optional destination address (defaults to own address)
    """
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    try:
        if recipient is None:
            wallet_cfg = policy_mgr.get_wallet_config(agent.wallet_id)
            recipient = wallet_cfg.get("address")
            if not recipient:
                raise HTTPException(
                    status_code=400,
                    detail="No default withdrawal address in policy. Set wallets.<alias>.address or pass recipient.",
                )

        result = await client.withdraw_from_gateway(
            wallet_id=agent.wallet_id,
            amount_usdc=amount,
            destination_chain=destination_chain,
            recipient=recipient,
        )
        burn_tx_hash = getattr(result, "burn_tx_hash", None)
        mint_tx_hash = getattr(result, "mint_tx_hash", None)
        status = getattr(result, "status", None) or ("COMPLETED" if mint_tx_hash else "PENDING")
        return {
            "success": bool(mint_tx_hash),
            "amount_withdrawn": result.formatted_amount,
            "burn_tx_hash": burn_tx_hash,
            "mint_tx_hash": mint_tx_hash,
            "status": status,
            "message": "Withdrawal initiated",
        }
    except Exception as e:
        import traceback

        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}") from e


@router.post("/withdraw-trustless")
async def withdraw_trustless(
    request: Request,
    amount: str = ...,
    agent: AuthenticatedAgent = Depends(get_current_agent),
):
    """
    Initiate trustless withdrawal directly on-chain (~7-day delay).

    This bypasses Circle's API and withdraws directly to the agent's own address.
    """
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    try:
        import os
        from datetime import datetime, timedelta

        from omniclaw.core.types import network_to_caip2
        from omniclaw.protocols.nanopayments.client import NanopaymentClient
        from omniclaw.protocols.nanopayments.wallet import GatewayWalletManager

        private_key_str = os.environ.get("OMNICLAW_PRIVATE_KEY")
        if not private_key_str:
            raise HTTPException(status_code=500, detail="OMNICLAW_PRIVATE_KEY not configured")

        config = request.app.state.config if hasattr(request.app.state, "config") else {}
        network = config.get("nanopay_network") or network_to_caip2(
            os.environ.get("OMNICLAW_NETWORK", "ARC-TESTNET")
        )
        rpc_url = config.get("rpc_url") or os.environ.get("OMNICLAW_RPC_URL") or ""
        if not network or ":" not in network:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Invalid nanopayments network. Set OMNICLAW_NETWORK to an EVM chain "
                    "that maps to a CAIP-2 chain ID (e.g., ETH-SEPOLIA)."
                ),
            )
        if not rpc_url:
            raise HTTPException(status_code=500, detail="OMNICLAW_RPC_URL not configured")

        nanopayment_client = NanopaymentClient(
            api_key=os.environ.get("CIRCLE_API_KEY"),
        )

        manager = GatewayWalletManager(
            private_key=private_key_str,
            network=network,
            rpc_url=rpc_url,
            nanopayment_client=nanopayment_client,
        )

        delay_blocks = await manager.get_withdrawal_delay()

        delay_seconds = delay_blocks * 12
        available_after = datetime.now() + timedelta(seconds=delay_seconds)

        tx_hash = await manager.initiate_trustless_withdrawal(amount_usdc=amount)

        return {
            "success": True,
            "tx_hash": tx_hash,
            "amount": amount,
            "delay_blocks": delay_blocks,
            "available_after": available_after.isoformat(),
            "message": f"Trustless withdrawal initiated. Wait ~{delay_blocks} blocks before completing.",
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}") from e


@router.post("/withdraw-trustless/complete")
async def complete_trustless_withdrawal(
    request: Request,
    agent: AuthenticatedAgent = Depends(get_current_agent),
):
    """
    Complete a trustless withdrawal after the delay has passed.
    """
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    try:
        import os

        from omniclaw.core.types import network_to_caip2
        from omniclaw.protocols.nanopayments.client import NanopaymentClient
        from omniclaw.protocols.nanopayments.wallet import GatewayWalletManager

        private_key_str = os.environ.get("OMNICLAW_PRIVATE_KEY")
        if not private_key_str:
            raise HTTPException(status_code=500, detail="OMNICLAW_PRIVATE_KEY not configured")

        config = request.app.state.config if hasattr(request.app.state, "config") else {}
        network = config.get("nanopay_network") or network_to_caip2(
            os.environ.get("OMNICLAW_NETWORK", "ARC-TESTNET")
        )
        rpc_url = config.get("rpc_url") or os.environ.get("OMNICLAW_RPC_URL") or ""
        if not network or ":" not in network:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Invalid nanopayments network. Set OMNICLAW_NETWORK to an EVM chain "
                    "that maps to a CAIP-2 chain ID (e.g., ETH-SEPOLIA)."
                ),
            )
        if not rpc_url:
            raise HTTPException(status_code=500, detail="OMNICLAW_RPC_URL not configured")

        nanopayment_client = NanopaymentClient(
            api_key=os.environ.get("CIRCLE_API_KEY"),
        )

        manager = GatewayWalletManager(
            private_key=private_key_str,
            network=network,
            rpc_url=rpc_url,
            nanopayment_client=nanopayment_client,
        )

        current_block = manager._w3.eth.block_number
        gateway_address = await manager._resolve_gateway_address()
        usdc_address = await manager._resolve_usdc_address()
        gateway = manager._get_gateway_contract(gateway_address)
        withdrawal_block = gateway.functions.withdrawalBlock(usdc_address, manager._address).call()

        if withdrawal_block == 0:
            raise HTTPException(
                status_code=400,
                detail="No withdrawal initiated. Call /withdraw-trustless first.",
            )

        if current_block < withdrawal_block:
            blocks_remaining = withdrawal_block - current_block
            raise HTTPException(
                status_code=425,
                detail=f"Withdrawal not ready. {blocks_remaining} blocks remaining.",
            )

        tx_hash = await manager.complete_trustless_withdrawal()

        return {
            "success": True,
            "tx_hash": tx_hash,
            "message": "Trustless withdrawal completed.",
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()}") from e


@router.get("/deposit-address")
async def get_deposit_address(
    request: Request,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """
    Get the EOA address for depositing USDC from external sources.

    This is the address to send USDC to from faucet or other wallets.
    Then use /deposit to move it to Gateway, or it auto-deposits for nanopayments.
    """
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    eoa_address = client._nano_adapter.address if client._nano_adapter else None
    if not eoa_address:
        raise HTTPException(
            status_code=500,
            detail="Nanopayments not initialized (direct key required)",
        )

    config = request.app.state.config if hasattr(request.app.state, "config") else {}
    from omniclaw.core.types import network_to_caip2

    network = config.get("nanopay_network") or network_to_caip2(
        os.getenv("OMNICLAW_NETWORK", "ARC-TESTNET")
    )

    if not network:
        raise HTTPException(
            status_code=500,
            detail=(
                "Nanopayments network is not configured. Set OMNICLAW_NETWORK to an "
                "EVM chain that maps to a CAIP-2 chain ID."
            ),
        )

    return {
        "address": eoa_address,
        "network": network,
        "instructions": "Send USDC to this address, then call /deposit to move to Gateway",
    }


@router.post("/pay", response_model=PayResponse)
async def pay(
    request: PayRequest,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    if agent.wallet_id.startswith("pending-"):
        raise HTTPException(
            status_code=425,
            detail="Wallet is currently initializing. Please try again in a few seconds.",
        )

    if not policy_mgr.is_valid_recipient(request.recipient, agent.wallet_id):
        raise HTTPException(status_code=400, detail="Recipient not allowed by policy")

    amount = Decimal(request.amount)
    allowed, reason = policy_mgr.check_limits(amount, agent.wallet_id)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    try:
        result = await client.pay(
            wallet_id=agent.wallet_id,
            recipient=request.recipient,
            amount=str(amount),
            purpose=request.purpose,
            idempotency_key=request.idempotency_key,
            destination_chain=request.destination_chain,
            fee_level=request.fee_level,
            check_trust=request.check_trust,
            skip_guards=request.skip_guards,
            metadata=request.metadata,
        )
        requires_confirmation = bool(
            result.metadata.get("confirmation_required") if result.metadata else False
        )
        confirmation_id = result.metadata.get("confirmation_id") if result.metadata else None

        return PayResponse(
            success=result.success,
            transaction_id=result.transaction_id,
            blockchain_tx=result.blockchain_tx,
            amount=str(result.amount),
            recipient=result.recipient,
            status=result.status.value
            if result.status and hasattr(result.status, "value")
            else (str(result.status) if result.status else "failed"),
            method=result.method.value
            if result.method and hasattr(result.method, "value")
            else (str(result.method) if result.method else "transfer"),
            error=result.error,
            requires_confirmation=requires_confirmation,
            confirmation_id=confirmation_id,
        )
    except Exception as e:
        logger.error(f"Payment failed: {e}")
        return PayResponse(
            success=False,
            amount=request.amount,
            recipient=request.recipient,
            status="FAILED",
            method="TRANSFER",
            error=str(e),
            requires_confirmation=False,
        )


@router.post("/simulate", response_model=SimulateResponse)
async def simulate(
    request: SimulateRequest,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    if not policy_mgr.is_valid_recipient(request.recipient, agent.wallet_id):
        return SimulateResponse(
            would_succeed=False, route="TRANSFER", reason="Recipient not allowed by policy"
        )

    amount = Decimal(request.amount)
    allowed, reason = policy_mgr.check_limits(amount, agent.wallet_id)
    if not allowed:
        return SimulateResponse(would_succeed=False, route="TRANSFER", reason=reason)

    try:
        result = await client.simulate(
            wallet_id=agent.wallet_id,
            recipient=request.recipient,
            amount=str(amount),
            check_trust=request.check_trust,
            skip_guards=request.skip_guards,
        )

        return SimulateResponse(
            would_succeed=result.would_succeed,
            route=result.route.value
            if result.route and hasattr(result.route, "value")
            else str(result.route),
            reason=result.reason,
            guards_that_would_pass=result.guards_that_would_pass,
        )
    except Exception as e:
        return SimulateResponse(would_succeed=False, route="TRANSFER", reason=str(e))


@router.get("/transactions", response_model=ListTransactionsResponse)
async def list_transactions(
    limit: int = 20,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    try:
        transactions = await client.list_transactions(wallet_id=agent.wallet_id)
        transactions = transactions[:limit]

        return ListTransactionsResponse(
            transactions=[
                TransactionInfo(
                    id=tx.id,
                    wallet_id=tx.wallet_id,
                    recipient=(
                        getattr(tx, "recipient", None)
                        or getattr(tx, "destination_address", None)
                        or getattr(tx, "source_address", None)
                        or ""
                    ),
                    amount=str(
                        getattr(tx, "amount", None)
                        or (tx.amounts[0] if getattr(tx, "amounts", None) else "0")
                    ),
                    status=(
                        (tx.status.value if hasattr(tx.status, "value") else str(tx.status))
                        if getattr(tx, "status", None) is not None
                        else (
                            tx.state.value
                            if getattr(tx, "state", None) is not None and hasattr(tx.state, "value")
                            else (
                                str(tx.state)
                                if getattr(tx, "state", None) is not None
                                else "failed"
                            )
                        )
                    ),
                    tx_hash=tx.tx_hash,
                    created_at=(
                        tx.created_at.isoformat()
                        if getattr(tx, "created_at", None)
                        else (
                            tx.create_date.isoformat() if getattr(tx, "create_date", None) else None
                        )
                    ),
                )
                for tx in transactions
            ],
            total=len(transactions),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/intents", response_model=IntentResponse)
async def create_intent(
    request: CreateIntentRequest,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    if not policy_mgr.is_valid_recipient(request.recipient, agent.wallet_id):
        raise HTTPException(status_code=400, detail="Recipient not allowed by policy")

    amount = Decimal(request.amount)
    allowed, reason = policy_mgr.check_limits(amount, agent.wallet_id)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    try:
        intent = await client.create_payment_intent(
            wallet_id=agent.wallet_id,
            recipient=request.recipient,
            amount=str(amount),
            purpose=request.purpose,
            expires_in=request.expires_in,
            idempotency_key=request.idempotency_key,
            check_trust=request.check_trust,
            **(request.metadata or {}),
        )

        return IntentResponse(
            intent_id=intent.id,
            wallet_id=intent.wallet_id,
            recipient=intent.recipient,
            amount=str(intent.amount),
            status=intent.status.value
            if intent.status and hasattr(intent.status, "value")
            else (str(intent.status) if intent.status else "failed"),
            expires_at=intent.expires_at.isoformat() if intent.expires_at else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/intents/{intent_id}", response_model=IntentResponse)
async def get_intent(
    intent_id: str,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    try:
        intent = await client.get_payment_intent(intent_id)
        if not intent:
            raise HTTPException(status_code=404, detail="Intent not found")

        if intent.wallet_id != agent.wallet_id:
            raise HTTPException(status_code=403, detail="Intent belongs to different wallet")

        return IntentResponse(
            intent_id=intent.id,
            wallet_id=intent.wallet_id,
            recipient=intent.recipient,
            amount=str(intent.amount),
            status=intent.status.value
            if intent.status and hasattr(intent.status, "value")
            else (str(intent.status) if intent.status else "failed"),
            expires_at=intent.expires_at.isoformat() if intent.expires_at else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/intents/{intent_id}/confirm", response_model=PayResponse)
async def confirm_intent(
    intent_id: str,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    try:
        intent = await client.get_payment_intent(intent_id)
        if not intent:
            raise HTTPException(status_code=404, detail="Intent not found")

        if intent.wallet_id != agent.wallet_id:
            raise HTTPException(status_code=403, detail="Intent belongs to different wallet")

        result = await client.confirm_payment_intent(intent_id)

        return PayResponse(
            success=result.success,
            transaction_id=result.transaction_id,
            blockchain_tx=result.blockchain_tx,
            amount=str(result.amount),
            recipient=result.recipient,
            status=result.status.value
            if result.status and hasattr(result.status, "value")
            else (str(result.status) if result.status else "failed"),
            method=result.method.value
            if result.method and hasattr(result.method, "value")
            else (str(result.method) if result.method else "transfer"),
            error=result.error,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/intents/{intent_id}", response_model=IntentResponse)
async def cancel_intent(
    intent_id: str,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    try:
        intent = await client.get_payment_intent(intent_id)
        if not intent:
            raise HTTPException(status_code=404, detail="Intent not found")

        if intent.wallet_id != agent.wallet_id:
            raise HTTPException(status_code=403, detail="Intent belongs to different wallet")

        cancelled = await client.cancel_payment_intent(intent_id)

        return IntentResponse(
            intent_id=cancelled.id,
            wallet_id=cancelled.wallet_id,
            recipient=cancelled.recipient,
            amount=str(cancelled.amount),
            status=cancelled.status.value
            if hasattr(cancelled.status, "value")
            else str(cancelled.status),
            expires_at=cancelled.expires_at.isoformat() if cancelled.expires_at else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/confirmations/{confirmation_id}")
async def get_confirmation(
    confirmation_id: str,
    _: None = Depends(require_owner),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    store = ConfirmationStore(client._storage)
    record = await store.get(confirmation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Confirmation not found")
    return record


@router.post("/confirmations/{confirmation_id}/approve")
async def approve_confirmation(
    confirmation_id: str,
    _: None = Depends(require_owner),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    store = ConfirmationStore(client._storage)
    record = await store.approve(confirmation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Confirmation not found")
    return record


@router.post("/confirmations/{confirmation_id}/deny")
async def deny_confirmation(
    confirmation_id: str,
    _: None = Depends(require_owner),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    store = ConfirmationStore(client._storage)
    record = await store.deny(confirmation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Confirmation not found")
    return record


@router.get("/can-pay", response_model=CanPayResponse)
async def can_pay(
    recipient: str,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
):
    is_valid = policy_mgr.is_valid_recipient(recipient, agent.wallet_id)
    if is_valid:
        return CanPayResponse(can_pay=True)
    else:
        return CanPayResponse(can_pay=False, reason="Recipient not allowed by policy")


@router.get("/wallets", response_model=ListWalletsResponse)
async def list_wallets(
    agent: AuthenticatedAgent = Depends(get_current_agent),
    policy_mgr: PolicyManager = Depends(get_policy_manager),
    wallet_mgr: WalletManager = Depends(get_wallet_manager),
):
    is_pending = agent.wallet_id.startswith("pending-")
    address = await wallet_mgr.get_wallet_address(agent.wallet_id)

    wallet_cfg = policy_mgr.get_wallet_config(agent.wallet_id)
    alias = wallet_cfg.get("alias") or agent.wallet_id.replace("pending-", "")

    policy = policy_mgr.get_policy()

    # Send a mock policy block for the CLI display
    # We check for to_dict or just use empty dict
    policy_dict = {}
    if hasattr(policy, "to_dict"):
        policy_dict = policy.to_dict()

    wallets = [
        WalletInfo(
            alias=alias,
            wallet_id=agent.wallet_id,
            address=address or ("INITIALIZING..." if is_pending else "NONE"),
            fund_address=address,
            policy=policy_dict,
        )
    ]

    return ListWalletsResponse(wallets=wallets)


@router.post("/x402/pay", response_model=PayResponse)
async def x402_pay(
    request: X402PayRequest,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """Execute an automated x402 payment flow using client.pay() for automatic routing to Circle Gateway."""
    try:
        amount = request.amount if request.amount else "0.01"
        result = await client.pay(
            wallet_id=agent.wallet_id,
            recipient=request.url,
            amount=amount,
            idempotency_key=request.idempotency_key,
            metadata={"method": request.method, "body": request.body, "headers": request.headers},
        )
        requires_confirmation = bool(
            result.metadata.get("confirmation_required") if result.metadata else False
        )
        confirmation_id = result.metadata.get("confirmation_id") if result.metadata else None

        return PayResponse(
            success=result.success,
            transaction_id=result.transaction_id,
            blockchain_tx=result.blockchain_tx,
            amount=str(result.amount),
            recipient=result.recipient,
            status=result.status.value
            if result.status and hasattr(result.status, "value")
            else (str(result.status) if result.status else "failed"),
            method="nanopayment",
            error=result.error,
            requires_confirmation=requires_confirmation,
            confirmation_id=confirmation_id,
            response_data=result.resource_data,
        )
    except Exception as e:
        logger.error(f"x402 payment failed: {e}")
        return PayResponse(
            success=False,
            amount="0",
            recipient=request.url,
            status="FAILED",
            method="nanopayment",
            error=str(e),
            response_data=None,
        )


@router.post("/x402/verify")
async def x402_verify(
    request: X402VerifyRequest,
    agent: AuthenticatedAgent = Depends(get_current_agent),
    client: OmniClaw = Depends(get_omniclaw_client),
):
    """Verify and settle an incoming x402 payment signature (for 'omniclaw-cli serve')."""
    import base64
    import json

    try:
        if not client._nano_client:
            return {"valid": False, "error": "Nanopayment client not initialized"}

        sig_data = json.loads(base64.b64decode(request.signature))

        from omniclaw.protocols.nanopayments.types import PaymentPayload, PaymentRequirements

        payload = PaymentPayload.from_dict(sig_data)

        amount_micro = (
            int(request.amount) if request.amount.isdigit() else int(float(request.amount) * 10**6)
        )

        wallet_addr = await client.get_payment_address(agent.wallet_id)

        requirements = PaymentRequirements(
            scheme=payload.scheme,
            network=payload.network,
            max_amount_required=str(amount_micro),
            resource=request.resource,
            description="x402 payment",
            recipient=wallet_addr,
        )

        result = await client._nano_client.settle(payload, requirements)

        if result.success:
            return {
                "valid": True,
                "sender": result.payer,
                "amount": request.amount,
                "transaction": result.transaction,
            }
        else:
            return {"valid": False, "error": result.error_reason or "Settlement failed"}

    except Exception as e:
        logger.error(f"x402 verify failed: {e}")
        return {"valid": False, "error": str(e)}
