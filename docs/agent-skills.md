# OmniClaw Agent Wallet Skill

## What This Is
A secure, owner-controlled skill (structured instructions + reference docs) that teaches AI agents how to use the **OmniClaw CLI** to safely execute financial operations. 

In stark contrast to other agentic wallet SDKs, **OmniClaw is designed with "Friction as a Feature."** 
- Your human operator hosts the OmniClaw Control Plane.
- The control plane holds the private keys and dictates the policies (spending limits, allowed recipients).
- You (the agent) use the thin CLI client to request actions. You **cannot** create wallets or modify your own budget constraints.

## Use Cases
What can autonomous agents do within their safe boundaries?
- **Micro-Payments**: Pay other agents for completed tasks using Circle USDC Nanopayments.
- **API Billing**: Handle subscriptions and per-call payments for premium API access.
- **Escrow & Settlement**: Settle debts securely via the x402 protocol, mediated by your OmniClaw policy limits.

## Quick Start
Your execution environment must be provisioned with two variables by your human operator:
1. `OMNICLAW_SERVER_URL`
2. `OMNICLAW_TOKEN`

Initialize your CLI configuration:
```bash
omniclaw-cli configure --server-url $OMNICLAW_SERVER_URL --token $OMNICLAW_TOKEN --wallet your-wallet-alias
```

## Available Tool Actions
As an autonomous agent, you have access to the following deterministic commands.

### `address`
Get your assigned wallet address.
```bash
omniclaw-cli address
```

### `balance`
Check your current available balance before attempting payments.
```bash
omniclaw-cli balance
```

### `can-pay`
Verify if a specific recipient address or domain is whitelisted by your operator's policy.
```bash
omniclaw-cli can-pay --recipient 0xRecipientAddress
```

### `simulate`
Always simulate transactions before execution to ensure they meet your spending limits and velocity constraints.
```bash
omniclaw-cli simulate --recipient 0xRecipientAddress --amount 5.00
```

### `pay`
Execute a payment. If this violates your policy (e.g., exceeds your budget), the CLI will reject it. 
```bash
omniclaw-cli pay --recipient 0xRecipientAddress --amount 5.00 --purpose "Invoice #123"
```
*Note: If a transaction returns `PENDING_APPROVAL`, you successfully initiated it, but it exceeded your autonomous limit and requires Human-in-the-Loop (HITL) approval. Pause your workflow and notify the user.*

### `list_tx`
Retrieve your transaction history for reconciliation.
```bash
omniclaw-cli list_tx --limit 10
```

## Safety Constraints
- Do not attempt to use `curl` or raw HTTP requests to bypass the CLI.
- Do not attempt to modify your limits. If a payment is blocked by a policy, you MUST HALT and request your operator to amend the `policy.json` file.
