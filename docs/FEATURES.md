# OmniClaw Architecture and Features

This document explains how the Financial Policy Engine is structured and what each subsystem is responsible for.

## System Overview

OmniClaw is centered on the Financial Policy Engine, which wires together:

- configuration loading
- wallet management
- storage
- guards
- reservations and fund locking
- payment routing
- ledger persistence
- payment intents
- webhook verification
- optional trust evaluation

## Main Components

### `OmniClaw`

The top-level client in [client.py](../src/omniclaw/client.py). It exposes the public async Financial Policy Engine surface:

- wallet creation and lookup
- payment execution and simulation
- intent creation, confirmation, and cancellation
- guard management helpers
- ledger access
- trust access

### Wallet Service

The wallet layer in [wallet/service.py](../src/omniclaw/wallet/service.py) wraps Circle wallet operations:

- wallet set creation
- wallet creation
- wallet lookup and listing
- balance lookup
- transaction lookup
- direct transfers

Circle client initialization is lazy, so local tests and non-network flows do not require immediate provider calls at client construction time.

### Payment Router

The router in [payment/router.py](../src/omniclaw/payment/router.py) chooses an adapter based on recipient shape and destination chain.

Current routing:

- URL -> `NanopaymentProtocolAdapter` (Gateway x402), with fallback to `X402Adapter` if needed
- address + amount below micro-threshold -> `NanopaymentProtocolAdapter` (Gateway)
- address -> `TransferAdapter`
- `destination_chain` set -> `GatewayAdapter`

### Guards

The guard system in [guards/](../src/omniclaw/guards) is the primary spend-control layer.

Supported guard types:

- `BudgetGuard`
- `RateLimitGuard`
- `SingleTxGuard`
- `RecipientGuard`
- `ConfirmGuard`

Guard checks are integrated with reservation and commit/release behavior so failed payments do not permanently consume policy limits.

### Reservations and Fund Locks

OmniClaw separates two concerns:

- reservations hold spend capacity for intents
- fund locks serialize wallet execution to reduce double-spend races

Relevant modules:

- [intents/reservation.py](../src/omniclaw/intents/reservation.py)
- [ledger/lock.py](../src/omniclaw/ledger/lock.py)

### Ledger

The ledger in [ledger/](../src/omniclaw/ledger) tracks payment records and status transitions.

Typical use cases:

- internal observability
- transaction lookup
- reconciliation
- launch debugging

### Payment Intents

Payment intents provide an authorize/confirm flow:

1. simulate and validate
2. reserve funds
3. wait for confirmation or review
4. execute or cancel

Relevant modules:

- [intents/service.py](../src/omniclaw/intents/service.py)
- [intents/intent_facade.py](../src/omniclaw/intents/intent_facade.py)

### Trust Gate

Trust evaluation lives in [trust/](../src/omniclaw/trust). It is optional, but when enabled it can approve, hold, or block a payment using ERC-8004-related identity and reputation signals.

Current runtime rules:

- trust checks are optional by default
- explicit trust checks require a real `OMNICLAW_RPC_URL`
- simulation and payment execution follow the same trust gating rules

### Nanopayments (EIP-3009)

Nanopayments enable gas-free USDC transfers via Circle's Gateway nanopayments protocol, built on EIP-3009. They are designed for micro-transactions where gas costs would make regular transfers impractical.

**Gateway CAIP-2 derivation:** Gateway nanopayment CAIP-2 is derived from `OMNICLAW_NETWORK` via `network_to_caip2`. Only EVM networks are supported — non-EVM networks will raise a clear configuration error.

#### Architecture

The nanopayments stack is organized under [protocols/nanopayments/](../src/omniclaw/protocols/nanopayments/):

- `signing.py` — EIP-3009 signature creation (`EIP3009Signer`) and verification
- `types.py` — `PaymentRequirementsKind`, `PaymentPayload`, `SettleResponse`, `PaymentInfo`, `ResourceInfo`, `SupportedKind`, `GatewayBalance` types
- `client.py` — `NanopaymentClient` wrapping Circle's Gateway API (settle, verify, get_supported, check_balance)
- `keys.py` — key encryption utilities (legacy; not used in direct-key mode)
- `middleware.py` — `GatewayMiddleware` (seller-side x402 gate, `@agent.sell()` equivalent)
- `adapter.py` — `NanopaymentAdapter` (buyer-side payment execution)
- `wallet.py` — `GatewayWalletManager` (on-chain deposit/withdraw via `depositWithAuthorization`)
- `exceptions.py` — `InsufficientBalanceError`, `SettlementError`, etc.

#### Payment Flow

1. **Buyer** creates a `PaymentRequirementsKind` (network, amount, seller address)
2. **Buyer** signs with `EIP3009Signer` → `PaymentPayload` (off-chain, no gas)
3. **Buyer** base64-encodes payload → sends as `PAYMENT-SIGNATURE` header
4. **Seller** gateway receives header → calls `gateway.handle(request_headers, price)`
5. **Seller** gateway calls `client.settle(payload, requirements)` → Circle settles on-chain
6. **Result** is `SettleResponse(success, transaction, payer, error_reason)`

The on-chain settlement is batched — multiple nanopayments settle in a single transaction, so gas costs are amortized across many payments.

#### Buyer vs Seller

- **Buyer**: Uses `NanopaymentAdapter` and `NanopaymentClient` to create and send payments via `client.pay()`
- **Seller**: Uses `GatewayMiddleware` and `@omniclaw.sell()` to protect FastAPI endpoints

#### Key Management

Nanopayment signing uses a single direct private key configured via `OMNICLAW_PRIVATE_KEY`.

#### OmniClaw Integration

`OmniClaw` wires nanopayments into the Financial Policy Engine surface:

- `client.nanopayment_adapter` → `NanopaymentAdapter` for buyer payments
- `client.gateway()` → `GatewayMiddleware` for seller endpoints
- `client.sell(price)` → FastAPI `Depends()` for `@agent.sell()`
- `client.current_payment()` → `PaymentInfo` within decorated routes
- `client.get_gateway_balance()` → gateway wallet balance
- `client.configure_nanopayments()` → auto-topup settings

Relevant modules:

- [protocols/nanopayments/middleware.py](../src/omniclaw/protocols/nanopayments/middleware.py)
- [protocols/nanopayments/adapter.py](../src/omniclaw/protocols/nanopayments/adapter.py)
- [protocols/nanopayments/keys.py](../src/omniclaw/protocols/nanopayments/keys.py)
- [protocols/nanopayments/client.py](../src/omniclaw/protocols/nanopayments/client.py)

### Storage

Storage backends live in [storage/](../src/omniclaw/storage).

Supported backends:

- in-memory storage for tests and simple local runs
- Redis for shared, concurrent, or production-like execution

Canonical Redis env:

```env
OMNICLAW_STORAGE_BACKEND=redis
OMNICLAW_REDIS_URL=redis://localhost:6379
```

## Environment Model

Core environment variables:

```env
CIRCLE_API_KEY=...
OMNICLAW_NETWORK=ARC-TESTNET
```

Optional:

```env
OMNICLAW_STORAGE_BACKEND=memory
OMNICLAW_REDIS_URL=redis://localhost:6379
OMNICLAW_LOG_LEVEL=INFO
OMNICLAW_RPC_URL=https://...
OMNICLAW_DEFAULT_WALLET=wallet-id
OMNICLAW_DAILY_BUDGET=100.00
OMNICLAW_HOURLY_BUDGET=20.00
OMNICLAW_TX_LIMIT=50.00
OMNICLAW_RATE_LIMIT_PER_MIN=5
OMNICLAW_WHITELISTED_RECIPIENTS=0xabc,0xdef
OMNICLAW_CONFIRM_ALWAYS=false
OMNICLAW_CONFIRM_THRESHOLD=500.00
```

## Execution Sequence

For a typical `pay()` call, the Financial Policy Engine does the following:

1. validate arguments
2. optionally evaluate trust
3. create a ledger entry
4. reserve guards
5. acquire wallet fund lock
6. verify available balance after reservations
7. pass through the router and chosen adapter
8. commit or release guard reservations
9. update ledger status
10. release wallet lock

## Launch-Focused Recommendations

- Use Redis for any multi-agent or concurrent environment.
- Treat `simulate()` as part of your pre-execution workflow for higher-risk payments.
- Use payment intents for any approval or review-dependent flow.
- Configure `OMNICLAW_RPC_URL` only when you actually want trust evaluation available.
- Keep environment names and network selection explicit in deployment configs.
