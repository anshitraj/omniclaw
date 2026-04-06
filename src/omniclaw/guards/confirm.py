"""
ConfirmGuard - Requires explicit confirmation for payments.

Simple guard that requires confirmation above a threshold or for all payments.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import uuid4

from omniclaw.events import event_emitter
from omniclaw.guards.base import Guard, GuardResult, PaymentContext
from omniclaw.guards.confirmations import ConfirmationStore


class ConfirmRequiredError(ValueError):
    """Raised when a payment requires manual confirmation."""

    def __init__(self, confirmation_id: str) -> None:
        super().__init__("Payment requires confirmation")
        self.confirmation_id = confirmation_id


# Type for confirmation callback
ConfirmCallback = Callable[[PaymentContext], Awaitable[bool]]


class ConfirmGuard(Guard):
    """
    Guard that requires explicit confirmation for payments.

    Useful for high-value transactions or sensitive recipients.

    Two modes of operation:
    1. **Callback mode**: Provide a callback that gets called for confirmation
    2. **Threshold only**: Blocks payments above threshold (requires external handling)
    """

    def __init__(
        self,
        confirm_callback: ConfirmCallback | None = None,
        threshold: Decimal | None = None,
        always_confirm: bool = False,
        name: str = "confirm",
    ) -> None:
        """
        Initialize ConfirmGuard.

        Args:
            confirm_callback: Async function to call for confirmation
            threshold: Only confirm payments above this amount
            always_confirm: If True, confirm all payments
            name: Guard name for identification
        """
        self._name = name
        self._callback = confirm_callback
        self._threshold = threshold
        self._always_confirm = always_confirm
        self._storage: Any | None = None
        self._confirmations: ConfirmationStore | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def threshold(self) -> Decimal | None:
        return self._threshold

    def bind_storage(self, storage: Any) -> None:
        self._storage = storage
        self._confirmations = ConfirmationStore(storage)

    def _needs_confirmation(self, amount: Decimal) -> bool:
        """Check if amount requires confirmation."""
        if self._always_confirm:
            return True
        return self._threshold is not None and amount >= self._threshold

    async def check(self, context: PaymentContext) -> GuardResult:
        """Check if payment is confirmed."""
        if not self._needs_confirmation(context.amount):
            event_emitter.emit_background(
                "payment.guard_evaluated", context.wallet_id, {"result": "PASS"}
            )
            return GuardResult(
                allowed=True,
                guard_name=self.name,
                metadata={"confirmation_required": False},
            )

        # If we have a callback, use it
        if self._callback is not None:
            try:
                confirmed = await self._callback(context)
                if confirmed:
                    event_emitter.emit_background(
                        "payment.guard_evaluated", context.wallet_id, {"result": "PASS"}
                    )
                    return GuardResult(
                        allowed=True,
                        guard_name=self.name,
                        metadata={"confirmation_required": True, "confirmed": True},
                    )
                else:
                    event_emitter.emit_background(
                        "payment.guard_evaluated", context.wallet_id, {"result": "FAIL"}
                    )
                    return GuardResult(
                        allowed=False,
                        reason="Payment not confirmed by user",
                        guard_name=self.name,
                        metadata={"confirmation_required": True, "confirmed": False},
                    )
            except Exception as e:
                event_emitter.emit_background(
                    "payment.guard_evaluated", context.wallet_id, {"result": "FAIL"}
                )
                return GuardResult(
                    allowed=False,
                    reason=f"Confirmation callback failed: {e}",
                    guard_name=self.name,
                    metadata={"confirmation_required": True, "error": str(e)},
                )

        # No callback - block and indicate confirmation needed
        event_emitter.emit_background(
            "guard.confirm_required", context.wallet_id, {"amount": str(context.amount)}
        )
        event_emitter.emit_background(
            "payment.guard_evaluated", context.wallet_id, {"result": "FAIL"}
        )
        return GuardResult(
            allowed=False,
            reason=(
                f"Payment of {context.amount} requires confirmation. "
                "Set a confirm_callback or handle confirmation externally."
            ),
            guard_name=self.name,
            metadata={
                "confirmation_required": True,
                "amount": str(context.amount),
                "threshold": str(self._threshold) if self._threshold else None,
            },
        )

    async def reserve(self, context: PaymentContext) -> str | None:
        """Reserve confirmation or allow if already approved."""
        if not self._needs_confirmation(context.amount):
            return None

        # Callback path (if configured) is handled in check()
        if self._callback is not None:
            result = await self.check(context)
            if not result.allowed:
                raise ValueError(result.reason)
            return None

        metadata = context.metadata or {}
        confirmation_id = metadata.get("confirmation_id")
        if not confirmation_id:
            idem = metadata.get("idempotency_key")
            if idem:
                confirmation_id = f"{context.wallet_id}:{idem}"

        # If confirmation_id provided, check status
        if confirmation_id and self._confirmations:
            record = await self._confirmations.get(confirmation_id)
            if record:
                status = record.get("status")
                if status == "APPROVED":
                    await self._confirmations.consume(confirmation_id)
                    return None
                if status == "DENIED":
                    raise ValueError("Payment confirmation denied")

        # Create a confirmation record
        if self._confirmations:
            if not confirmation_id:
                confirmation_id = str(uuid4())
            await self._confirmations.create(
                wallet_id=context.wallet_id,
                recipient=context.recipient,
                amount=str(context.amount),
                purpose=context.purpose,
                confirmation_id=confirmation_id,
                idempotency_key=metadata.get("idempotency_key"),
            )

        raise ConfirmRequiredError(str(confirmation_id))

    def reset(self) -> None:
        """No state to reset."""
        pass
