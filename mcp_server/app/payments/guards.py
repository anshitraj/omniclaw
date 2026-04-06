from abc import ABC, abstractmethod
from typing import Any

import structlog

from app.core.config import settings
from app.utils.exceptions import (
    BudgetExceededError,
    UnauthorizedRecipientError,
)

logger = structlog.get_logger(__name__)


class PaymentGuard(ABC):
    """Base class for all payment security guardrails."""

    @abstractmethod
    async def validate(self, amount: float, wallet_id: str, recipient: str | None = None):
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert guard configuration to a dictionary for SDK registration."""
        pass


class BudgetGuard(PaymentGuard):
    """Enforces daily and hourly spending limits."""

    def __init__(
        self,
        daily_limit: float = settings.OMNICLAW_DAILY_BUDGET,
        hourly_limit: float = settings.OMNICLAW_HOURLY_BUDGET,
    ):
        self.daily_limit = daily_limit
        self.hourly_limit = hourly_limit

    async def validate(self, amount: float, wallet_id: str, recipient: str | None = None):
        # Implementation would check against ledger/cache
        # For now, it defines the policy to be enforced by Omniclaw
        pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "budget",
            "daily_limit": self.daily_limit,
            "hourly_limit": self.hourly_limit,
        }


class SingleTransactionGuard(PaymentGuard):
    """Limits the maximum amount for any single transaction."""

    def __init__(self, tx_limit: float = settings.OMNICLAW_TX_LIMIT):
        self.tx_limit = tx_limit

    async def validate(self, amount: float, wallet_id: str, recipient: str | None = None):
        if amount > self.tx_limit:
            raise BudgetExceededError(f"Transaction exceeds limit of {self.tx_limit}")

    def to_dict(self) -> dict[str, Any]:
        return {"type": "single_transaction", "max_amount": self.tx_limit}


class RateLimitGuard(PaymentGuard):
    """Limits the number of transactions per minute."""

    def __init__(self, requests_per_min: int = settings.OMNICLAW_RATE_LIMIT_PER_MIN):
        self.requests_per_min = requests_per_min

    async def validate(self, amount: float, wallet_id: str, recipient: str | None = None):
        pass

    def to_dict(self) -> dict[str, Any]:
        return {"type": "rate_limit", "requests_per_minute": self.requests_per_min}


class RecipientWhitelistGuard(PaymentGuard):
    """Restricts payments to a pre-approved list of addresses."""

    def __init__(self, whitelisted_addresses: list[str] = settings.OMNICLAW_WHITELISTED_RECIPIENTS):
        self.whitelisted_addresses = whitelisted_addresses

    async def validate(self, amount: float, wallet_id: str, recipient: str | None = None):
        if self.whitelisted_addresses and recipient not in self.whitelisted_addresses:
            raise UnauthorizedRecipientError(recipient or "Unknown")

    def to_dict(self) -> dict[str, Any]:
        return {"type": "recipient_whitelist", "addresses": self.whitelisted_addresses}


def get_default_guards() -> list[PaymentGuard]:
    """Returns the set of default guards as configured in the environment."""
    return [BudgetGuard(), SingleTransactionGuard(), RateLimitGuard(), RecipientWhitelistGuard()]
