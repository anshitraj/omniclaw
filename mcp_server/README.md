# OmniClaw MCP Server

FastMCP server exposing the OmniClaw Financial Policy Engine as MCP tools for agent-facing wallet and payment operations.

This server is not the primary launch artifact for today, but its docs are kept aligned so the repo does not publish stale MCP behavior.

## Highlights

- FastMCP HTTP transport
- Optional bearer or JWT authentication
- Wallet provisioning and balance lookup
- Guarded payment execution and simulation
- Payment intent lifecycle
- Read-only routing, trust, transaction, and ledger lookup tools

## Requirements

- Python `3.11+`
- Valid `CIRCLE_API_KEY`
- Valid `ENTITY_SECRET`

## Configuration

Example `.env`:

```env
ENVIRONMENT=dev

CIRCLE_API_KEY=...
ENTITY_SECRET=...
OMNICLAW_NETWORK=ARC-TESTNET

OMNICLAW_DAILY_BUDGET=1000
OMNICLAW_HOURLY_BUDGET=200
OMNICLAW_TX_LIMIT=500
OMNICLAW_RATE_LIMIT_PER_MIN=5
OMNICLAW_WHITELISTED_RECIPIENTS=0xabc...,0xdef...
OMNICLAW_CONFIRM_ALWAYS=false

MCP_AUTH_ENABLED=true
MCP_REQUIRE_AUTH=true
MCP_AUTH_TOKEN=...
```

Backward-compatible `OMNIAGENTPAY_*` aliases are still accepted by the MCP server config, but `OMNICLAW_*` should be treated as canonical.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Endpoints:

- MCP: `POST /mcp/`
- Health: `GET /health`

## Current Tool Surface

Wallets:

- `create_agent_wallet`
- `list_wallets`
- `get_wallet`
- `check_balance`
- `get_balances`

Payments and intents:

- `simulate`
- `pay`
- `batch_pay`
- `create_payment_intent`
- `get_payment_intent`
- `confirm_payment_intent`
- `cancel_intent`

Transactions and ledger:

- `list_transactions`
- `sync_transaction`
- `ledger_get_entry`

Routing and trust:

- `can_pay`
- `detect_payment_method`
- `trust_lookup`

For detailed request shapes, see [TOOLS.md](TOOLS.md).

## Security Notes

- In `prod`, Circle credentials are required at startup.
- If auth is enabled and required, configure `MCP_AUTH_TOKEN` or `MCP_JWT_SECRET`.
- Use HTTPS and secret management in deployed environments.
