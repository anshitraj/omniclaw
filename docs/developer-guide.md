# OmniClaw Developer Guide (Python SDK)

This guide covers how developers, vendors, and application teams build policy-controlled payment flows with the OmniClaw Python SDK.

> **Vendors vs Agents:** This guide is for developers embedding OmniClaw code into real Python applications (like FastAPI servers or backend worker scripts). If you are looking to operate an autonomous AI Agent using the command line, please see the [Agent CLI Guide](agent-getting-started.md).

---

## 1. Initialize the SDK Client

```python
from omniclaw import OmniClaw, Network

# Initialize the client (auto-loads credentials from env)
client = OmniClaw(network=Network.ETH_SEPOLIA)
```

With environment variables:

```env
CIRCLE_API_KEY=your_circle_api_key
OMNICLAW_NETWORK=ETH-SEPOLIA
```

### Automatic Entity Secret Management

If your Circle account/API key already has an Entity Secret, set it directly:

```env
ENTITY_SECRET=your_existing_64_char_hex_entity_secret
```

Circle only allows one active Entity Secret per account/API key. OmniClaw will use `ENTITY_SECRET` from the environment first, then its managed local credential store. It only auto-generates and registers a new Entity Secret when no existing secret is provided or found.

For non-interactive setup:

```bash
omniclaw setup --api-key "$CIRCLE_API_KEY" --entity-secret "$ENTITY_SECRET"
```

---

## 2. Managing Wallets programmatically

Whether you are building a buyer app that needs to spend funds or a seller app that needs to receive funds, you need an OmniClaw-managed wallet.

### Create an Application Wallet
```python
# Creates a wallet_set and primary wallet for your app
wallet_set, wallet = await client.create_agent_wallet("my-backend-app")

print(f"Your application's wallet ID is: {wallet.id}")
print(f"Your on-chain address is: {wallet.address}")

# Get detailed balance (what you can spend safely)
detailed = await client.get_detailed_balance(wallet.id)
print(f"Available USDC: {detailed['available']}")
```

---

## 3. As a Developer: Buying and Sending Payments

Use the SDK to programmatically send USDC payments (e.g., in a background job, cron script, or user-initiated transaction).

### Standard P2P Transfer
```python
result = await client.pay(
    wallet_id=wallet.id,
    recipient="0xRecipientAddress",
    amount="10.50",
    purpose="Monthly API refill",
)
print(f"Payment successful. TX: {result.blockchain_tx or result.transaction_id}")
```

### Paying an x402 Paid Endpoint Programmatically
OmniClaw's routing engine handles all the complexity of the x402 402-Payment-Required handshake internally. Just pass the URL as the recipient:

```python
# OmniClaw performs the 402 handshake, signs the selected payment, retries the
# request with the payment header, and returns the paid resource response.
result = await client.pay(
    wallet_id=wallet.id,
    recipient="https://api.vendor.com/premium-data",
    amount="0.05",
)

print(result.status, result.blockchain_tx or result.transaction_id)
print(result.resource_data)
```

---

## 4. As a Developer: Selling and Receiving Payments (Vendor)

If you are building an API and want to monetize it without setting up a separate billing system, use `client.sell()` in FastAPI.

### Quick Start: Gated Endpoints
```python
from fastapi import FastAPI
from omniclaw import OmniClaw

app = FastAPI()
client = OmniClaw()

# Require $0.01 in USDC to access this route
@app.get("/premium-data")
async def get_data(
    payment=client.sell("$0.01", seller_address="0xYourWalletAddress"),
):

    # This code ONLY executes if the payment has cleared and settled.
    return {
        "status": "success",
        "data": "premium content",
        "buyer_address": payment.payer,
    }
```

### Seller Facilitator Options

The seller SDK supports multiple settlement paths.

Circle Gateway default:

```python
payment=client.sell("$0.25", seller_address="0xVendorWallet")
```

Thirdweb managed x402:

```python
payment=client.sell(
    "$0.25",
    seller_address="0xThirdwebServerWallet",
    facilitator="thirdweb",
)
```

OmniClaw self-hosted exact facilitator:

```python
payment=client.sell(
    "$0.25",
    seller_address="0xVendorWallet",
    facilitator="omniclaw",
)
```

For the self-hosted path, run the facilitator separately:

```bash
export OMNICLAW_X402_SELF_HOSTED_FACILITATOR_URL="http://127.0.0.1:4022"
export OMNICLAW_X402_EXACT_NETWORK_PROFILE="ARC-TESTNET"

omniclaw facilitator exact --network-profile ARC-TESTNET --port 4022
```

See [B2B SDK Integration](../examples/b2b-sdk-integration/README.md) for complete deployment examples.

### Managing Your Vendor Earnings
Payments received via the standard Circle Gateway routes pile up in your Gateway balance. You must withdraw them to your main on-chain wallet.

```python
# Check earnings
balance = await client.get_gateway_balance(wallet.id)
print(f"Earnings waiting in Gateway: {balance.formatted_total}")

# Sweep earnings to your exact on-chain wallet
await client.withdraw_from_gateway(
    wallet_id=wallet.id,
    amount_usdc="50.00",
)
```

---

## 5. Adding Safety Guards via Code

As a developer, you want absolute assurance your background jobs won't drain your liquidity.

```python
# Block your application from spending more than $100 a day
await client.add_budget_guard(wallet.id, daily_limit="100.00", hourly_limit="20.00")

# Stop runaway loops: max 5 payments per minute
await client.add_rate_limit_guard(wallet.id, max_per_minute=5)

# Never allow a single payment over $25
await client.add_single_tx_guard(wallet.id, max_amount="25.00")

# Restrict outbound funds to a specific whitelist of known vendor APIs
await client.add_recipient_guard(
    wallet.id,
    mode="whitelist",
    addresses=["0xTrustedSupplier"],
    domains=["api.openai.com", "api.anthropic.com"],
)
```

## 6. Advanced programmatic controls

### Simulating Payments
Test if a complex payment flow will pass guards without actually sending money.
```python
sim = await client.simulate(
    wallet_id=wallet.id,
    recipient="0xRecipient",
    amount="25.00",
)

if sim.would_succeed:
    print(f"Will execute using route: {sim.route}")
else:
    print(f"Blocked by: {sim.reason}")
```

### Webhooks
When receiving async settlement events from the Circle API:
```python
event = client.webhooks.handle(payload, headers)
print(f"Received settlement for transaction {event.transaction_hash}")
```
