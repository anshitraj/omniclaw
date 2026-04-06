import pytest

from omniclaw.intents.reservation import ReservationService
from omniclaw.storage.memory import InMemoryStorage


@pytest.mark.asyncio
async def test_get_reserved_total_fails_closed_on_corrupted_amount() -> None:
    storage = InMemoryStorage()
    service = ReservationService(storage)

    await storage.save(
        service.COLLECTION,
        "intent-corrupt",
        {
            "wallet_id": "wallet-1",
            "amount": "not-a-decimal",
            "intent_id": "intent-corrupt",
            "created_at": "2026-01-01T00:00:00",
        },
    )

    with pytest.raises(ValueError, match="Corrupted reservation amount"):
        await service.get_reserved_total("wallet-1")
