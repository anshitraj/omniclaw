# OmniClaw Financial Policy Engine Usage Guide

This guide covers common workflows for the Financial Policy Engine without repeating the full architecture or every method signature.

## 1. Initialize the Client

```python
from omniclaw import OmniClaw, Network

client = OmniClaw(network=Network.ARC_TESTNET)
```

With environment variables:

```env
CIRCLE_API_KEY=your_circle_api_key
OMNICLAW_NETWORK=ARC-TESTNET
```

Optional runtime settings:

```env
OMNICLAW_STORAGE_BACKEND=redis
OMNICLAW_REDIS_URL=redis://localhost:6379
OMNICLAW_LOG_LEVEL=DEBUG
OMNICLAW_RPC_URL=https://your-rpc-provider

# Nanopayments network is derived from OMNICLAW_NETWORK (EVM chain)
```

### Entity Secret

You do not need to set `ENTITY_SECRET` manually. It is auto-generated and registered on first run when `CIRCLE_API_KEY` is available.

Linux recovery-file location:

```text
~/.config/omniclaw/
```

This matters because Circle entity secret registration is effectively a one-time setup per account until you recover or reset it.

Run the built-in diagnostic command to check the full state:

```bash
omniclaw doctor
```

## Testing with Real Funds

To test payments with real USDC on testnet:

**1. Configure for Base Sepolia:**

```env
OMNICLAW_NETWORK=BASE-SEPOLIA
OMNICLAW_RPC_URL=https://sepolia.base.org
```

**2. Get testnet tokens:**

- **ETH (for gas):** https://faucets.chain.link/base-sepolia
- **USDC (for payments):** https://faucet.circle.com/ → Select Base Sepolia → Send 20 USDC

**3. Get payment addresses:**

```python
wallet_set, wallet = await client.create_agent_wallet("my-agent")

# Circle wallet (for transfers)
circle_address = wallet.address

# Nano/Gateway (for nanopayments - EIP-3009)
nano_address = client.nanopayment_adapter.address
```

**4. Test a payment:**

```python
result = await client.pay(
    wallet_id=wallet.id,
    recipient="0xRecipientAddress",
    amount="0.01",  # 1 cent USDC
)
```

## 2. Create a Wallet

Fastest path:

```python
wallet_set, wallet = await client.create_agent_wallet("agent-007")
```

Manual path:

```python
wallet_set = await client.create_wallet_set("ops-wallets")
wallet = await client.create_wallet(
    wallet_set_id=wallet_set.id,
    blockchain=Network.ETH,
)
```

Common wallet operations:

```python
wallets = await client.list_wallets(wallet_set_id=wallet_set.id)
wallet_info = await client.get_wallet(wallet.id)
balance = await client.get_balance(wallet.id)

# Get payment address (where to fund with USDC)
payment_address = await client.get_payment_address(wallet.id)

# Get detailed balance (available + reserved for intents)
detailed = await client.get_detailed_balance(wallet.id)
print(f"Available: {detailed['available']}, Reserved: {detailed['reserved']}")

transactions = await client.list_transactions(wallet_id=wallet.id)
```

## 3. Add Safety Guards

```python
await client.add_budget_guard(wallet.id, daily_limit="100.00", hourly_limit="20.00")
await client.add_rate_limit_guard(wallet.id, max_per_minute=5)
await client.add_single_tx_guard(wallet.id, max_amount="25.00")
await client.add_recipient_guard(
    wallet.id,
    mode="whitelist",
    addresses=["0xTrustedRecipient"],
    domains=["api.openai.com"],
)
await client.add_confirm_guard(wallet.id, threshold="500.00")
```

Wallet-set guard helpers apply the same logic across all wallets in a set.

```python
await client.add_budget_guard_for_set(wallet_set.id, daily_limit="500.00")
await client.add_rate_limit_guard_for_set(wallet_set.id, max_per_hour=100)
```

## 4. Execute a Payment

```python
result = await client.pay(
    wallet_id=wallet.id,
    recipient="0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0",
    amount="10.50",
    purpose="vendor payment",
)
```

Key runtime arguments:

- `wallet_id`: required source wallet
- `recipient`: blockchain address or URL
- `amount`: USDC amount
- `destination_chain`: set for cross-chain flows
- `purpose`: audit-friendly note
- `idempotency_key`: caller-controlled dedupe key
- `skip_guards`: bypass guards, only for special cases
- `check_trust`: `None`, `True`, or `False`
- `wait_for_completion`: wait for provider confirmation when supported

## 5. Understand Routing

OmniClaw routes automatically:

- URL -> Gateway nanopayments (x402), with fallback to x402 direct if needed
- address + amount below micro-threshold -> Gateway nanopayments
- address -> direct transfer
- address + `destination_chain` -> gateway/cross-chain

Examples:

```python
await client.pay(wallet_id=wallet.id, recipient="0xRecipient", amount="5.00")
await client.pay(wallet_id=wallet.id, recipient="https://api.vendor.com/paywall", amount="0.05")
await client.pay(
    wallet_id=wallet.id,
    recipient="0xRecipientOnBase",
    amount="20.00",
    destination_chain=Network.BASE,
)
```

## 6. Simulate Before Sending

```python
sim = await client.simulate(
    wallet_id=wallet.id,
    recipient="0xRecipient",
    amount="25.00",
)

if sim.would_succeed:
    print(sim.route)
else:
    print(sim.reason)
```

Simulation checks:

- balance after reservations
- guard outcomes
- trust outcome when enabled
- adapter suitability

## 7. Use Payment Intents for Approval Flows

```python
intent = await client.create_payment_intent(
    wallet_id=wallet.id,
    recipient="0xRecipient",
    amount="250.00",
    purpose="high-value purchase",
)
```

Confirm later:

```python
result = await client.confirm_payment_intent(intent.id)
```

Cancel if needed:

```python
await client.cancel_payment_intent(intent.id, reason="approval denied")
```

Use intents when you need:

- human review
- delayed execution
- serialized approval flows
- explicit reservation of spendable balance

## 8. Receive Nanopayments as a Seller

Nanopayments use EIP-3009 for gas-free USDC transfers via Circle Gateway batch settlement. As a seller, you protect FastAPI endpoints so buyers pay before receiving content.

### Quick Start (6 lines!)

```python
from fastapi import FastAPI, Depends
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

# Create seller account - ONE CALL does everything
wallet_set, wallet = await client.create_agent_wallet("my-saas-product")

# Protect your endpoint - that's it!
@app.get("/premium-data")
async def get_premium(payment=Depends(client.sell("$0.01"))):
    return {
        "data": "premium content",
        "paid_by": payment.payer,
    }
```

### How It Works

1. **Circle Gateway batch settlement** - All nanopayments are automatically batched and settled via EIP-3009
2. **Gasless for buyers** - Buyers don't pay gas fees
3. **Seller receives USDC in Gateway** - Instant settlement to your Gateway wallet

### Get Payment Address

```python
# Get address for buyers to pay to
payment_address = await client.get_payment_address(wallet.id)
```

### Check Earnings

```python
# Check your Gateway balance (USDC received from buyers)
balance = await client.get_gateway_balance(wallet.id)
print(f"Total: {balance.formatted_total}")
print(f"Available: {balance.formatted_available}")
```

### Withdraw Earnings

```python
# Withdraw to your Circle wallet
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="50.00",
)

# Or withdraw to another chain (cross-chain via CCTP)
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="25.00",
    destination_chain="eip155:1",  # Ethereum mainnet
    recipient="0xYourEthAddress",
)
```

### Why OmniClaw vs Raw x402?

**OmniClaw (SIMPLE - 3 lines):**
```python
wallet_set, wallet = await client.create_agent_wallet("my-product")

@app.get("/data")
async def handler(payment=Depends(client.sell("$0.01"))):
    return {"data": "..."}
```

**Raw x402 (40+ lines):**
```python
server = x402ResourceServer(HTTPFacilitatorClient(FacilitatorConfig(url=...)))
server.register("eip155:84532", ExactEvmServerScheme())

routes = {
    "GET /data": RouteConfig(
        accepts=[PaymentOption(scheme="exact", price="$0.01", network="eip155:84532", pay_to=address)]
    ),
}
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)

@app.get("/data")
async def handler():
    return {"data": "..."}
```

**OmniClaw handles all the complexity** - facilitator, settlement, networks - you just write business logic!

### Advanced: Custom Routes (like x402)

If you need more control like x402:

```python
# Coming soon - define custom routes with multiple payment options
routes = {
    "GET /premium": RouteConfig(
        accepts=[
            PaymentOption(scheme="exact", price="$0.01", network="eip155:84532", pay_to=address),
            PaymentOption(scheme="exact", price="$0.01", network="eip155:1", pay_to=address),
        ]
    ),
}
```

### Deposit USDC to Enable Receiving

Your gateway wallet needs a USDC balance to receive payments (it acts as a buffer — buyers pay you by sending from their gateway to yours).

```python
# Check your gateway balance (uses wallet_id)
balance = await client.get_gateway_balance(wallet.id)
print(f"Gateway balance: {balance.formatted_total}")

# Deposit from your Circle wallet to Gateway (for gasless nanopayments)
await client.deposit_to_gateway(
    wallet_id=wallet.id,
    amount_usdc="100.00",
)

# Withdraw from Gateway back to your wallet
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="50.00",
)
```

### Protect FastAPI Endpoints

```python
from fastapi import FastAPI, Depends

app = FastAPI()

@app.get("/premium-data")
async def get_premium(payment=Depends(client.sell("$0.001"))):
    payment_info = client.current_payment()
    return {
        "data": "premium content",
        "paid_by": payment_info.payer,
        "network": payment_info.network,
    }
```

The `@client.sell()` decorator:

- Returns a FastAPI `Depends()` that gates the route with x402 payment
- Checks the `PAYMENT-SIGNATURE` header (base64-encoded EIP-3009 authorization)
- Verifies the payment amount matches
- Settles via Circle Gateway
- Returns `PaymentInfo` including the payer's address

### Get Paid Content

```python
@app.get("/premium")
async def premium(payment=Depends(client.sell("$0.50"))):
    info = client.current_payment()
    print(f"Paid by {info.payer} on {info.network}")
    print(f"Transaction: {info.transaction}")
    return {"content": "..."}
```

### Withdraw from Gateway

```python
# Withdraw to your Circle wallet
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="50.00",
)

# Or withdraw to another blockchain address
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="25.00",
    destination_chain=Network.BASE,
    recipient="0xBaseRecipient",
)
```

### Auto-Topup

Automatically refill gateway balance when it drops below a threshold:

```python
client.configure_nanopayments(
    auto_topup_enabled=True,
    auto_topup_threshold="5.00",  # Refill when balance < $5
    auto_topup_amount="50.00",    # Add $50 each time
    wallet_manager=gateway_manager,
)
```

## 9. Send Nanopayments as a Buyer

Nanopayments are sent automatically when you `pay()` a small amount to a gateway-enabled address:

```python
# Amounts below the micro threshold use gateway nanopayments
result = await client.pay(
    wallet_id=wallet.id,
    recipient="0xSellerGatewayAddress",
    amount="0.05",  # Small amount → gas-free nanopayment
)
```

Configuration:

```env
OMNICLAW_NANOPAYMENTS_MICRO_THRESHOLD=1.00  # Amounts < $1 use nanopayments
```

**Gateway CAIP-2:** The nanopayment CAIP-2 chain identifier is derived from `OMNICLAW_NETWORK` via `network_to_caip2`. Only EVM networks are supported.

On the buyer side, OmniClaw:
1. Checks if the recipient supports gateway nanopayments
2. Creates an EIP-3009 authorization (off-chain signing)
3. Sends the authorization as a `PAYMENT-SIGNATURE` header to Circle's settle API
4. Circle batches and settles on-chain

## 10. Enable Trust Checks

Set a real RPC URL:

```env
OMNICLAW_RPC_URL=https://your-rpc-provider
```

Then request trust evaluation:

```python
result = await client.pay(
    wallet_id=wallet.id,
    recipient="0xRecipient",
    amount="10.00",
    check_trust=True,
)
```

Rules:

- `check_trust=True` fails if no real RPC URL is configured
- `check_trust=None` uses auto mode
- `check_trust=False` skips trust evaluation

## 11. Webhooks

Use the webhook parser when handling Circle events:

```python
event = client.webhooks.handle(payload, headers)
```

If signature verification is configured, pass the raw payload and headers so verification can run before parsing.

## 12. Operational Guidance

- Use Redis in any concurrent deployment.
- Keep `OMNICLAW_NETWORK` explicit in every deployed environment.
- Keep trust checks opt-in unless your deployment is prepared with a working RPC provider.
- Prefer `simulate()` for higher-risk or user-approved operations.
- Prefer payment intents for review-required or delayed-execution flows.
