# External x402 Facilitator Validation

This example validates OmniClaw against an external standard x402 `exact` facilitator.

Use this first for standard external-facilitator validation. The default path uses the public x402.org facilitator on Base Sepolia.

## What This Proves

- seller advertises standard x402 `exact` requirements
- settlement goes through an external facilitator
- OmniClaw buyer can inspect and pay through `/api/v1/pay`
- no OmniClaw self-hosted facilitator is required for this path

## Seller: x402.org On Base Sepolia

Preferred setup:

```bash
export OMNICLAW_PRIVATE_KEY="0xYourSellerPrivateKey"
```

Start the seller:

```bash
python scripts/start_external_x402_seller.py
```

Defaults:

```env
OMNICLAW_X402_EXACT_NETWORK_PROFILE=BASE-SEPOLIA
OMNICLAW_X402_EXACT_NETWORK=eip155:84532
OMNICLAW_X402_EXACT_PRICE=$0.25
OMNICLAW_X402_EXACT_FACILITATOR_URL=https://x402.org/facilitator
OMNICLAW_X402_EXACT_PORT=4021
```

The seller harness derives `payTo` from `OMNICLAW_PRIVATE_KEY` by default.

Optional override:

```bash
export OMNICLAW_X402_EXACT_PAY_TO="0xYourSellerAddress"
```

Use that override only when you intentionally want to advertise a payout address different from the runtime key.

Paid endpoint:

```text
http://127.0.0.1:4021/compute?size=70000
```

## Buyer: OmniClaw CLI

Point the CLI at the buyer Financial Policy Engine:

```bash
export OMNICLAW_SERVER_URL="http://127.0.0.1:8080"
export OMNICLAW_TOKEN="my-agent-token"
```

Inspect:

```bash
omniclaw-cli inspect-x402 \
  --recipient http://127.0.0.1:4021/compute?size=70000
```

Pay:

```bash
omniclaw-cli pay \
  --recipient http://127.0.0.1:4021/compute?size=70000 \
  --idempotency-key x402-org-base-sepolia-001
```

## Success Criteria

- `inspect-x402` selects `x402`
- selected payment source is `direct_wallet`
- selected network is `eip155:84532`
- payment settles
- paid compute response unlocks
- transaction hash appears in the response metadata

## Product Meaning

If this passes, the supported product claim is:

`OmniClaw supports external standard x402 exact facilitators. The buyer remains policy-controlled, while the seller can settle through an external facilitator such as x402.org.`

Thirdweb remains the next managed facilitator target once account access is available.

## Layer Ownership

For this flow:

- seller harness creates the `accepts` requirements
- x402.org handles `verify` and `settle`
- OmniClaw buyer policy engine inspects, approves, and signs the allowed payment
