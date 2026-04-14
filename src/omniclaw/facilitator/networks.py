from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from x402.schemas import AssetAmount

from omniclaw.core.cctp_constants import USDC_CONTRACTS
from omniclaw.core.types import Network, network_to_caip2, normalize_network


@dataclass(frozen=True)
class ExactSettlementNetworkProfile:
    network: Network
    caip2: str
    label: str
    default_rpc_url: str | None = None
    explorer_base_url: str | None = None
    default_asset_address: str | None = None
    default_asset_name: str = "USDC"
    default_asset_version: str = "2"
    default_asset_decimals: int = 6


_DEFAULT_PROFILE_METADATA: dict[Network, dict[str, str | None]] = {
    Network.ETH: {
        "default_rpc_url": "https://ethereum-rpc.publicnode.com",
        "explorer_base_url": "https://etherscan.io/tx/",
    },
    Network.ETH_SEPOLIA: {
        "default_rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
        "explorer_base_url": "https://sepolia.etherscan.io/tx/",
    },
    Network.BASE: {
        "default_rpc_url": "https://mainnet.base.org",
        "explorer_base_url": "https://basescan.org/tx/",
    },
    Network.BASE_SEPOLIA: {
        "default_rpc_url": "https://sepolia.base.org",
        "explorer_base_url": "https://sepolia.basescan.org/tx/",
    },
    Network.OP: {
        "default_rpc_url": "https://mainnet.optimism.io",
        "explorer_base_url": "https://optimistic.etherscan.io/tx/",
    },
    Network.OP_SEPOLIA: {
        "default_rpc_url": "https://sepolia.optimism.io",
        "explorer_base_url": "https://sepolia-optimism.etherscan.io/tx/",
    },
    Network.ARB: {
        "default_rpc_url": "https://arb1.arbitrum.io/rpc",
        "explorer_base_url": "https://arbiscan.io/tx/",
    },
    Network.ARB_SEPOLIA: {
        "default_rpc_url": "https://sepolia-rollup.arbitrum.io/rpc",
        "explorer_base_url": "https://sepolia.arbiscan.io/tx/",
    },
    Network.UNI: {
        "default_rpc_url": "https://mainnet.unichain.org",
        "explorer_base_url": "https://uniscan.xyz/tx/",
    },
    Network.UNI_SEPOLIA: {
        "default_rpc_url": "https://sepolia.unichain.org",
        "explorer_base_url": "https://sepolia.uniscan.xyz/tx/",
    },
    Network.ARC_TESTNET: {
        "default_rpc_url": "https://rpc.testnet.arc.network",
        "explorer_base_url": "https://testnet.arcscan.app/tx/",
    },
}


def resolve_exact_settlement_network_profile(
    network: Network | str | None,
) -> ExactSettlementNetworkProfile:
    normalized = normalize_network(network or Network.BASE_SEPOLIA)
    if normalized is None:
        raise ValueError("Exact settlement network profile cannot be resolved from None")
    if not normalized.is_evm():
        raise ValueError(f"Exact settlement only supports EVM networks, got: {normalized.value}")

    caip2 = network_to_caip2(normalized)
    if not caip2:
        raise ValueError(f"No CAIP-2 mapping available for exact settlement: {normalized.value}")

    metadata = _DEFAULT_PROFILE_METADATA.get(normalized, {})
    return ExactSettlementNetworkProfile(
        network=normalized,
        caip2=caip2,
        label=normalized.value,
        default_rpc_url=metadata.get("default_rpc_url"),
        explorer_base_url=metadata.get("explorer_base_url"),
        default_asset_address=USDC_CONTRACTS.get(normalized.value),
    )


def build_exact_asset_amount(
    *,
    profile: ExactSettlementNetworkProfile,
    decimal_amount: float | str | Decimal,
    network: str,
) -> AssetAmount | None:
    if network != profile.caip2 or not profile.default_asset_address:
        return None

    amount_decimal = Decimal(str(decimal_amount))
    scaled = amount_decimal * (Decimal(10) ** profile.default_asset_decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"Amount {decimal_amount} cannot be represented with "
            f"{profile.default_asset_decimals} decimals"
        )

    return AssetAmount(
        amount=str(int(scaled)),
        asset=profile.default_asset_address,
        extra={
            "name": profile.default_asset_name,
            "version": profile.default_asset_version,
        },
    )
