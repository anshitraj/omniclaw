# OmniClaw API Reference

This is the public API reference for the Financial Policy Engine. It focuses on the API surface users are expected to call directly.

## Top-Level Imports

Common imports from [src/omniclaw/__init__.py](../src/omniclaw/__init__.py):

```python
from omniclaw import (
    OmniClaw,
    Network,
    FeeLevel,
    PaymentMethod,
    PaymentStatus,
    PaymentIntentStatus,
    quick_setup,
)
```

## Environment Contract

Required:

```env
CIRCLE_API_KEY=...
OMNICLAW_NETWORK=ETH-SEPOLIA  # or ARC-TESTNET
# Direct-key mode (recommended for agents / nanopayments)
OMNICLAW_PRIVATE_KEY=0x...
```

If you are using Circle developer-controlled wallets directly, provide:
```
ENTITY_SECRET=...
```

Optional:

```env
OMNICLAW_DEFAULT_WALLET=wallet-id
OMNICLAW_LOG_LEVEL=INFO
OMNICLAW_ENV=development
OMNICLAW_RPC_URL=https://...
OMNICLAW_STORAGE_BACKEND=memory
OMNICLAW_REDIS_URL=redis://localhost:6379
OMNICLAW_DAILY_BUDGET=100.00
OMNICLAW_HOURLY_BUDGET=20.00
OMNICLAW_TX_LIMIT=50.00
OMNICLAW_RATE_LIMIT_PER_MIN=5
OMNICLAW_WHITELISTED_RECIPIENTS=0xabc,0xdef
OMNICLAW_CONFIRM_ALWAYS=false
OMNICLAW_CONFIRM_THRESHOLD=500.00
```

## Setup Utilities

Defined in [onboarding.py](../src/omniclaw/onboarding.py).

### `quick_setup(api_key, env_path=".env", network="ARC-TESTNET")`

One-time onboarding helper that generates and registers an entity secret and writes an env file (optional).

### `generate_entity_secret()` (optional)

Returns a 64-character hex entity secret (manual setup only).

### `register_entity_secret(api_key, entity_secret, recovery_dir=None)` (optional)

Registers an entity secret with Circle and downloads the recovery file (manual setup only).

### `create_env_file(api_key, entity_secret, env_path=".env", network="ARC-TESTNET", overwrite=False)` (optional)

Writes the basic OmniClaw env file (manual setup only).

### `verify_setup()`

Returns a readiness summary for the local environment.

### `doctor(api_key=None, entity_secret=None)`

Returns a diagnostic summary covering:

- Circle SDK availability
- API key presence
- environment entity secret presence
- managed config entity secret presence
- recovery-file presence

### `print_doctor_status(api_key=None, entity_secret=None)`

Prints the same diagnostic state in a human-readable format.

## `OmniClaw`

Defined in [client.py](../src/omniclaw/client.py).

### Constructor

```python
OmniClaw(
    circle_api_key: str | None = None,
    entity_secret: str | None = None,
    network: Network = Network.ARC_TESTNET,
    log_level: int | str | None = None,
    trust_policy: TrustPolicy | str | None = None,
    rpc_url: str | None = None,
)
```

### Properties

- `config`
- `wallet`
- `guards`
- `trust`
- `intent`
- `intents`
- `ledger`
- `webhooks`
- `nanopayment_adapter` — NanopaymentAdapter for buyer-side nanopayments

### Wallet Methods

```python
await client.create_wallet(
    blockchain=None,
    wallet_set_id=None,
    account_type=AccountType.EOA,
    name=None,
)

await client.create_agent_wallet(
    agent_name,
    blockchain=None,
    apply_default_guards=True,
)

await client.create_wallet_set(name=None)
await client.list_wallets(wallet_set_id=None)
await client.list_wallet_sets()
await client.get_wallet(wallet_id)
await client.get_wallet_set(wallet_set_id)
await client.get_balance(wallet_id)
await client.list_transactions(wallet_id=None, blockchain=None)
```

### Payment Methods

```python
await client.pay(
    wallet_id,
    recipient,
    amount,
    destination_chain=None,
    wallet_set_id=None,
    purpose=None,
    idempotency_key=None,
    fee_level=FeeLevel.MEDIUM,
    strategy=PaymentStrategy.RETRY_THEN_FAIL,
    skip_guards=False,
    check_trust=None,
    consume_intent_id=None,
    metadata=None,
    wait_for_completion=False,
    timeout_seconds=None,
    **kwargs,
)
```

```python
await client.simulate(
    wallet_id,
    recipient,
    amount,
    wallet_set_id=None,
    check_trust=None,
    skip_guards=False,
    **kwargs,
)
```

Other helpers:

```python
client.can_pay(recipient)
client.detect_method(recipient)
await client.batch_pay(requests, concurrency=5)
await client.sync_transaction(entry_id)
```

### Payment Intent Methods

```python
await client.create_payment_intent(
    wallet_id,
    recipient,
    amount,
    purpose=None,
    expires_in=None,
    idempotency_key=None,
    skip_guards=False,
    check_trust=None,
    **kwargs,
)

await client.confirm_payment_intent(intent_id)
await client.get_payment_intent(intent_id)
await client.cancel_payment_intent(intent_id, reason=None)
```

### Guard Helper Methods

```python
await client.add_budget_guard(wallet_id, daily_limit=None, hourly_limit=None, total_limit=None, name="budget")
await client.add_budget_guard_for_set(wallet_set_id, daily_limit=None, hourly_limit=None, total_limit=None, name="budget")
await client.add_single_tx_guard(wallet_id, max_amount=None, min_amount=None, name="single_tx")
await client.add_recipient_guard(wallet_id, mode="whitelist", addresses=None, patterns=None, domains=None, name="recipient")
await client.add_recipient_guard_for_set(wallet_set_id, mode="whitelist", addresses=None, patterns=None, domains=None, name="recipient")
await client.add_rate_limit_guard(wallet_id, max_per_minute=None, max_per_hour=None, max_per_day=None, name="rate_limit")
await client.add_rate_limit_guard_for_set(wallet_set_id, max_per_minute=None, max_per_hour=None, max_per_day=None, name="rate_limit")
await client.add_confirm_guard(wallet_id, threshold=None, always_confirm=False, name="confirm")
await client.add_confirm_guard_for_set(wallet_set_id, threshold=None, always_confirm=False, name="confirm")
await client.list_guards(wallet_id)
await client.list_guards_for_set(wallet_set_id)
```

### Nanopayments Methods

Nanopayments use EIP-3009 for gas-free USDC transfers on Circle Gateway. They work alongside regular payments — micro-transactions route through the gateway while larger payments use standard transfers.

#### Seller: Receiving Nanopayments

```python
# Get the GatewayMiddleware for protecting endpoints
await client.gateway()  # -> GatewayMiddleware

# Decorator factory for marking paid FastAPI routes
client.sell(price: str)  # -> Depends() for FastAPI

# Get current payment info inside a @sell() decorated route
client.current_payment()  # -> PaymentInfo(payer, amount, network, transaction)
```

Example (FastAPI seller):

```python
from fastapi import Depends

@app.get("/premium")
async def premium(payment=Depends(omniclaw.sell("$0.001"))):
    payment_info = omniclaw.current_payment()
    return {"data": "paid content", "paid_by": payment_info.payer}
```

#### Buyer: Sending Nanopayments

```python
# Execute a nanopayment to a seller's address
await client.pay(
    wallet_id=wallet.id,
    recipient="0xSellerAddress",
    amount="0.001",  # Small amount - uses gateway nanopayment
)
# Routes to Circle Gateway nanopayment if amount < nanopayments_micro_threshold
```

#### Gateway Wallet Management

```python
# Get gateway balance
await client.get_gateway_balance(wallet_id="wallet-id")
# -> GatewayBalance(total, available, formatted_total, formatted_available)

# Deposit USDC to gateway wallet (enables receiving nanopayments)
await client.deposit_to_gateway(
    wallet_id="wallet-id",
    amount_usdc="10.00",
)

# Withdraw USDC from gateway wallet
await client.withdraw_from_gateway(
    wallet_id="wallet-id",
    amount_usdc="5.00",
    destination_chain=None,  # Optional: withdraw to another chain
    recipient="0xDestination",  # Optional: specific recipient
)

# Configure auto-topup for gateway balance
client.configure_nanopayments(
    auto_topup_enabled=True,
    auto_topup_threshold="1.00",
    auto_topup_amount="10.00",
    wallet_manager=gateway_wallet_manager,
)
```

#### Agent Creation

```python
# Create an agent wallet
agent_wallet = await client.create_agent(
    agent_name="data-agent",
)
```

### Nanopayments Environment Variables

```env
OMNICLAW_NANOPAYMENTS_ENABLED=true
OMNICLAW_NANOPAYMENTS_ENVIRONMENT=testnet  # or "mainnet"
OMNICLAW_NANOPAYMENTS_MICRO_THRESHOLD=1.00
OMNICLAW_NANOPAYMENTS_AUTO_TOPUP=true
OMNICLAW_NANOPAYMENTS_TOPUP_THRESHOLD=1.00
OMNICLAW_NANOPAYMENTS_TOPUP_AMOUNT=10.00
# Nanopayments network is derived from OMNICLAW_NETWORK (EVM chain)
```

## `WalletService`

Accessible through `client.wallet`.

Use it when you want direct wallet operations instead of the higher-level client helpers.

Primary methods:

```python
create_wallet_set(name)
list_wallet_sets()
get_wallet_set(wallet_set_id)
create_wallet(wallet_set_id, blockchain=None, account_type=AccountType.EOA)
create_wallets(wallet_set_id, count, blockchain=None, account_type=AccountType.EOA)
setup_agent_wallet(agent_name, blockchain=None)
get_wallet(wallet_id)
list_wallets(wallet_set_id=None, blockchain=None)
list_transactions(wallet_id=None, blockchain=None)
get_balances(wallet_id)
get_usdc_balance(wallet_id)
get_usdc_balance_amount(wallet_id)
transfer(
    wallet_id,
    destination_address,
    amount,
    fee_level=FeeLevel.MEDIUM,
    idempotency_key=None,
    check_balance=True,
    wait_for_completion=False,
    timeout_seconds=None,
)
```

## `WebhookParser`

Accessible through `client.webhooks`.

Primary methods:

```python
WebhookParser(verification_key=None)
verify_signature(payload, headers)
handle(payload, headers)
```

When verification is enabled, pass raw payload data and headers so signature verification happens before JSON parsing.

## Important Runtime Rules

- `pay()` and `simulate()` are async.
- Wallet creation helpers on `OmniClaw` are async.
- Wallet-service methods are mixed: some are sync, some are async; prefer `OmniClaw` unless you need lower-level access.
- Explicit trust checking requires a real `OMNICLAW_RPC_URL`.
- Redis configuration uses `OMNICLAW_REDIS_URL` only.
- `OmniClaw` now syncs the active entity secret into the managed config store when possible.
- Managed config lives under the platform-specific OmniClaw config directory, such as `~/.config/omniclaw/` on Linux.

## Error Categories

Important exported exceptions:

- `ConfigurationError`
- `WalletError`
- `PaymentError`
- `GuardError`
- `ProtocolError`
- `InsufficientBalanceError`
- `NetworkError`
- `X402Error`
- `ValidationError`
- `NanopaymentNotInitializedError`
- `InsufficientBalanceError`
- `SettlementError`
- `NoDefaultKeyError`
