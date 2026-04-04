# OmniClaw Agent Getting Started

This guide walks you through setting up an OmniClaw agent for both buying and selling.

OmniClaw is the **Economic Execution and Control Layer for Agentic Systems**.
In that system:

- the owner runs the **Financial Policy Engine**
- the agent uses `omniclaw-cli` as the **zero-trust execution layer**
- buyers pay with `omniclaw-cli pay`
- sellers earn with `omniclaw-cli serve`

---

## Prerequisites

- Python 3.10+
- Circle API key
- USDC on the target network (testnet or mainnet)
- A private key for your agent

---

## Step 1: Create Policy.json

Create a `policy.json` file that defines your agent:

```json
{
  "version": "2.0",
  "tokens": {
    "my-agent-token": {
      "wallet_alias": "primary",
      "active": true,
      "label": "My Agent"
    }
  },
  "wallets": {
    "primary": {
      "name": "Primary Wallet",
      "limits": {
        "daily_max": "100.00",
        "per_tx_max": "50.00"
      },
      "recipients": {
        "mode": "allow_all"
      }
    }
  }
}
```

On startup, the server will auto-generate and persist `wallet_id` and `address`
inside each wallet entry if they are missing.

You can copy the default from `examples/default-policy.json` and edit it.

The server validates policy.json on startup and will refuse to boot if it is invalid.

---

## Step 2: Set Environment Variables

```bash
# Required
export OMNICLAW_PRIVATE_KEY="0x..."           # Your agent's private key
export OMNICLAW_AGENT_TOKEN="my-agent-token"   # Must match policy.json token key
export OMNICLAW_AGENT_POLICY_PATH="/path/to/policy.json"
export CIRCLE_API_KEY="your-circle-api-key"

# Network (testnet or mainnet)
export OMNICLAW_NETWORK="ETH-SEPOLIA"         # or ETH-MAINNET for production

# Set production for mainnet usage
export OMNICLAW_ENV="production"              # optional - for mainnet

# RPC for on-chain operations
export OMNICLAW_RPC_URL="https://..."
export OMNICLAW_OWNER_TOKEN="your-owner-token" # Required for approvals
export OMNICLAW_POLICY_RELOAD_INTERVAL="5"     # Hot reload interval (seconds)
```

---

## Step 3: Start the Financial Policy Engine

```bash
uvicorn omniclaw.agent.server:app --port 8080
```

The Financial Policy Engine runs at `http://localhost:8080`.

---

## Step 4: Configure the CLI

For agents, use environment variables (no interactive setup required):

```bash
export OMNICLAW_SERVER_URL="http://localhost:8080"
export OMNICLAW_TOKEN="my-agent-token"
```

Optional: persist config locally for dev workflows:

```bash
omniclaw-cli configure --server-url http://localhost:8080 --token my-agent-token --wallet primary
```

CLI output is agent-first (JSON, no banner). For human-friendly output set:

```bash
export OMNICLAW_CLI_HUMAN=1
```

---

## Step 5: Use the CLI

### Check Your Address
```bash
omniclaw-cli address
```

### Check Balance
```bash
omniclaw-cli balance

# Or detailed view
omniclaw-cli balance_detail
```

### Deposit USDC to Gateway
```bash
omniclaw-cli deposit --amount 10
```
This moves USDC from your EOA to the Circle Gateway contract.

### Withdraw to Circle Wallet
```bash
omniclaw-cli withdraw --amount 5
```
This moves USDC from Gateway to your Circle Developer Wallet.

---

## Confirmations (High-Value Policy Thresholds)

If a policy requires confirmation, `/pay` will return:

- `requires_confirmation: true`
- `confirmation_id: <id>`

Approve with the owner token:

```bash
omniclaw-cli configure --owner-token YOUR_OWNER_TOKEN
omniclaw-cli confirmations approve --id <confirmation_id>
```

Then retry the payment with the same `confirmation_id` in metadata:

```json
{
  "recipient": "0xRecipient",
  "amount": "50.00",
  "metadata": {
    "confirmation_id": "<confirmation_id>"
  }
}
```

---

## For SELLERS: Expose a Payment Gate

To receive payments, expose a service behind x402 payment:

```bash
omniclaw-cli serve \
  --price 0.01 \
  --endpoint /api/data \
  --exec "python my_service.py" \
  --port 8000
```

This opens `http://localhost:8000/api/data` that requires USDC payment to access.

This is the seller side of the same OmniClaw economy.
The same CLI powers both sides:

- buyer: `omniclaw-cli pay`
- seller: `omniclaw-cli serve`

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `omniclaw-cli address` | Get your wallet address |
| `omniclaw-cli balance` | Check balance |
| `omniclaw-cli deposit --amount X` | Deposit to Gateway |
| `omniclaw-cli withdraw --amount X` | Withdraw to Circle wallet |
| `omniclaw-cli withdraw_trustless --amount X` | Trustless withdraw (~7-day delay) |
| `omniclaw-cli withdraw_trustless_complete` | Complete trustless withdraw after delay |
| `omniclaw-cli pay --recipient 0x... --amount X` | Pay another agent |
| `omniclaw-cli serve --price X --endpoint /api --exec "cmd"` | Start payment gate |

---

## Network Switching

To switch from testnet to mainnet:

```bash
export OMNICLAW_NETWORK="ETH-MAINNET"
export OMNICLAW_ENV="production"
```

Everything automatically switches to mainnet URLs.

---

## Troubleshooting

### "Wallet is currently initializing"
Wait a few seconds and retry. The agent is setting up.

### "Invalid token"
Check that `OMNICLAW_AGENT_TOKEN` matches a key in your policy.json's `tokens` section.

### "Insufficient balance"
Make sure you've deposited USDC to the Gateway first:
```bash
omniclaw-cli deposit --amount 10
```
