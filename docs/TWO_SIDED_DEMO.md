# Two-Sided OmniClaw CLI Demo

This demo shows both sides of the economy:
- **Seller** exposes a paid x402 URL.
- **Buyer** pays that URL through OmniClaw + Circle nanopayments.

It uses:
- `examples/agent/seller/policy.json`
- `examples/agent/buyer/policy.json`
- `scripts/demo_two_sided.sh`

Note: the script copies policy files into per-run `logs/demo_<timestamp>/...runtime.json`
so your checked-in policy files are not modified during the demo.

## 1. Preflight

```bash
./scripts/demo_two_sided.sh --check-only
```

This validates required env keys from `.env` without printing secrets.

## 2. ETH Sepolia Demo (recommended first)

If your default ports are already used:

```bash
./scripts/demo_two_sided.sh \
  --seller-cp-port 8181 \
  --buyer-cp-port 8182 \
  --seller-gate-port 9101
```

Optional full flow attempt (pay from buyer to seller URL):

```bash
./scripts/demo_two_sided.sh \
  --seller-cp-port 8181 \
  --buyer-cp-port 8182 \
  --seller-gate-port 9101 \
  --run-payment
```

Keep services running for live walkthrough:

```bash
./scripts/demo_two_sided.sh \
  --seller-cp-port 8181 \
  --buyer-cp-port 8182 \
  --seller-gate-port 9101 \
  --hold
```

## 3. Base Sepolia Variant

```bash
./scripts/demo_two_sided.sh \
  --network BASE-SEPOLIA \
  --rpc-url https://base-sepolia-rpc.publicnode.com \
  --seller-cp-port 8181 \
  --buyer-cp-port 8182 \
  --seller-gate-port 9101
```

## 4. Logs

Each run writes logs under:

```text
logs/demo_<timestamp>/
```

Files include:
- `seller-control-plane.log` - seller Financial Policy Engine log
- `buyer-control-plane.log` - buyer Financial Policy Engine log
- `seller-gateway.log`
- `seller-cli.log`
- `buyer-cli.log`
