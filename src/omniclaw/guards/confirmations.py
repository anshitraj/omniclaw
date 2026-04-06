"""Confirmation request storage for ConfirmGuard approvals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from omniclaw.storage.base import StorageBackend

CONFIRM_COLLECTION = "confirmations"


@dataclass
class ConfirmationRecord:
    confirmation_id: str
    wallet_id: str
    recipient: str
    amount: str
    purpose: str | None
    status: str
    created_at: str
    expires_at: str | None = None
    idempotency_key: str | None = None


class ConfirmationStore:
    """Persist and manage confirmation requests."""

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    def _key(self, confirmation_id: str) -> str:
        return confirmation_id

    async def get(self, confirmation_id: str) -> dict[str, Any] | None:
        return await self._storage.get(CONFIRM_COLLECTION, self._key(confirmation_id))

    async def create(
        self,
        *,
        wallet_id: str,
        recipient: str,
        amount: str,
        purpose: str | None,
        confirmation_id: str | None = None,
        idempotency_key: str | None = None,
        ttl_minutes: int = 60,
    ) -> ConfirmationRecord:
        confirmation_id = confirmation_id or str(uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl_minutes)
        record = ConfirmationRecord(
            confirmation_id=confirmation_id,
            wallet_id=wallet_id,
            recipient=recipient,
            amount=amount,
            purpose=purpose,
            status="PENDING",
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            idempotency_key=idempotency_key,
        )
        await self._storage.save(CONFIRM_COLLECTION, self._key(confirmation_id), record.__dict__)
        return record

    async def set_status(self, confirmation_id: str, status: str) -> dict[str, Any] | None:
        record = await self.get(confirmation_id)
        if not record:
            return None
        record["status"] = status
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._storage.save(CONFIRM_COLLECTION, self._key(confirmation_id), record)
        return record

    async def approve(self, confirmation_id: str) -> dict[str, Any] | None:
        return await self.set_status(confirmation_id, "APPROVED")

    async def deny(self, confirmation_id: str) -> dict[str, Any] | None:
        return await self.set_status(confirmation_id, "DENIED")

    async def consume(self, confirmation_id: str) -> dict[str, Any] | None:
        return await self.set_status(confirmation_id, "CONSUMED")
