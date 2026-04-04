# OmniClaw

**Economic Execution and Control Layer for Agentic Systems** — Policy-controlled payments with Circle Gateway nanopayments (EIP-3009), x402 protocol support, gasless transactions, and per-agent wallet isolation.

📦 [PyPI](https://pypi.org/project/omniclaw/) · 🧪 [Tests: 1220 passed](tests/)

---

## Why OmniClaw?

In the Agent Era, software can act economically. But current wallets fail when software, not humans, is the operator:

- **Full key access** = extreme risk (agent can drain the wallet)
- **Human approval** = kills speed and autonomy
- **No spending limits** = agent can spend unlimited

Where Stripe helps merchants accept human payments, OmniClaw governs autonomous agents making machine payments — with policy, trust verification, and concurrency safety built in.

**OmniClaw solves this** by separating:
1. **Financial Policy Engine** (owner runs) - holds private keys, enforces policy
2. **Zero-Trust Execution Layer** (agent uses) - constrained CLI that only does what policy allows

The agent **never touches the private key**. It only talks to the CLI. The owner decides what the agent can do via policy.json.

---

## Architecture: Three Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OMNICLAW SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   OWNER SIDE (runs the Financial Policy Engine)   AGENT SIDE (uses CLI)     │
│   ════════════════════════════════════════════════   ═══════════════════════   │
│                                                                     │
│   ┌─────────────────────────────┐                ┌─────────────────────┐   │
│   │  Financial Policy Engine   │                │     OmniClaw CLI   │   │
│   │  (uvicorn server)          │◄──────────────►│ (zero-trust exec)  │   │
│   │                            │   HTTPS        │                    │   │
│   │  - Holds private key       │                │  - pay             │   │
│   │  - Enforces policy         │                │  - deposit         │   │
│   │  - Signs transactions      │                │  - withdraw        │   │
│   └─────────────────────────────┘                └─────────────────────┘   │
│            │                                      │                 │
│            │      Circle Nanopayment             │                 │
│            └──────────────┬──────────────────────┘                 │
│                           │                                          │
│                    ┌──────▼──────┐                                  │
│                    │   Circle    │                                  │
│                    │   Gateway   │                                  │
│                    │   (USDC)    │                                  │
│                    └─────────────┘                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Why Two Parts?

| Component | Who Runs It | What It Does |
|-----------|-------------|--------------|
| **Financial Policy Engine** | Owner/human | Holds private key, enforces policy, signs transactions |
| **CLI** (agent uses) | Agent | Zero-trust execution layer - constrained command surface, cannot bypass policy |

---

## Key Concepts

### 1. Two Wallets Every Agent Has

Every agent has **two wallets**:

| Wallet | How It Works |
|--------|--------------|
| **EOA** (External Owned Account) | Derived from `OMNICLAW_PRIVATE_KEY`. Holds actual USDC on-chain. Used to sign deposits. |
| **Circle Developer Wallet** | Created via policy.json. Where withdrawn funds go. The "circle wallet." |

### 2. Why Deposit + Pay + Withdraw?

```
Your USDC starts here:         Then moves here:              Ends up here:
┌──────────┐                  ┌────────────┐              ┌──────────────┐
│   EOA    │ ─deposit───────► │  Gateway   │ ──pay──────► │    Seller    │
│ (on-chain)│   (on-chain)    │  Contract  │   (x402)     │    EOA       │
└──────────┘                  └────────────┘              └──────────────┘
                                  │                              │
                                  │ withdraw                     │
                                  └──────────────► Circle Developer Wallet
```

- **Deposit**: Move USDC from your EOA → Gateway (on-chain, costs gas)
- **Pay**: Use Gateway for gasless payments (x402 protocol)
- **Withdraw**: Move USDC from Gateway → your Circle wallet

### 3. Why Gasless Nanopayments?

Circle's Gateway supports **EIP-3009** - off-chain authorization:
- No gas needed for payments
- Instant settlement
- Circle batches and settles on-chain
- Sub-cent transactions are economically viable

This is what makes agent-to-agent commerce practical — agents can trade at high frequency without bleeding gas on every transaction.

### 4. Seller Side: Accept Payments from Other Agents

OmniClaw isn't just for buyers. You can protect your own endpoint behind x402 and accept payments from other agents:

```python
from omniclaw.protocols.nanopayments import GatewayMiddleware

# Protect any async endpoint
middleware = GatewayMiddleware(
    price="0.01",  # 0.01 USDC per call
    seller_address="0xYourAddress",
)

app = FastAPI()
app.add_middleware(GatewayMiddleware, price="0.01")

@app.get("/api/data")
async def get_data():
    return {"data": "expensive information"}
```

This opens your service to agent-to-agent commerce — other agents can pay your endpoint using gasless nanopayments.

---

## Quick Start

### 1. Install

```bash
pip install omniclaw
# or
uv add omniclaw
```

### 2. Environment Variables (Required)

```bash
# Required to run
export OMNICLAW_PRIVATE_KEY="0x..."     # Your agent's private key
export OMNICLAW_AGENT_TOKEN="your-token" # Token from policy.json
export OMNICLAW_AGENT_POLICY_PATH="/path/to/policy.json"
export CIRCLE_API_KEY="your-circle-key" # Circle API key

# Network (testnet or mainnet)
export OMNICLAW_NETWORK="ETH-SEPOLIA"    # or ETH-MAINNET
export OMNICLAW_ENV="production"         # set for mainnet

# RPC for on-chain operations
export OMNICLAW_RPC_URL="https://..."
# Nanopayments CAIP-2 is derived from OMNICLAW_NETWORK (EVM only)
```

### 3. Start Financial Policy Engine (Owner)

```bash
uvicorn omniclaw.agent.server:app --port 8080
```

This runs the Financial Policy Engine that holds the private key and enforces policy.

### 4. Configure CLI (Agent)

Agent runtime should set these (no interactive setup required):

```bash
export OMNICLAW_SERVER_URL="http://localhost:8080"
export OMNICLAW_TOKEN="your-agent-token"
```

Optional: persist config locally for dev workflows:

```bash
omniclaw-cli configure --server-url http://localhost:8080 --token your-token --wallet primary
```

CLI output is agent-first (JSON, no banner). For human-friendly output set:

```bash
export OMNICLAW_CLI_HUMAN=1
```

Note: `omniclaw` and `omniclaw-cli` point to the same CLI.

---

## For BUYERS (Paying for Services)

### Step 1: Get USDC
Send USDC to your EOA address (derived from OMNICLAW_PRIVATE_KEY)

### Step 2: Deposit to Gateway
```bash
omniclaw-cli deposit --amount 10
```
→ Moves USDC from EOA → Circle Gateway contract (on-chain, costs gas)

### Step 3: Pay for Services
```bash
# Pay another agent
omniclaw-cli pay --recipient 0xDEAD... --amount 5

# Or pay for x402 service (URL)
omniclaw-cli pay --recipient https://api.example.com/data --amount 1
```
→ Uses gasless nanopayments via x402 protocol (Gateway CAIP-2 derived from `OMNICLAW_NETWORK`, EVM only)

### Step 4: Withdraw to Circle Wallet
```bash
omniclaw-cli withdraw --amount 3
```
→ Moves USDC from Gateway → your Circle Developer Wallet

---

## For SELLERS (Receiving Payments)

### Option A: Simple Transfer
Just share your address, receive payments directly:
```bash
omniclaw-cli address  # Get your address to share
```

### Option B: x402 Payment Gate (Recommended)
Expose your service behind payment:

```bash
omniclaw-cli serve \
  --price 0.01 \
  --endpoint /api/data \
  --exec "python my_service.py" \
  --port 8000
```

This opens `http://localhost:8000/api/data` that requires USDC payment to access.

---

## Complete CLI Commands

| Command | Description | Example |
|---------|-------------|---------|
| `configure` | Set Financial Policy Engine URL, token, wallet | `configure --server-url http://localhost:8080 --token mytoken --wallet primary` |
| `address` | Get wallet address | `address` |
| `balance` | Get wallet balance | `balance` |
| `balance-detail` | Detailed balance (EOA, Gateway, Circle) | `balance-detail` |
| `deposit` | Deposit USDC to Gateway | `deposit --amount 5` |
| `withdraw` | Withdraw to Circle wallet | `withdraw --amount 2` |
| `withdraw-trustless` | Trustless withdraw (~7-day fallback) | `withdraw-trustless --amount 2` |
| `withdraw-trustless-complete` | Complete trustless withdraw after delay | `withdraw-trustless-complete` |
| `pay` | Make payment | `pay --recipient 0x... --amount 5` |
| `simulate` | Simulate payment | `simulate --recipient 0x... --amount 5` |
| `serve` | Expose x402 payment gate | `serve --price 0.01 --endpoint /api --exec "echo hello"` |
| `status` | Agent status | `status` |
| `ping` | Health check | `ping` |
| `ledger` | Transaction history | `ledger --limit 20` |

---

## Default Policy.json

Copy and edit `examples/policy-simple.json`:

For full policy options, see **[docs/POLICY_REFERENCE.md](docs/POLICY_REFERENCE.md)**

```json
{
  "version": "2.0",
  "tokens": {
    "YOUR_AGENT_TOKEN": {
      "wallet_alias": "primary",
      "active": true,
      "label": "Your Agent Name"
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

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `OMNICLAW_PRIVATE_KEY` | Yes | Agent's private key for signing |
| `OMNICLAW_AGENT_TOKEN` | Yes | Token matching policy.json |
| `OMNICLAW_AGENT_POLICY_PATH` | Yes | Path to policy.json |
| `OMNICLAW_NETWORK` | No | Network (ETH-SEPOLIA, ETH-MAINNET) |
| `OMNICLAW_ENV` | No | Set to "production" for mainnet |
| `OMNICLAW_RPC_URL` | No | RPC endpoint for on-chain ops |
| `CIRCLE_API_KEY` | Yes | Circle API key |
| `OMNICLAW_SERVER_URL` | No | Financial Policy Engine URL for the zero-trust CLI |

---

## Documentation

- **[docs/agent-getting-started.md](docs/agent-getting-started.md)** - Agent setup walkthrough
- **[docs/agent-skills.md](docs/agent-skills.md)** - Skill instructions for AI agents
- **[docs/FEATURES.md](docs/FEATURES.md)** - Full feature documentation

---

## License

MIT — © 2026 [Omnuron AI](https://www.omniclaw.ai/). See [LICENSE](LICENSE) for details.
