# Thirdweb HTTP Facilitator Validation

This example validates Thirdweb as a managed external x402 facilitator using HTTP directly from the Python OmniClaw codebase.

No TypeScript seller SDK is required for this repo.

OmniClaw uses Thirdweb's public HTTP API:

- `POST https://api.thirdweb.com/v1/payments/x402/accepts`
- `POST https://api.thirdweb.com/v1/payments/x402/verify`
- `POST https://api.thirdweb.com/v1/payments/x402/settle`
- `POST https://api.thirdweb.com/v1/payments/x402/fetch`
- `GET https://api.thirdweb.com/v1/payments/x402/discovery/resources`

## What This Proves

- Thirdweb can handle managed x402 settlement.
- OmniClaw can integrate Thirdweb without competing with it.
- OmniClaw remains the policy and execution control layer.

## Inputs

You need two JSON files from an x402 flow:

- `payment-payload.json` - signed x402 payment payload from the buyer
- `payment-requirements.json` - selected seller payment requirements

These are the same objects passed to x402 facilitator verify/settle calls.

For seller-side requirement generation, OmniClaw can call Thirdweb's `accepts` endpoint through `ThirdwebFacilitator.create_accepts(...)`. This is the API that creates the x402 `accepts` array using the Thirdweb server wallet context.

## Configure

```bash
export THIRDWEB_SECRET_KEY="..."
export THIRDWEB_SERVER_WALLET_ADDRESS="0x..."
```

## Verify Only

```bash
python examples/thirdweb-http-facilitator/verify_settle.py \
  --payment-payload payment-payload.json \
  --payment-requirements payment-requirements.json \
  --verify-only
```

## Verify And Settle

```bash
python examples/thirdweb-http-facilitator/verify_settle.py \
  --payment-payload payment-payload.json \
  --payment-requirements payment-requirements.json
```

## Expected Result

The script prints JSON with:

- facilitator name
- verify result
- settle result when settlement is enabled

## Product Position

Thirdweb settles. OmniClaw governs.

For buyer-side agent flows, the normal command remains:

```bash
omniclaw-cli inspect-x402 --recipient https://seller.example.com/compute
omniclaw-cli pay --recipient https://seller.example.com/compute --idempotency-key job-123
```
