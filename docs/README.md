# OmniClaw Documentation

OmniClaw is a policy-controlled payment layer for agents, applications, and machine services.

Use this index to choose the right integration path.

## Choose Your Path

| Role | Start Here | What You Build |
| --- | --- | --- |
| Agent buyer | [Agent Getting Started](agent-getting-started.md) | An agent that pays through `omniclaw-cli` |
| Python buyer | [Developer Guide](developer-guide.md) | A backend service that pays programmatically |
| Vendor / enterprise seller | [Developer Guide](developer-guide.md) | A FastAPI service with paid endpoints through the SDK |
| Infrastructure team | [Operator CLI](operator-cli.md) | Financial Policy Engine, policies, and facilitators |
| Maintainer | [Production Readiness](production-readiness.md) | Proof checklist and ship status |

## Buyer Guides

| Guide | Use Case |
| --- | --- |
| [Agent Getting Started](agent-getting-started.md) | Configure an agent with `omniclaw-cli` |
| [CLI Reference](cli-reference.md) | Full generated `omniclaw-cli` command reference |
| [Developer Guide](developer-guide.md) | Pay with the Python SDK |
| [API Reference](API_REFERENCE.md) | SDK methods, request shapes, and payment APIs |

## Seller Guides

| Guide | Use Case |
| --- | --- |
| [Developer Guide](developer-guide.md) | Add production paid FastAPI routes with `client.sell()` |
| [B2B SDK Integration](../examples/b2b-sdk-integration/README.md) | Enterprise SDK deployment with Circle, Thirdweb, or self-hosted exact |
| [Vendor Integration](../examples/vendor-integration/README.md) | Production-style vendor API integration |
| [Business Compute](../examples/business-compute/README.md) | Payment-gated compute service |
| [CLI Reference](cli-reference.md) | Agent-facing paid service flow with `omniclaw-cli serve` |

## Machine Payment Examples

| Example | Demonstrates |
| --- | --- |
| [B2B SDK Integration](../examples/b2b-sdk-integration/README.md) | Enterprise buyer/seller SDK integration |
| [Machine to Machine](../examples/machine-to-machine/README.md) | One automated service paying another |
| [Machine to Vendor](../examples/machine-to-vendor/README.md) | Agent buyer paying a vendor-owned API |
| [Local Economy](../examples/local-economy/README.md) | Local buyer/seller stack with Docker |
| [External x402 Facilitator](../examples/external-x402-facilitator/README.md) | x402.org exact settlement on Base Sepolia |
| [Thirdweb HTTP Facilitator](../examples/thirdweb-http-facilitator/README.md) | Thirdweb HTTP facilitator integration |
| [Arc Marketplace Showcase](../examples/arc-marketplace-showcase/README.md) | Visual vendor kiosk with Arc Testnet x402 exact settlement |

## Arc Testnet Quickstart

Run the full Arc marketplace showcase with Docker-reachable service IPs:

```bash
bash scripts/start_arc_marketplace_showcase_docker.sh
```

The buyer key must hold Arc Testnet USDC for the selected paid product, and the seller/facilitator key must hold Arc Testnet gas. The launcher prints balances, product URLs, the exact OmniClaw config, and a lower-cost `$0.10` proof endpoint when the buyer wallet is not funded for the `$0.25` product.

The showcase UI also has a built-in mini buyer agent, so the full demo can run directly from the browser. The kiosk backend proxies inspect/pay actions into the buyer Financial Policy Engine while keeping the policy token server-side.

Defaults:

| Service | URL |
| --- | --- |
| Browser UI | `http://127.0.0.1:8020` |
| Vendor kiosk | `http://172.18.0.51:8020` |
| Buyer policy engine | `http://172.18.0.52:8080` |
| Exact facilitator | `http://172.18.0.50:4022` |

For setup details and ArcLens submission notes, see [Arc Marketplace Showcase](../examples/arc-marketplace-showcase/README.md).

## Operator and Production Docs

| Document | Covers |
| --- | --- |
| [Operator CLI](operator-cli.md) | `omniclaw server`, `omniclaw setup`, `omniclaw facilitator exact` |
| [Policy Reference](POLICY_REFERENCE.md) | Tokens, wallets, budgets, recipient rules, confirmations |
| [Facilitators](facilitators.md) | Circle Gateway, x402.org, Thirdweb, self-hosted exact |
| [Production Readiness](production-readiness.md) | Live proof status and release checklist |
| [Production Hardening](PRODUCTION_HARDENING.md) | Deployment controls, Redis, nonce, security settings |

## Architecture and Reference

| Document | Covers |
| --- | --- |
| [Architecture and Features](FEATURES.md) | Core design, route selection, guards, settlement paths |
| [Architecture Diagram](architecture_overview.svg) | System overview |
| [Compliance Architecture](compliance-architecture.md) | Compliance and control framing |
| [CCTP Usage](CCTP_USAGE.md) | Circle CCTP notes |
| [ERC-804 Spec](erc_804_spec.md) | Trust-related specification notes |

## Project Files

| File | Purpose |
| --- | --- |
| [CHANGELOG](../CHANGELOG.md) | Release history |
| [CONTRIBUTING](../CONTRIBUTING.md) | Development and PR workflow |
| [SECURITY](../SECURITY.md) | Security reporting |
| [ROADMAP](../ROADMAP.md) | Built status and planned work |
