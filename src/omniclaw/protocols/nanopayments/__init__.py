"""
OmniClaw Nanopayments Module.

Provides gasless USDC micro-payments via Circle Gateway batched settlement.
Built on EIP-3009 TransferWithAuthorization for off-chain payment authorization.

Architecture:
    - EIP3009Signer: Cryptographic signing of payment authorizations
    - NanopaymentClient: Circle Gateway REST API wrapper
    - NanopaymentAdapter: Buyer-side payment execution
    - GatewayMiddleware: Seller-side x402 payment gate
    - GatewayWalletManager: On-chain deposit/withdraw operations

Usage:
    Buyer side:
        result = await nanopayment_adapter.pay_x402_url(url="https://api.provider.com/data")

    Seller side:
        @app.get("/premium")
        async def premium(payment=Depends(gateway.require("$0.001"))):
            return {"data": "paid content", "paid_by": payment.payer}
"""

from omniclaw.protocols.nanopayments.constants import (
    CAIP2_TO_CIRCLE_DOMAIN,
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_SCHEME,
    CIRCLE_BATCHING_VERSION,
    CIRCLE_DOMAIN_TO_CAIP2,
    DEFAULT_GATEWAY_AUTO_TOPUP_AMOUNT,
    DEFAULT_GATEWAY_AUTO_TOPUP_THRESHOLD,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_MICRO_PAYMENT_THRESHOLD_USDC,
    DEFAULT_VALID_BEFORE_SECONDS,
    GATEWAY_API_MAINNET,
    GATEWAY_API_TESTNET,
    GATEWAY_BALANCES_PATH,
    GATEWAY_INFO_PATH,
    GATEWAY_X402_SETTLE_PATH,
    GATEWAY_X402_SUPPORTED_PATH,
    GATEWAY_X402_VERIFY_PATH,
    MAX_TIMEOUT_SECONDS,
    MIN_VALID_BEFORE_SECONDS,
    SUPPORTED_NETWORKS_CACHE_TTL_SECONDS,
    USDC_DECIMAL_PLACES,
    X402_VERSION,
)

from omniclaw.protocols.nanopayments.exceptions import (
    AuthorizationExpiredError,
    AuthorizationNotYetValidError,
    DepositError,
    DuplicateKeyAliasError,
    ERC20ApprovalError,
    GatewayAPIError,
    GatewayConnectionError,
    GatewayTimeoutError,
    GatewayWalletError,
    InsufficientBalanceError,
    InsufficientGatewayBalanceError,
    InvalidPriceError,
    InvalidPrivateKeyError,
    InvalidSignatureError,
    KeyEncryptionError,
    KeyManagementError,
    KeyNotFoundError,
    MiddlewareError,
    NanopaymentError,
    NanopaymentNotInitializedError,
    NetworkMismatchError,
    NoDefaultKeyError,
    NoNetworksAvailableError,
    NonceReusedError,
    PaymentRequiredError,
    SettlementError,
    SignatureVerificationError,
    SigningError,
    UnsupportedNetworkError,
    UnsupportedSchemeError,
    VerificationError,
    WithdrawError,
)

from omniclaw.protocols.nanopayments.types import (
    DepositResult,
    EIP3009Authorization,
    GatewayBalance,
    NanopaymentResult,
    PaymentInfo,
    PaymentPayload,
    PaymentPayloadInner,
    PaymentRequirements,
    PaymentRequirementsExtra,
    PaymentRequirementsKind,
    SettleResponse,
    SupportedKind,
    VerifyResponse,
    WithdrawResult,
)

from omniclaw.protocols.nanopayments.client import (
    NanopaymentClient,
    NanopaymentHTTPClient,
)

from omniclaw.protocols.nanopayments.wallet import GatewayWalletManager

from omniclaw.protocols.nanopayments.middleware import (
    GatewayMiddleware,
    PaymentRequiredHTTPError,
    parse_price,
)

from omniclaw.protocols.nanopayments.adapter import (
    NanopaymentAdapter,
    NanopaymentProtocolAdapter,
)

__all__ = [
    # Constants
    "CAIP2_TO_CIRCLE_DOMAIN",
    "CIRCLE_BATCHING_NAME",
    "CIRCLE_BATCHING_SCHEME",
    "CIRCLE_BATCHING_VERSION",
    "CIRCLE_DOMAIN_TO_CAIP2",
    "DEFAULT_GATEWAY_AUTO_TOPUP_AMOUNT",
    "DEFAULT_GATEWAY_AUTO_TOPUP_THRESHOLD",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_MICRO_PAYMENT_THRESHOLD_USDC",
    "DEFAULT_VALID_BEFORE_SECONDS",
    "GATEWAY_API_MAINNET",
    "GATEWAY_API_TESTNET",
    "GATEWAY_BALANCES_PATH",
    "GATEWAY_INFO_PATH",
    "GATEWAY_X402_SETTLE_PATH",
    "GATEWAY_X402_SUPPORTED_PATH",
    "GATEWAY_X402_VERIFY_PATH",
    "MAX_TIMEOUT_SECONDS",
    "MIN_VALID_BEFORE_SECONDS",
    "SUPPORTED_NETWORKS_CACHE_TTL_SECONDS",
    "USDC_DECIMAL_PLACES",
    "X402_VERSION",
    # Types
    "DepositResult",
    "EIP3009Authorization",
    "GatewayBalance",
    "NanopaymentResult",
    "PaymentInfo",
    "PaymentPayload",
    "PaymentPayloadInner",
    "PaymentRequirements",
    "PaymentRequirementsExtra",
    "PaymentRequirementsKind",
    "SettleResponse",
    "SupportedKind",
    "VerifyResponse",
    "WithdrawResult",
    # Client
    "NanopaymentClient",
    "NanopaymentHTTPClient",
    # Wallet
    "GatewayWalletManager",
    # Adapter
    "NanopaymentAdapter",
    # Middleware
    "GatewayMiddleware",
    "PaymentRequiredHTTPError",
    "parse_price",
    # Adapter wrapper
    "NanopaymentProtocolAdapter",
    # Exceptions
    "NanopaymentNotInitializedError",
    "NanopaymentError",
    "AuthorizationExpiredError",
    "AuthorizationNotYetValidError",
    "DepositError",
    "DuplicateKeyAliasError",
    "ERC20ApprovalError",
    "GatewayAPIError",
    "GatewayConnectionError",
    "GatewayTimeoutError",
    "GatewayWalletError",
    "InsufficientBalanceError",
    "InsufficientGatewayBalanceError",
    "InvalidPriceError",
    "InvalidPrivateKeyError",
    "InvalidSignatureError",
    "KeyEncryptionError",
    "KeyManagementError",
    "KeyNotFoundError",
    "MiddlewareError",
    "NetworkMismatchError",
    "NoDefaultKeyError",
    "NoNetworksAvailableError",
    "NonceReusedError",
    "PaymentRequiredError",
    "SettlementError",
    "SignatureVerificationError",
    "SigningError",
    "UnsupportedNetworkError",
    "UnsupportedSchemeError",
    "VerificationError",
    "WithdrawError",
]
