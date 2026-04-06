from abc import ABC, abstractmethod
from typing import Any


class PaymentProvider(ABC):
    @abstractmethod
    async def initiate_transfer(
        self, amount: float, currency: str, destination: str
    ) -> dict[str, Any]:
        pass


class DirectTransferProvider(PaymentProvider):
    async def initiate_transfer(
        self, amount: float, currency: str, destination: str
    ) -> dict[str, Any]:
        # Logic for direct bank/wallet transfer
        return {"provider": "direct", "status": "initiated", "destination": destination}


class X402Provider(PaymentProvider):
    async def initiate_transfer(
        self, amount: float, currency: str, destination: str
    ) -> dict[str, Any]:
        # Logic for x402 / HTTP 402 Payment Required protocol
        return {
            "provider": "x402",
            "status": "awaiting_payment_receipt",
            "destination": destination,
        }


class CircleProvider(PaymentProvider):
    async def initiate_transfer(
        self, amount: float, currency: str, destination: str
    ) -> dict[str, Any]:
        # Circle API integration
        return {"provider": "circle", "status": "processing", "destination": destination}
