"""
Generic x402 Facilitator interface.

Supports the top facilitators:
1. Circle Gateway - Circle's native facilitator
2. Coinbase CDP - Coinbase's facilitator
3. OrderN - https://ordern.ai (x402 facilitator)
4. RBX - https://rbx.io (x402 facilitator)
5. Thirdweb - thirdweb's facilitator

Usage:
    from omniclaw.seller import create_facilitator

    # Circle's facilitator
    facilitator = create_facilitator("circle", api_key="...")

    # Coinbase's facilitator
    facilitator = create_facilitator("coinbase", api_key="...")

    # OrderN facilitator
    facilitator = create_facilitator("ordern", api_key="...")

    # Auto-detect from provider string
    facilitator = create_facilitator("circle")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from omniclaw.seller.facilitator import (
    CircleGatewayFacilitator as CircleImpl,
)
from omniclaw.seller.facilitator import (
    SettleResult,
    VerifyResult,
)

# Re-export Circle's implementation
CircleGatewayFacilitator = CircleImpl


async def _fetch_supported_networks(
    client: Any,
    base_url: str,
    headers: dict[str, str],
    candidate_paths: list[str],
) -> list[dict[str, Any]]:
    """Fetch supported networks from known provider endpoints."""
    last_error: Exception | None = None
    for path in candidate_paths:
        try:
            response = await client.get(f"{base_url}{path}", headers=headers)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if isinstance(data.get("supportedNetworks"), list):
                    return data["supportedNetworks"]
                if isinstance(data.get("networks"), list):
                    return data["networks"]
                if isinstance(data.get("kinds"), list):
                    return data["kinds"]
                if isinstance(data.get("data"), list):
                    return data["data"]
            if isinstance(data, list):
                return data
            last_error = ValueError(f"Unsupported /supported schema from {path}")
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise RuntimeError(f"Unable to fetch supported networks: {last_error}") from last_error
    raise RuntimeError("Unable to fetch supported networks: no candidate paths configured")


class BaseFacilitator(ABC):
    """
    Abstract base class for x402 facilitators.

    Facilitators handle payment verification and settlement on behalf of sellers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Facilitator name."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """API base URL."""
        pass

    @property
    @abstractmethod
    def environment(self) -> str:
        """Environment (testnet/mainnet)."""
        pass

    @abstractmethod
    async def verify(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> VerifyResult:
        """
        Verify payment payload (read-only).

        Args:
            payment_payload: The payment payload from client
            payment_requirements: The payment requirements from 402 response

        Returns:
            VerifyResult with validation status
        """
        pass

    @abstractmethod
    async def settle(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> SettleResult:
        """
        Settle payment (execute on-chain).

        Args:
            payment_payload: The payment payload from client
            payment_requirements: The payment requirements from 402 response

        Returns:
            SettleResult with settlement status
        """
        pass

    @abstractmethod
    async def get_supported_networks(self) -> list[dict[str, Any]]:
        """Get supported networks."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close HTTP client."""
        pass


def _parse_price_to_atomic(price: str) -> str:
    value = str(price).strip()
    if not value:
        raise ValueError("price is required")
    if value.startswith("$"):
        value = value[1:].strip()
    decimal_value = Decimal(value)
    scaled = decimal_value * Decimal(1_000_000)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"price {price!r} cannot be represented with 6 decimals")
    return str(int(scaled))


# =============================================================================
# Coinbase Facilitator
# =============================================================================


class CoinbaseFacilitator(BaseFacilitator):
    """
    Coinbase CDP x402 Facilitator.

    https://docs.cdp.coinbase.com/x402/docs/facilitator
    """

    COINBASE_TESTNET = "https://api.cdp.coinbase.com/platform"
    COINBASE_MAINNET = "https://api.cdp.coinbase.com/platform"

    def __init__(
        self,
        api_key: str,
        environment: str = "testnet",
        timeout: float = 30.0,
    ):
        import httpx

        self._api_key = api_key
        self._environment = environment
        self._timeout = timeout
        self._base_url = (
            self.COINBASE_TESTNET if environment == "testnet" else self.COINBASE_MAINNET
        )
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return "coinbase"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def environment(self) -> str:
        return self._environment

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        url = f"{self._base_url}/v2/x402/verify"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return VerifyResult(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        except Exception as e:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(e))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        url = f"{self._base_url}/v2/x402/settle"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return SettleResult(
                success=data.get("success", False),
                transaction=data.get("transaction"),
                network=data.get("network"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
            )
        except Exception as e:
            return SettleResult(
                success=False, transaction=None, network=None, error_reason=str(e), payer=None
            )

    async def get_supported_networks(self) -> list:
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        return await _fetch_supported_networks(
            client=self._client,
            base_url=self._base_url,
            headers=headers,
            candidate_paths=["/v2/x402/supported", "/v1/x402/supported", "/x402/supported"],
        )

    async def close(self):
        await self._client.aclose()


# =============================================================================
# OrderN Facilitator (https://ordern.ai)
# =============================================================================


class OrderNFacilitator(BaseFacilitator):
    """
    OrderN x402 Facilitator.

    https://ordern.ai
    """

    ORDERN_TESTNET = "https://api.testnet.ordern.ai"
    ORDERN_MAINNET = "https://api.ordern.ai"

    def __init__(self, api_key: str, environment: str = "testnet", timeout: float = 30.0):
        import httpx

        self._api_key = api_key
        self._environment = environment
        self._timeout = timeout
        self._base_url = self.ORDERN_TESTNET if environment == "testnet" else self.ORDERN_MAINNET
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return "ordern"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def environment(self) -> str:
        return self._environment

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        url = f"{self._base_url}/v1/x402/verify"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return VerifyResult(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        except Exception as e:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(e))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        url = f"{self._base_url}/v1/x402/settle"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return SettleResult(
                success=data.get("success", False),
                transaction=data.get("transaction"),
                network=data.get("network"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
            )
        except Exception as e:
            return SettleResult(
                success=False, transaction=None, network=None, error_reason=str(e), payer=None
            )

    async def get_supported_networks(self) -> list:
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        return await _fetch_supported_networks(
            client=self._client,
            base_url=self._base_url,
            headers=headers,
            candidate_paths=["/v1/x402/supported", "/x402/supported", "/api/v1/x402/supported"],
        )

    async def close(self):
        await self._client.aclose()


# =============================================================================
# RBX Facilitator (https://rbx.io)
# =============================================================================


class RBXFacilitator(BaseFacilitator):
    """
    RBX x402 Facilitator.

    https://rbx.io
    """

    RBX_TESTNET = "https://api.testnet.rbx.io"
    RBX_MAINNET = "https://api.rbx.io"

    def __init__(self, api_key: str, environment: str = "testnet", timeout: float = 30.0):
        import httpx

        self._api_key = api_key
        self._environment = environment
        self._timeout = timeout
        self._base_url = self.RBX_TESTNET if environment == "testnet" else self.RBX_MAINNET
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return "rbx"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def environment(self) -> str:
        return self._environment

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        url = f"{self._base_url}/x402/verify"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return VerifyResult(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        except Exception as e:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(e))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        url = f"{self._base_url}/x402/settle"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return SettleResult(
                success=data.get("success", False),
                transaction=data.get("transaction"),
                network=data.get("network"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
            )
        except Exception as e:
            return SettleResult(
                success=False, transaction=None, network=None, error_reason=str(e), payer=None
            )

    async def get_supported_networks(self) -> list:
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        return await _fetch_supported_networks(
            client=self._client,
            base_url=self._base_url,
            headers=headers,
            candidate_paths=["/x402/supported", "/v1/x402/supported", "/api/v1/x402/supported"],
        )

    async def close(self):
        await self._client.aclose()


# =============================================================================
# Thirdweb Facilitator
# =============================================================================


class ThirdwebFacilitator(BaseFacilitator):
    """
    Thirdweb x402 Facilitator using the public HTTP API.

    https://portal.thirdweb.com/reference#tag/x402
    """

    THIRDWEB_API = "https://api.thirdweb.com"

    def __init__(
        self,
        api_key: str,
        environment: str = "testnet",
        timeout: float = 30.0,
        server_wallet_address: str | None = None,
        default_network: str | None = None,
    ):
        import os

        import httpx

        self._api_key = api_key
        self._environment = environment
        self._timeout = timeout
        self._server_wallet_address = (
            server_wallet_address or os.environ.get("THIRDWEB_SERVER_WALLET_ADDRESS") or ""
        ).strip()
        self._default_network = (
            default_network
            or os.environ.get("THIRDWEB_X402_NETWORK")
            or os.environ.get("OMNICLAW_X402_NETWORK")
            or "base-sepolia"
        ).strip()
        self._base_url = self.THIRDWEB_API
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return "thirdweb"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def environment(self) -> str:
        return self._environment

    async def create_accepts(
        self,
        *,
        resource_url: str,
        method: str = "GET",
        network: str | None = None,
        price: str,
        server_wallet_address: str | None = None,
    ) -> list[dict[str, Any]]:
        """Create x402 accepts through Thirdweb's public HTTP API."""
        wallet_address = (server_wallet_address or self._server_wallet_address).strip()
        if not wallet_address:
            raise ValueError(
                "THIRDWEB_SERVER_WALLET_ADDRESS is required to create Thirdweb x402 accepts"
            )

        url = f"{self._base_url}/v1/payments/x402/accepts"
        headers = {"x-secret-key": self._api_key, "Content-Type": "application/json"}
        response = await self._client.post(
            url,
            json={
                "resourceUrl": resource_url,
                "method": method.upper(),
                "network": network or self._default_network,
                "price": price,
                "serverWalletAddress": wallet_address,
            },
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        data = data.get("result", data) if isinstance(data, dict) else {}
        accepts = data.get("accepts", data if isinstance(data, list) else [])
        if not isinstance(accepts, list):
            raise RuntimeError("Thirdweb accepts response did not contain an accepts array")
        return accepts

    async def fetch_with_payment(
        self,
        *,
        url: str,
        from_address: str,
        method: str = "GET",
        chain_id: str | None = None,
        max_value: str | None = None,
        asset: str | None = None,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        """Proxy/pay an x402 URL through Thirdweb's public fetch API."""
        query = {
            "url": url,
            "from": from_address,
            "method": method.upper(),
        }
        if chain_id:
            query["chainId"] = chain_id
        if max_value:
            query["maxValue"] = max_value
        if asset:
            query["asset"] = asset

        request_headers = {"x-secret-key": self._api_key}
        if headers:
            request_headers.update(headers)
        response = await self._client.post(
            f"{self._base_url}/v1/payments/x402/fetch?{urlencode(query)}",
            headers=request_headers,
            json=body if isinstance(body, dict) else None,
            content=None if isinstance(body, dict) else body,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("result", data) if isinstance(data, dict) else {"result": data}

    async def discover_resources(self, **query: Any) -> dict[str, Any]:
        """Read Thirdweb x402 discovery resources."""
        params = {key: value for key, value in query.items() if value is not None}
        suffix = f"?{urlencode(params)}" if params else ""
        response = await self._client.get(
            f"{self._base_url}/v1/payments/x402/discovery/resources{suffix}",
            headers={"x-secret-key": self._api_key, "Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("result", data) if isinstance(data, dict) else {"result": data}

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        url = f"{self._base_url}/v1/payments/x402/verify"
        headers = {"x-secret-key": self._api_key, "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return VerifyResult(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        except Exception as e:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(e))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        url = f"{self._base_url}/v1/payments/x402/settle"
        headers = {"x-secret-key": self._api_key, "Content-Type": "application/json"}
        try:
            r = await self._client.post(
                url,
                json={
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                    "waitUntil": "confirmed",
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            data = data.get("result", data) if isinstance(data, dict) else {}
            return SettleResult(
                success=data.get("success", False),
                transaction=data.get("transaction"),
                network=data.get("network"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
            )
        except Exception as e:
            return SettleResult(
                success=False, transaction=None, network=None, error_reason=str(e), payer=None
            )

    async def get_supported_networks(self) -> list:
        headers = {"x-secret-key": self._api_key, "Accept": "application/json"}
        return await _fetch_supported_networks(
            client=self._client,
            base_url=self._base_url,
            headers=headers,
            candidate_paths=[
                "/v1/payments/x402/supported",
                "/v1/payments/x402/accepts",
            ],
        )

    async def close(self):
        await self._client.aclose()


class OmniClawExactFacilitator(BaseFacilitator):
    """
    OmniClaw self-hosted exact x402 facilitator.

    Use this for vendor SDK integrations that want to monetize routes with
    `client.sell(..., facilitator="omniclaw")` while running their own
    OmniClaw exact facilitator for verify/settle.
    """

    def __init__(
        self,
        api_key: str | None = None,
        environment: str = "testnet",
        timeout: float = 30.0,
        base_url: str | None = None,
        network_profile: str | None = None,
        network: str | None = None,
        asset: str | None = None,
        name: str = "omniclaw",
    ):
        import os

        import httpx

        from omniclaw.facilitator.networks import resolve_exact_settlement_network_profile

        profile = resolve_exact_settlement_network_profile(
            network_profile
            or os.environ.get("OMNICLAW_X402_EXACT_NETWORK_PROFILE")
            or os.environ.get("OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE")
            or os.environ.get("OMNICLAW_NETWORK")
            or "BASE-SEPOLIA"
        )
        self._environment = environment
        self._name = name
        self._base_url = (
            base_url
            or os.environ.get("OMNICLAW_X402_SELF_HOSTED_FACILITATOR_URL")
            or os.environ.get("OMNICLAW_X402_EXACT_FACILITATOR_URL")
            or "http://127.0.0.1:4022"
        ).rstrip("/")
        self._network = network or profile.caip2
        self._asset = asset or profile.default_asset_address
        if not self._asset:
            raise ValueError(f"No exact settlement asset configured for {profile.label}")
        self._asset_name = profile.default_asset_name
        self._asset_version = profile.default_asset_version
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def environment(self) -> str:
        return self._environment

    async def create_accepts(
        self,
        *,
        resource_url: str,
        method: str = "GET",
        network: str | None = None,
        price: str,
        server_wallet_address: str | None = None,
    ) -> list[dict[str, Any]]:
        if not server_wallet_address:
            raise ValueError("server_wallet_address is required")
        return [
            {
                "scheme": "exact",
                "network": network or self._network,
                "asset": self._asset,
                "amount": _parse_price_to_atomic(price),
                "payTo": server_wallet_address,
                "maxTimeoutSeconds": 300,
                "extra": {
                    "name": self._asset_name,
                    "version": self._asset_version,
                },
            }
        ]

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/verify",
                json={
                    "x402Version": 2,
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
            )
            response.raise_for_status()
            data = response.json()
            return VerifyResult(
                is_valid=data.get("isValid", data.get("is_valid", False)),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason") or data.get("invalid_reason"),
            )
        except Exception as exc:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(exc))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/settle",
                json={
                    "x402Version": 2,
                    "paymentPayload": payment_payload,
                    "paymentRequirements": payment_requirements,
                },
            )
            response.raise_for_status()
            data = response.json()
            return SettleResult(
                success=data.get("success", False),
                transaction=data.get("transaction"),
                network=data.get("network"),
                error_reason=data.get("errorReason") or data.get("error_reason"),
                payer=data.get("payer"),
            )
        except Exception as exc:
            return SettleResult(
                success=False,
                transaction=None,
                network=None,
                error_reason=str(exc),
                payer=None,
            )

    async def get_supported_networks(self) -> list[dict[str, Any]]:
        response = await self._client.get(f"{self._base_url}/supported")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get("kinds"), list):
            return data["kinds"]
        if isinstance(data, dict) and isinstance(data.get("supported"), list):
            return data["supported"]
        if isinstance(data, list):
            return data
        return [
            {
                "x402Version": 2,
                "scheme": "exact",
                "network": self._network,
                "extra": {"usdcAddress": self._asset},
            }
        ]

    async def close(self):
        await self._client.aclose()


# =============================================================================
# Factory Function
# =============================================================================


SUPPORTED_FACILITATORS = {
    "circle": CircleGatewayFacilitator,
    "coinbase": CoinbaseFacilitator,
    "ordern": OrderNFacilitator,
    "rbx": RBXFacilitator,
    "thirdweb": ThirdwebFacilitator,
    "omniclaw": OmniClawExactFacilitator,
    "selfhosted": OmniClawExactFacilitator,
    "self-hosted": OmniClawExactFacilitator,
}


def create_facilitator(
    provider: str = "circle",
    api_key: str | None = None,
    environment: str = "testnet",
    **kwargs,
) -> BaseFacilitator:
    """
    Factory to create a facilitator.

    Supports managed and self-hosted facilitators:
    - circle: Circle Gateway (https://circle.com)
    - coinbase: Coinbase CDP (https://coinbase.com)
    - ordern: OrderN (https://ordern.ai)
    - rbx: RBX (https://rbx.io)
    - thirdweb: Thirdweb (https://thirdweb.com)
    - omniclaw: OmniClaw self-hosted exact facilitator

    Args:
        provider: Facilitator name ("circle", "coinbase", "ordern", "rbx", "thirdweb", "omniclaw")
        api_key: API key for the facilitator
        environment: "testnet" or "mainnet"
        **kwargs: Additional options

    Returns:
        BaseFacilitator instance
    """
    import os

    provider = provider.lower()

    if provider in {"omniclaw", "selfhosted", "self-hosted"}:
        return OmniClawExactFacilitator(
            api_key=api_key,
            environment=environment,
            name=provider,
            **kwargs,
        )

    if api_key is not None:
        key = api_key
    elif provider == "thirdweb":
        key = (
            os.environ.get("THIRDWEB_SECRET_KEY")
            or os.environ.get("FACILITATOR_API_KEY")
            or os.environ.get("CIRCLE_API_KEY")
        )
    else:
        key = os.environ.get("FACILITATOR_API_KEY") or os.environ.get("CIRCLE_API_KEY")

    if not key:
        raise ValueError("api_key is required")

    if provider not in SUPPORTED_FACILITATORS:
        raise ValueError(
            f"Unknown facilitator: {provider}. Use: {', '.join(SUPPORTED_FACILITATORS.keys())}"
        )

    facilitator_class = SUPPORTED_FACILITATORS[provider]

    # CircleGatewayFacilitator uses circle_api_key, others use api_key
    if provider == "circle":
        return facilitator_class(circle_api_key=key, environment=environment, **kwargs)
    return facilitator_class(api_key=key, environment=environment, **kwargs)


__all__ = [
    "BaseFacilitator",
    "CircleGatewayFacilitator",
    "CoinbaseFacilitator",
    "OrderNFacilitator",
    "RBXFacilitator",
    "ThirdwebFacilitator",
    "OmniClawExactFacilitator",
    "VerifyResult",
    "SettleResult",
    "create_facilitator",
    "SUPPORTED_FACILITATORS",
]
