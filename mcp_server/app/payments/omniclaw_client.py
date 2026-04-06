import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import structlog

from app.core.config import settings
from app.payments.interfaces import AbstractPaymentClient
from omniclaw import OmniClaw
from omniclaw.core.types import AccountType, Network
from omniclaw.identity.types import TrustPolicy
from omniclaw.ledger import LedgerEntryStatus, LedgerEntryType

logger = structlog.get_logger(__name__)


class OmniclawPaymentClient(AbstractPaymentClient):
    """Production wrapper around the Omniclaw SDK for MCP tools."""

    _instance: Optional["OmniclawPaymentClient"] = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        network = Network.from_string(settings.OMNICLAW_NETWORK)
        self._client = OmniClaw(
            circle_api_key=settings.CIRCLE_API_KEY.get_secret_value()
            if settings.CIRCLE_API_KEY
            else None,
            entity_secret=settings.ENTITY_SECRET.get_secret_value()
            if settings.ENTITY_SECRET
            else None,
            network=network,
        )
        logger.info(
            "omniclaw_sdk_initialized",
            network=network.value,
            cloud_mode=bool(settings.OMNICLAW_KEY),
        )

    @classmethod
    async def get_instance(cls) -> "OmniclawPaymentClient":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    async def close_instance(cls) -> None:
        if cls._instance is None:
            return
        await cls._instance._client.__aexit__(None, None, None)
        cls._instance = None

    @staticmethod
    def _serialize(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [OmniclawPaymentClient._serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: OmniclawPaymentClient._serialize(v) for k, v in value.items()}
        if is_dataclass(value):
            return OmniclawPaymentClient._serialize(asdict(value))
        if hasattr(value, "to_dict") and callable(value.to_dict):
            raw_dict = value.to_dict()
            if isinstance(raw_dict, dict):
                return OmniclawPaymentClient._serialize(raw_dict)
            return raw_dict
        if hasattr(value, "guards") and isinstance(value.guards, list):
            return [getattr(guard, "name", str(guard)) for guard in value.guards]
        return value

    @staticmethod
    def _as_network(value: str | None) -> Network | None:
        if not value:
            return None
        return Network.from_string(value)

    async def create_agent_wallet(
        self,
        agent_name: str,
        blockchain: str | None = None,
        apply_default_guards: bool = True,
    ) -> dict[str, Any]:
        wallet_set, wallet = await self._client.create_agent_wallet(
            agent_name=agent_name,
            blockchain=self._as_network(blockchain),
            apply_default_guards=apply_default_guards,
        )

        response: dict[str, Any] = {
            "wallet_set": self._serialize(wallet_set),
            "wallet": self._serialize(wallet),
        }

        if apply_default_guards:
            guards = await self.get_wallet_guards(wallet.id)
            if guards:
                response["default_guards"] = guards

        return response

    async def create_wallet_set(self, name: str | None = None) -> dict[str, Any]:
        wallet_set = await self._client.create_wallet_set(name=name)
        return self._serialize(wallet_set)

    async def get_wallet_set(self, wallet_set_id: str) -> dict[str, Any]:
        wallet_set = await self._client.get_wallet_set(wallet_set_id)
        return self._serialize(wallet_set)

    async def create_wallets(
        self,
        count: int,
        wallet_set_id: str | None = None,
        blockchain: str | None = None,
        account_type: str = "EOA",
    ) -> list[dict[str, Any]]:
        wallets = self._client.wallet.create_wallets(
            count=count,
            wallet_set_id=wallet_set_id,
            blockchain=self._as_network(blockchain),
            account_type=AccountType(account_type.upper()),
        )
        return self._serialize(wallets)

    async def create_wallet(
        self,
        wallet_set_id: str | None = None,
        blockchain: str | None = None,
        account_type: str = "EOA",
        name: str | None = None,
    ) -> dict[str, Any]:
        wallet = await self._client.create_wallet(
            wallet_set_id=wallet_set_id,
            blockchain=self._as_network(blockchain),
            account_type=AccountType(account_type.upper()),
            name=name,
        )
        return self._serialize(wallet)

    async def list_wallet_sets(self) -> list[dict[str, Any]]:
        wallet_sets = await self._client.list_wallet_sets()
        return self._serialize(wallet_sets)

    async def list_wallets(self, wallet_set_id: str | None = None) -> list[dict[str, Any]]:
        wallets = await self._client.list_wallets(wallet_set_id=wallet_set_id)
        return self._serialize(wallets)

    async def get_wallet(self, wallet_id: str) -> dict[str, Any]:
        wallet = await self._client.get_wallet(wallet_id)
        return self._serialize(wallet)

    async def simulate_payment(
        self,
        wallet_id: str,
        recipient: str,
        amount: str,
        wallet_set_id: str | None = None,
        check_trust: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        simulation = await self._client.simulate(
            wallet_id=wallet_id,
            recipient=recipient,
            amount=amount,
            wallet_set_id=wallet_set_id,
            check_trust=check_trust,
            **kwargs,
        )
        return self._serialize(simulation)

    async def execute_payment(
        self,
        wallet_id: str,
        recipient: str,
        amount: str,
        destination_chain: str | None = None,
        wallet_set_id: str | None = None,
        purpose: str | None = None,
        idempotency_key: str | None = None,
        fee_level: str = "medium",
        strategy: str = "retry_then_fail",
        skip_guards: bool = False,
        check_trust: bool | None = None,
        consume_intent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        wait_for_completion: bool = False,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from omniclaw.core.types import FeeLevel, PaymentStrategy

        result = await self._client.pay(
            wallet_id=wallet_id,
            recipient=recipient,
            amount=amount,
            destination_chain=self._as_network(destination_chain) if destination_chain else None,
            wallet_set_id=wallet_set_id,
            purpose=purpose,
            idempotency_key=idempotency_key,
            fee_level=FeeLevel(fee_level.upper()),
            strategy=PaymentStrategy(strategy.lower()),
            skip_guards=skip_guards,
            check_trust=check_trust,
            consume_intent_id=consume_intent_id,
            metadata=metadata,
            wait_for_completion=wait_for_completion,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        return self._serialize(result)

    async def create_payment_intent(
        self,
        wallet_id: str,
        recipient: str,
        amount: str,
        purpose: str | None = None,
        expires_in: int | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent = await self._client.intent.create(
            wallet_id=wallet_id,
            recipient=recipient,
            amount=amount,
            purpose=purpose,
            expires_in=expires_in,
            idempotency_key=idempotency_key,
            **(metadata or {}),
        )
        return self._serialize(intent)

    async def get_payment_intent(self, intent_id: str) -> dict[str, Any] | None:
        intent = await self._client.intent.get(intent_id)
        return self._serialize(intent)

    async def confirm_intent(self, intent_id: str) -> dict[str, Any]:
        result = await self._client.intent.confirm(intent_id)
        return self._serialize(result)

    async def cancel_intent(self, intent_id: str, reason: str | None = None) -> dict[str, Any]:
        result = await self._client.intent.cancel(intent_id=intent_id, reason=reason)
        return self._serialize(result)

    async def get_wallet_usdc_balance(self, wallet_id: str) -> dict[str, Any]:
        balance = await self._client.get_balance(wallet_id)
        return {
            "wallet_id": wallet_id,
            "currency": "USDC",
            "usdc_balance": str(balance),
        }

    async def get_balances(self, wallet_id: str) -> dict[str, Any]:
        balances = self._client.wallet.get_balances(wallet_id)
        return {"wallet_id": wallet_id, "balances": self._serialize(balances)}

    async def list_guards(self, wallet_id: str) -> dict[str, Any]:
        guards = await self._client.guards.list_wallet_guard_names(wallet_id)
        return {"wallet_id": wallet_id, "guards": guards}

    async def get_wallet_guards(self, wallet_id: str) -> dict[str, Any]:
        guards = await self._client.guards.get_wallet_guards(wallet_id)
        return {"wallet_id": wallet_id, "guards": self._serialize(guards)}

    async def get_wallet_set_guards(self, wallet_set_id: str) -> dict[str, Any]:
        guards = await self._client.guards.get_wallet_set_guards(wallet_set_id)
        return {"wallet_set_id": wallet_set_id, "guards": self._serialize(guards)}

    async def list_wallet_set_guard_names(self, wallet_set_id: str) -> dict[str, Any]:
        guards = await self._client.guards.list_wallet_set_guard_names(wallet_set_id)
        return {"wallet_set_id": wallet_set_id, "guards": guards}

    async def remove_guard(self, wallet_id: str, guard_name: str) -> dict[str, Any]:
        removed = await self._client.guards.remove_guard(wallet_id, guard_name)
        return {"wallet_id": wallet_id, "guard_name": guard_name, "removed": removed}

    async def remove_guard_from_set(self, wallet_set_id: str, guard_name: str) -> dict[str, Any]:
        removed = await self._client.guards.remove_guard_from_set(wallet_set_id, guard_name)
        return {"wallet_set_id": wallet_set_id, "guard_name": guard_name, "removed": removed}

    async def clear_wallet_guards(self, wallet_id: str) -> dict[str, Any]:
        await self._client.guards.clear_wallet_guards(wallet_id)
        return {"wallet_id": wallet_id, "cleared": True}

    async def clear_wallet_set_guards(self, wallet_set_id: str) -> dict[str, Any]:
        await self._client.guards.clear_wallet_set_guards(wallet_set_id)
        return {"wallet_set_id": wallet_set_id, "cleared": True}

    async def add_budget_guard(
        self,
        wallet_id: str,
        daily_limit: str | None = None,
        hourly_limit: str | None = None,
        total_limit: str | None = None,
        name: str = "budget",
    ) -> dict[str, Any]:
        from omniclaw.guards.budget import BudgetGuard

        guard = BudgetGuard(
            name=name,
            daily_limit=Decimal(daily_limit) if daily_limit else None,
            hourly_limit=Decimal(hourly_limit) if hourly_limit else None,
            total_limit=Decimal(total_limit) if total_limit else None,
        )
        await self._client.guards.add_guard(wallet_id, guard)
        return {
            "wallet_id": wallet_id,
            "guard": "budget",
            "name": name,
            "daily_limit": daily_limit,
            "hourly_limit": hourly_limit,
            "total_limit": total_limit,
        }

    async def add_rate_limit_guard(
        self,
        wallet_id: str,
        max_per_minute: int | None = None,
        max_per_hour: int | None = None,
        max_per_day: int | None = None,
        name: str = "rate_limit",
    ) -> dict[str, Any]:
        from omniclaw.guards.rate_limit import RateLimitGuard

        guard = RateLimitGuard(
            name=name,
            max_per_minute=max_per_minute,
            max_per_hour=max_per_hour,
            max_per_day=max_per_day,
        )
        await self._client.guards.add_guard(wallet_id, guard)
        return {
            "wallet_id": wallet_id,
            "guard": "rate_limit",
            "name": name,
            "max_per_minute": max_per_minute,
            "max_per_hour": max_per_hour,
            "max_per_day": max_per_day,
        }

    async def add_single_tx_guard(
        self,
        wallet_id: str,
        max_amount: str,
        min_amount: str | None = None,
        name: str = "single_tx",
    ) -> dict[str, Any]:
        from omniclaw.guards.single_tx import SingleTxGuard

        guard = SingleTxGuard(
            name=name,
            max_amount=Decimal(max_amount),
            min_amount=Decimal(min_amount) if min_amount else None,
        )
        await self._client.guards.add_guard(wallet_id, guard)
        return {
            "wallet_id": wallet_id,
            "guard": "single_tx",
            "name": name,
            "max_amount": max_amount,
            "min_amount": min_amount,
        }

    async def add_recipient_guard(
        self,
        wallet_id: str,
        mode: str = "whitelist",
        addresses: list[str] | None = None,
        patterns: list[str] | None = None,
        domains: list[str] | None = None,
        name: str = "recipient",
    ) -> dict[str, Any]:
        from omniclaw.guards.recipient import RecipientGuard

        guard = RecipientGuard(
            name=name,
            mode=mode,
            addresses=addresses,
            patterns=patterns,
            domains=domains,
        )
        await self._client.guards.add_guard(wallet_id, guard)
        return {
            "wallet_id": wallet_id,
            "guard": "recipient",
            "name": name,
            "mode": mode,
            "addresses": addresses or [],
            "patterns": patterns or [],
            "domains": domains or [],
        }

    async def add_confirm_guard(
        self,
        wallet_id: str,
        always_confirm: bool = False,
        threshold: str | None = None,
        name: str = "confirm",
    ) -> dict[str, Any]:
        from omniclaw.guards.confirm import ConfirmGuard

        guard = ConfirmGuard(
            name=name,
            always_confirm=always_confirm,
            threshold=Decimal(threshold) if threshold else None,
        )
        await self._client.guards.add_guard(wallet_id, guard)
        return {
            "wallet_id": wallet_id,
            "guard": "confirm",
            "name": name,
            "always_confirm": always_confirm,
            "threshold": threshold,
        }

    async def add_guard_for_set(
        self,
        wallet_set_id: str,
        guard_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        # Helper that handles generic dict instantiations for set-level guard applications
        from omniclaw.guards.budget import BudgetGuard
        from omniclaw.guards.confirm import ConfirmGuard
        from omniclaw.guards.rate_limit import RateLimitGuard
        from omniclaw.guards.recipient import RecipientGuard
        from omniclaw.guards.single_tx import SingleTxGuard

        name = config.get("name", guard_type)
        guard = None

        if guard_type == "budget":
            daily_limit = config.get("daily_limit")
            hourly_limit = config.get("hourly_limit")
            total_limit = config.get("total_limit")
            guard = BudgetGuard(
                name=name,
                daily_limit=Decimal(str(daily_limit)) if daily_limit else None,
                hourly_limit=Decimal(str(hourly_limit)) if hourly_limit else None,
                total_limit=Decimal(str(total_limit)) if total_limit else None,
            )
        elif guard_type == "rate_limit":
            guard = RateLimitGuard(
                name=name,
                max_per_minute=config.get("max_per_minute"),
                max_per_hour=config.get("max_per_hour"),
                max_per_day=config.get("max_per_day"),
            )
        elif guard_type == "single_tx":
            min_amount = config.get("min_amount")
            guard = SingleTxGuard(
                name=name,
                max_amount=Decimal(str(config["max_amount"])),
                min_amount=Decimal(str(min_amount)) if min_amount else None,
            )
        elif guard_type == "recipient":
            guard = RecipientGuard(
                name=name,
                mode=config.get("mode", "whitelist"),
                addresses=config.get("addresses"),
                patterns=config.get("patterns"),
                domains=config.get("domains"),
            )
        elif guard_type == "confirm":
            threshold = config.get("threshold")
            guard = ConfirmGuard(
                name=name,
                always_confirm=config.get("always_confirm", False),
                threshold=Decimal(str(threshold)) if threshold else None,
            )
        else:
            raise ValueError(f"Unknown guard type: {guard_type}")

        await self._client.guards.add_guard_for_set(wallet_set_id, guard)
        return {"wallet_set_id": wallet_set_id, "guard_type": guard_type, "added": True}

    async def list_transactions(
        self,
        wallet_id: str | None = None,
        blockchain: str | None = None,
    ) -> dict[str, Any]:
        transactions = await self._client.list_transactions(
            wallet_id=wallet_id,
            blockchain=self._as_network(blockchain),
        )
        return {"transactions": self._serialize(transactions)}

    async def sync_transaction(self, ledger_entry_id: str) -> dict[str, Any]:
        entry = await self._client.sync_transaction(ledger_entry_id)
        return {"entry": self._serialize(entry)}

    async def batch_pay(
        self,
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from omniclaw.core.types import PaymentRequest

        payment_requests = []
        for req in requests:
            payment_requests.append(
                PaymentRequest(
                    wallet_id=req["wallet_id"],
                    recipient=req["recipient"],
                    amount=Decimal(str(req["amount"])),
                    purpose=req.get("purpose"),
                    idempotency_key=req.get("idempotency_key"),
                    destination_chain=req.get("destination_chain"),
                    metadata=req.get("metadata", {}),
                )
            )

        result = await self._client.batch_pay(
            requests=payment_requests,
            concurrency=5,
        )
        return self._serialize(result)

    async def trust_lookup(
        self,
        recipient_address: str,
        amount: str = "0",
        wallet_id: str | None = None,
        network: str | None = None,
    ) -> dict[str, Any]:
        result = await self._client.trust.evaluate(
            recipient_address=recipient_address,
            amount=Decimal(str(amount)),
            wallet_id=wallet_id,
            network=self._as_network(network),
        )
        return {"trust_result": self._serialize(result)}

    async def trust_set_policy(self, wallet_id: str, preset: str) -> dict[str, Any]:
        normalized = preset.strip().lower()
        if normalized == "permissive":
            policy = TrustPolicy.permissive()
        elif normalized == "standard":
            policy = TrustPolicy.standard()
        elif normalized == "strict":
            policy = TrustPolicy.strict()
        else:
            raise ValueError("Invalid trust policy preset. Use: permissive, standard, or strict.")

        self._client.trust.set_policy(wallet_id=wallet_id, policy=policy)
        return {
            "wallet_id": wallet_id,
            "preset": normalized,
            "policy": self._serialize(policy),
        }

    async def trust_get_policy(self, wallet_id: str | None = None) -> dict[str, Any]:
        policy = self._client.trust.get_policy(wallet_id)
        return {
            "wallet_id": wallet_id,
            "policy": self._serialize(policy),
        }

    async def ledger_get_entry(self, entry_id: str) -> dict[str, Any]:
        entry = await self._client.ledger.get(entry_id)
        return {"entry": self._serialize(entry)}

    async def ledger_query(
        self,
        wallet_id: str | None = None,
        wallet_set_id: str | None = None,
        recipient: str | None = None,
        entry_type: str | None = None,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        parsed_entry_type = LedgerEntryType(entry_type.lower()) if entry_type else None
        parsed_status = LedgerEntryStatus(status.lower()) if status else None
        parsed_from_date = datetime.fromisoformat(from_date) if from_date else None
        parsed_to_date = datetime.fromisoformat(to_date) if to_date else None

        entries = await self._client.ledger.query(
            wallet_id=wallet_id,
            wallet_set_id=wallet_set_id,
            recipient=recipient,
            entry_type=parsed_entry_type,
            status=parsed_status,
            from_date=parsed_from_date,
            to_date=parsed_to_date,
            limit=limit,
        )
        return {"entries": self._serialize(entries)}

    async def can_pay(self, recipient: str) -> dict[str, Any]:
        return {"recipient": recipient, "can_pay": self._client.can_pay(recipient)}

    async def detect_method(self, recipient: str) -> dict[str, Any]:
        method = self._client.detect_method(recipient)
        return {
            "recipient": recipient,
            "payment_method": method.value if method else None,
        }

    async def verify_webhook_signature(
        self,
        payload_body: str,
        signature_header: str,
        endpoint_secret: str,
    ) -> dict[str, Any]:
        from omniclaw.webhooks.parser import WebhookParser

        parser = WebhookParser(endpoint_secret)
        is_valid = parser.verify_signature(
            payload=payload_body,
            headers={"x-circle-signature": signature_header},
        )
        return {"is_valid": is_valid}

    async def handle_webhook(
        self,
        payload_body: str,
        signature_header: str,
        endpoint_secret: str,
    ) -> dict[str, Any]:
        from omniclaw.webhooks.parser import WebhookParser

        parser = WebhookParser(endpoint_secret)
        event = parser.handle(
            payload=payload_body,
            headers={"x-circle-signature": signature_header},
        )
        return {"event": self._serialize(event)}


# Backward compatibility alias used by legacy imports/tests.
OmniAgentPaymentClient = OmniclawPaymentClient
