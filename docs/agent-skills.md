---
name: omniClaw
description: Secure payment execution for AI agents with ERC-8004 identity, nanopayments, and policy-controlled wallets.
metadata:
  openclaw:
    requires:
      env:
        - OMNICLAW_PRIVATE_KEY
        - OMNICLAW_RPC_URL
        - CIRCLE_API_KEY
      bins:
        - python
    primaryEnv: OMNICLAW_PRIVATE_KEY
---

# OmniClaw Agent Wallet Skill

## What This Is
A secure, owner-controlled skill that teaches AI agents how to use the **OmniClaw CLI** to safely execute financial operations against the **OmniClaw Financial Policy Engine**.

**Why does this exist?** Because agents should never have direct access to private keys. Instead:
- Your **owner** runs the Financial Policy Engine that holds the private key
- **You** (the agent) use the thin CLI to request actions
- The **policy** in policy.json decides what you can and cannot do

This is "Friction as a Feature" - you can only do what your owner explicitly allows.

## How It Works

```
YOU (Agent)                    FINANCIAL POLICY ENGINE (Owner)
─────────────                  ────────────────────────────────

   │                                │
   │  omniclaw-cli pay ...          │
   ├───────────────────────────────►│
   │                                │ Check policy
   │                                │ Sign transaction
   │                                │ Return result
   │◄──────────────────────────────┤
   │                                │
```

You send requests to the Financial Policy Engine. It checks policy, signs with the private key (you never see it), and returns the result.

## Two Wallets You Have

| Wallet | Description |
|--------|-------------|
| **EOA** | Your "on-chain wallet" - derived from owner's private key. USDC starts here. |
| **Circle Developer Wallet** | Auto-generated on startup and persisted into policy.json. This is where withdrawn funds go. |

When you **deposit**, USDC moves from EOA → Gateway.
When you **withdraw**, USDC moves from Gateway → your Circle wallet.

## Use Cases
- **Micro-Payments**: Pay other agents using Circle USDC Nanopayments
- **API Billing**: Handle subscriptions and per-call payments for premium API access
- **Selling Services**: Expose your endpoints behind x402 payment gates to earn USDC
- **Escrow & Settlement**: Settle debts securely via the x402 protocol

## ERC-8004 Identity (Optional)

Your owner can register you on-chain for identity verification:

```bash
# Check/ensure identity is registered
agent_id = await client.ensure_identity()

# Submit feedback to rate sellers after payment
await client.submit_feedback(
    agent_id=seller_agent_id,
    value=85,  # positive rating
    tag1="helpful",
    tag2="fast"
)
```

This builds your on-chain reputation. Sellers can verify buyers before accepting payments.

## Quick Start
Agent runtimes should set environment variables (no interactive setup required):
1. `OMNICLAW_SERVER_URL` - where the Financial Policy Engine runs
2. `OMNICLAW_TOKEN` - your identity token (matches policy.json)
3. `OMNICLAW_OWNER_TOKEN` - required only for confirmation approvals

Optional: persist config locally for dev workflows:

```bash
omniclaw-cli configure --server-url $OMNICLAW_SERVER_URL --token $OMNICLAW_TOKEN --wallet primary
```

CLI output is agent-first (JSON, no banner). For human-friendly output set:

```bash
export OMNICLAW_CLI_HUMAN=1
```

---

## Available Tool Actions

### `address`
Get your assigned wallet address (EOA).
```bash
omniclaw-cli address
```

### `balance`
Check your current available balance in the Gateway.
```bash
omniclaw-cli balance
```

### `balance_detail`
Get detailed balance breakdown including EOA, Gateway, and Circle wallet.
```bash
omniclaw-cli balance_detail
```

### `can-pay`
Verify if a recipient is allowed by your owner's policy.
```bash
omniclaw-cli can-pay --recipient 0xRecipientAddress
```

### `simulate`
Simulate a payment before executing to check if it meets your spending limits.
```bash
omniclaw-cli simulate --recipient 0xRecipientAddress --amount 5.00
```
**Always do this before paying** to avoid failed transactions.

### `pay`
Execute a payment. If it violates your policy, the CLI rejects it.
```bash
# Direct transfer to another agent
omniclaw-cli pay --recipient 0xRecipientAddress --amount 5.00 --purpose "Payment for service"

# Pay for x402 service (URL)
omniclaw-cli pay --recipient https://api.example.com/data --amount 1.00
```

### `deposit`
Deposit USDC from your EOA to Circle Gateway. **Required before making nanopayments.**
```bash
omniclaw-cli deposit --amount 10.00
```
This is an on-chain transaction (costs gas). Moves USDC: EOA → Gateway.

### `withdraw`
Withdraw USDC from Gateway to your Circle Developer Wallet. No recipient needed - automatic.
```bash
omniclaw-cli withdraw --amount 5.00
```

### `withdraw_trustless`
Trustless withdrawal (fallback if Circle API fails). Takes ~7 days.
```bash
omniclaw-cli withdraw_trustless --amount 5.00
```
Use only if the regular `withdraw` fails.

### `withdraw_trustless_complete`
Complete a trustless withdrawal after the delay has passed.
```bash
omniclaw-cli withdraw_trustless_complete
```

### `serve`
Expose a service behind x402 payment gate to receive payments.
```bash
omniclaw-cli serve --price 0.01 --endpoint /api/data --exec "python my_service.py" --port 8000
```
This opens `http://localhost:8000/api/data` that requires USDC payment to access.
- Other agents can `pay` your URL
- Payment is automatically settled via Circle Gateway

### `create_intent`
Create a payment intent (pre-authorize a payment).
```bash
omniclaw-cli create_intent --recipient 0xRecipientAddress --amount 5.00 --purpose "Service payment"
```

### `confirm_intent`
Confirm a pending intent (capture the payment).
```bash
omniclaw-cli confirm_intent --intent-id <intent-id>
```

### `get_intent`
Get details of a payment intent.
```bash
omniclaw-cli get_intent --intent-id <intent-id>
```

### `cancel_intent`
Cancel a pending intent.
```bash
omniclaw-cli cancel_intent --intent-id <intent-id>
```

### `list_tx` / `ledger`
Retrieve your transaction history.
```bash
omniclaw-cli list_tx --limit 10
omniclaw-cli ledger --limit 20
```

### `status`
Get agent status and health.
```bash
omniclaw-cli status
```

### `ping`
Health check.
```bash
omniclaw-cli ping
```

---

## Safety Constraints

1. **Never use curl or raw HTTP** - always use the CLI. Bypassing the CLI bypasses policy.
2. **Never modify your limits** - if blocked by policy, you MUST HALT and request your operator.
3. **Always simulate before paying** - check if the payment will succeed.
4. **Withdraw auto-routes to Circle wallet** - no recipient needed, this is by design.
5. **You never see the private key** - only the owner has it. You only send requests.

---

## Typical Workflow

### To Pay for Something:
```bash
# 1. Check balance
omniclaw-cli balance

# 2. If needed, deposit more USDC to Gateway
omniclaw-cli deposit --amount 10

# 3. Simulate to check limits
omniclaw-cli simulate --recipient 0xSeller... --amount 5

# 4. Pay
omniclaw-cli pay --recipient 0xSeller... --amount 5
```

### To Receive Payments:
```bash
# Start a payment gate for your service
omniclaw-cli serve --price 0.01 --endpoint /api --exec "python my_service.py" --port 8000

# Other agents can now pay your URL and you automatically receive USDC
```

### To Move Funds Out:
```bash
# Withdraw from Gateway to your Circle Developer Wallet
omniclaw-cli withdraw --amount 5

# If API fails, use trustless (takes ~7 days)
omniclaw-cli withdraw_trustless --amount 5
```

---

## Flow Diagram

```
┌─────────┐    deposit     ┌─────────┐    pay     ┌─────────┐
│  Your   │ ────────────►  │ Gateway │ ─────────► │ Seller  │
│   EOA   │   (on-chain)   │ Contract│  (x402)    │   EOA   │
└─────────┘                └─────────┘           └─────────┘
                                  │
                                  │ withdraw
                                  ▼
                          ┌─────────────┐
                          │    Your     │
                          │ Circle Wallet│
                          └─────────────┘
```
