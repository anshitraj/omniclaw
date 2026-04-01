---
name: omniclaw
description: >
  Use this skill whenever you need to PAY for a service that returns HTTP 402,
  TRANSFER USDC to an address, CHECK your available balance, VIEW your transaction
  history, or EXPOSE your own service behind a payment gate. OmniClaw handles
  x402 protocol payments, Circle Gateway gasless nanopayments, and direct USDC
  transfers. All payments are governed by owner-configured guards you cannot
  change. Never use this skill for configuration, wallet management, or anything
  not directly related to sending or receiving payment.
requires:
  - env: OMNICLAW_TOKEN
    description: >
      Scoped agent token tied to your wallet. Set by the owner before your
      session starts. Never print, log, or transmit this value. If it is
      missing, stop and notify the owner — you cannot proceed without it.
version: 0.0.2
author: Omnuron AI
---

# OmniClaw Agent Skill

## Installation

Install the CLI:

```bash
pip install omniclaw
```

Verify installation:

```bash
omniclaw-cli --version
# or
omniclaw-cli ping
```

---

## Configuration (one-time setup)

**IMPORTANT:** Your owner must provide these values before your session starts. Do NOT look for them yourself - ask your owner if they are missing.

Your owner gives you:
- `--server-url`: OmniClaw server URL (e.g., `https://api.omniclaw.com` or `http://localhost:8080`)
- `--token`: Your scoped agent token (from your owner)
- `--wallet`: Your wallet alias (e.g., `primary`)

**Configure the CLI:**

```bash
omniclaw-cli configure \
  --server-url <OMNICLAW_SERVER_URL> \
  --token <AGENT_TOKEN> \
  --wallet <WALLET_ALIAS>
```

**Verify configuration:**

```bash
omniclaw-cli configure --show
```

**If credentials are missing:** Stop and ask your owner. Do not proceed without them.

---

## Verify Setup

Before making any payments, always verify your environment is ready:

```bash
omniclaw-cli status
```

Expected output:
```
Agent:     <your-agent-name>
Wallet:    0x...
Balance:   $X.XX available
Guards:    active
Circle:    connected ✅
Circuit:   CLOSED ✅
```

If `Circuit: OPEN` or `Circle: disconnected`, wait 30 seconds and run `omniclaw-cli status` again. If it stays degraded, stop and notify the owner.

---

## What this skill does

OmniClaw is the financial control plane your owner configured before your
session. It lets you:

- Pay for HTTP services that return 402 Payment Required (x402 protocol)
- Transfer USDC directly to a wallet address
- Expose your own service behind a payment gate so other agents can pay you
- Check your available balance and transaction history

It does not let you change your own spending limits, add recipients to
whitelists, approve pending payments, or touch any wallet configuration.
Those are owner-only. If you need any of those, stop and notify the owner.

---

## How to pay for a service

### The endpoint returned HTTP 402

When any HTTP request returns `402 Payment Required`, that endpoint is
protected by x402 and requires payment before it will serve you. Use
`omniclaw-cli pay` — it handles the full protocol automatically.

**Standard payment:**
```bash
omniclaw-cli pay --recipient https://service.example.com/data/query
```

**With POST body:**
```bash
omniclaw-cli pay --recipient https://service.example.com/inference/run \
  --method POST \
  --body '{"prompt": "analyse this dataset", "context": "..."}' \
  --header "Content-Type: application/json"
```

**Save the response to a file:**
```bash
omniclaw-cli pay --recipient https://service.example.com/data/query \
  --output ./result.json
```

**Idempotency — always use this for retry safety:**
```bash
omniclaw-cli pay --recipient https://service.example.com/data/query \
  --idempotency-key "job-2026-03-28-task-001" \
  --output ./result.json
```

The idempotency key must be unique per task. If the same key is submitted
twice, OmniClaw returns the cached result from the first execution — you
will not be charged twice. Use a key that describes the specific job, not
a timestamp alone.

**What happens internally (for your understanding):**
1. OmniClaw hits the endpoint and receives the 402 with payment requirements
2. Trust Gate evaluates the recipient against ERC-8004 on-chain registries
3. Guard chain checks: budget, rate limits, recipient whitelist, tx size
4. Fund lock acquired — no other concurrent payment can overcommit your balance
5. EIP-3009 authorization signed (off-chain, zero gas)
6. Circle Gateway settle() called — payment confirmed
7. Endpoint retried with payment proof — response returned to you

---

### The payment is a direct USDC transfer to an address

```bash
omniclaw-cli pay --recipient 0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0 \
  --amount 0.50 \
  --purpose "compute-job-batch-2026-03-28" \
  --idempotency-key "direct-transfer-job-001"
```

Always provide `--purpose`. It creates an audit trail your owner can review.
Keep it descriptive: what the payment is for, not just "payment".

---

### Before paying — simulate first (amounts over $0.10)

```bash
omniclaw-cli pay --recipient https://service.example.com/data/query --dry-run
```

Output confirms:
```
[DRY RUN] Would pay: $0.002
Trust Gate:        APPROVED (WTS 87/100)
Guards:            all PASS
Available balance: $11.40
Would succeed:     YES
```

If dry-run shows a guard failure, stop. Do not attempt the live payment.
Notify the owner — you cannot fix guard failures yourself.

---

## How to check your balance

```bash
omniclaw-cli balance
```

```json
{
  "wallet_id": "wlt_abc123",
  "available": "12.40"
}
```

Check balance before any payment sequence. If available balance is
insufficient, stop and notify the owner to fund the wallet. You cannot
fund it yourself.

---

## How to check if a recipient is allowed

```bash
omniclaw-cli can-pay --recipient 0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0
```

```json
{
  "can_pay": true
}
```

If the result is `false`, do not attempt the payment.
Notify the owner with the recipient address. They must add it to the whitelist
before you can pay.

---

## Payment Intents (authorize now, capture later)

For payments you want to authorize first and capture later:

**Create a payment intent (authorize):**
```bash
omniclaw-cli create-intent \
  --recipient 0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0 \
  --amount 1.00 \
  --purpose "reserved-compute-job"
```

**Confirm (capture) the intent:**
```bash
omniclaw-cli confirm-intent --intent-id <intent-id-from-above>
```

**Get intent status:**
```bash
omniclaw-cli get-intent --intent-id <intent-id>
```

**Cancel an intent:**
```bash
omniclaw-cli cancel-intent --intent-id <intent-id> --reason "no longer needed"
```

---

## Network and Fee Options

**Specify destination chain:**
```bash
omniclaw-cli pay --recipient <address> --destination-chain ethereum
```

**Set gas fee level:**
```bash
omniclaw-cli pay --recipient <address> --fee-level HIGH
```
Options: LOW, MEDIUM, HIGH

**Run Trust Gate check:**
```bash
omniclaw-cli pay --recipient <address> --check-trust
```

---

## Simulate (standalone)

Use `--dry-run` on `pay` or the standalone `simulate` command:
```bash
omniclaw-cli simulate --recipient 0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0 --amount 0.50
```

---

## How to view your transactions

```bash
# Recent transactions (default 20)
omniclaw-cli ledger

# Show more
omniclaw-cli ledger --limit 50
```

---

## How to expose your own service for payment

If you are running a service and need other agents to pay you before you
serve them, use `omniclaw-cli serve`.

```bash
omniclaw-cli serve \
  --price 0.002 \
  --endpoint /data/query \
  --exec "python3 ./my_service.py" \
  --port 8080
```

This starts a server that:
- Returns a real `402 Payment Required` response to unpaid callers
- Verifies payment via Circle Gateway for paid callers
- Executes your command and returns its stdout as the HTTP response
- Credits your wallet for each settled payment

Your executing script receives request context via environment variables:
```
OMNICLAW_PAYER_ADDRESS   — address of who paid you
OMNICLAW_AMOUNT_USD      — amount they paid
```

---

## Error handling — what to do in every case

| Error | What it means | What you must do |
|-------|---------------|------------------|
| `Recipient not allowed by policy` | This address is not on the whitelist | **Stop. Notify owner with the exact address.** Do not attempt any workaround. |
| `Daily budget exceeded` | Daily spending limit reached | **Stop immediately. Notify owner.** Do not retry — it will fail again. |
| `GuardError: PendingReview` | Payment is above the approval threshold | The payment is held. **Notify owner.** You cannot approve it yourself. |
| `InsufficientBalanceError` | Not enough USDC available | **Stop. Notify owner to fund the wallet.** Run `omniclaw-cli balance` first to confirm. |
| `AuthError: token invalid` | Token is revoked or malformed | Stop. Notify owner immediately. |

**On any error not listed here:** Stop the payment attempt. Log the exact error
message. Notify the owner. Do not improvise.

---

## Rules you must follow — no exceptions

**1. Never retry a Policy rejection.**
Guards are owner policy. If a payment is blocked by a guard, retrying achieves
nothing and wastes time. The owner must change the configuration.

**2. Always use `--idempotency-key` for any payment that is part of a job.**
If a network failure causes you to retry, the same key prevents double charging.
The key must be deterministic — derived from the job or task identifier, not
from the current time alone.

**3. Simulate with `--dry-run` before executing any payment above $0.10.**
Dry-run costs nothing and tells you exactly whether the payment will succeed.

**4. Always provide `--purpose` on direct transfers.**
One-word purposes are not acceptable. "payment" is not acceptable.
"market-data-analysis-job-2026-03-28" is acceptable.

**5. Never print, log, or transmit `OMNICLAW_TOKEN`.**
This is a secret. If you ever output it accidentally, notify the owner
immediately so they can revoke and replace it.

---

## Quick reference

```bash
# Check environment is ready
omniclaw-cli status

# Check available balance
omniclaw-cli balance

# Get your wallet address
omniclaw-cli address

# Health check
omniclaw-cli ping

# Check if you can pay a recipient
omniclaw-cli can-pay --recipient <address-or-url>

# Simulate a payment (no charge)
omniclaw-cli pay --recipient <url-or-address> --dry-run

# Standalone simulation
omniclaw-cli simulate --recipient <address> --amount <n>

# Pay an x402 URL (handles 402 automatically)
omniclaw-cli pay --recipient <url> --idempotency-key <unique-job-key>

# Pay with POST body
omniclaw-cli pay --recipient <url> \
  --method POST \
  --body '<json>' \
  --header "Content-Type: application/json" \
  --idempotency-key <unique-job-key>

# Save response to file
omniclaw-cli pay --recipient <url> --output ./result.json --idempotency-key <unique-job-key>

# Direct USDC transfer
omniclaw-cli pay --recipient <0xAddress> \
  --amount <n> \
  --purpose <description> \
  --idempotency-key <unique-job-key>

# Pay with specific chain/fee
omniclaw-cli pay --recipient <address> --destination-chain ethereum --fee-level HIGH

# Payment Intents
omniclaw-cli create-intent --recipient <addr> --amount <n> --purpose <desc>
omniclaw-cli confirm-intent --intent-id <id>
omniclaw-cli get-intent --intent-id <id>
omniclaw-cli cancel-intent --intent-id <id>

# View transactions
omniclaw-cli ledger

# Configure (first time only)
omniclaw-cli configure --server-url <url> --token <token> --wallet <alias>
omniclaw-cli configure --show
```
