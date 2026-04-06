from __future__ import annotations

import uuid
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator

from app.payments.interfaces import AbstractPaymentClient
from app.payments.omniclaw_client import OmniclawPaymentClient
from app.utils.exceptions import GuardValidationError, PaymentError

logger = structlog.get_logger(__name__)


class PaymentRequest(BaseModel):
    """Legacy compatibility request schema for payment orchestration."""

    wallet_id: str = Field(..., description="Source wallet ID")
    recipient: str = Field(..., description="Recipient address or URL")
    amount: str = Field(..., description="Amount to send as numeric string")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            value = float(v)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Amount must be a valid numeric string") from exc
        if value <= 0:
            raise ValueError("Amount must be positive")
        return v


class PaymentOrchestrator:
    """Compatibility orchestrator: simulate first, then execute."""

    def __init__(self, client: AbstractPaymentClient):
        self.client = client

    async def pay(self, request_data: dict[str, Any]) -> dict[str, Any]:
        try:
            req = PaymentRequest(**request_data)
        except Exception as exc:
            raise PaymentError(f"Invalid input: {exc}") from exc

        idempotency_key = str(uuid.uuid4())

        simulation = await self.client.simulate_payment(
            wallet_id=req.wallet_id,
            recipient=req.recipient,
            amount=req.amount,
        )
        if not simulation.get("would_succeed"):
            raise GuardValidationError(
                f"Payment simulation failed: {simulation.get('reason', 'Unknown simulation failure')}"
            )

        payment = await self.client.execute_payment(
            wallet_id=req.wallet_id,
            recipient=req.recipient,
            amount=req.amount,
            idempotency_key=idempotency_key,
        )

        logger.info(
            "orchestrated_payment_executed",
            wallet_id=req.wallet_id,
            recipient=req.recipient,
            amount=req.amount,
        )
        return {
            "status": "success",
            "idempotency_key": idempotency_key,
            "payment": payment,
        }


async def get_payment_orchestrator() -> PaymentOrchestrator:
    client = await OmniclawPaymentClient.get_instance()
    return PaymentOrchestrator(client)
