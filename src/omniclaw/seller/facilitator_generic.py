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
from typing import Any

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
    Thirdweb x402 Facilitator.

    https://thirdweb.com
    """

    THIRDWEB_TESTNET = "https://gateway.thirdweb-test.com"
    THIRDWEB_MAINNET = "https://gateway.thirdweb.com"

    def __init__(self, api_key: str, environment: str = "testnet", timeout: float = 30.0):
        import httpx

        self._api_key = api_key
        self._environment = environment
        self._timeout = timeout
        self._base_url = (
            self.THIRDWEB_TESTNET if environment == "testnet" else self.THIRDWEB_MAINNET
        )
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

    async def verify(self, payment_payload: dict, payment_requirements: dict) -> VerifyResult:
        url = f"{self._base_url}/api/v1/x402/verify"
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
            return VerifyResult(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        except Exception as e:
            return VerifyResult(is_valid=False, payer=None, invalid_reason=str(e))

    async def settle(self, payment_payload: dict, payment_requirements: dict) -> SettleResult:
        url = f"{self._base_url}/api/v1/x402/settle"
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
            candidate_paths=["/api/v1/x402/supported", "/v1/x402/supported", "/x402/supported"],
        )

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
}


def create_facilitator(
    provider: str = "circle",
    api_key: str | None = None,
    environment: str = "testnet",
    **kwargs,
) -> BaseFacilitator:
    """
    Factory to create a facilitator.

    Supports top 5 facilitators:
    - circle: Circle Gateway (https://circle.com)
    - coinbase: Coinbase CDP (https://coinbase.com)
    - ordern: OrderN (https://ordern.ai)
    - rbx: RBX (https://rbx.io)
    - thirdweb: Thirdweb (https://thirdweb.com)

    Args:
        provider: Facilitator name ("circle", "coinbase", "ordern", "rbx", "thirdweb")
        api_key: API key for the facilitator
        environment: "testnet" or "mainnet"
        **kwargs: Additional options

    Returns:
        BaseFacilitator instance
    """
    import os

    if api_key is not None:
        key = api_key
    else:
        key = os.environ.get("FACILITATOR_API_KEY") or os.environ.get("CIRCLE_API_KEY")

    if not key:
        raise ValueError("api_key is required")

    provider = provider.lower()

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
    "VerifyResult",
    "SettleResult",
    "create_facilitator",
    "SUPPORTED_FACILITATORS",
]
