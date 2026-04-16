# Business Compute Demo

A business-facing OmniClaw seller example.

This example is not a CLI seller surface. The business runs its own web app and integrates OmniClaw directly through the seller backend APIs for:
- x402 payment requirements
- x402 payment verification
- Circle Gateway-backed settlement flow

The app exposes paid products over HTTP:
- paid compute jobs
- paid compute sessions with credits
- paid research-paper PDFs

## What It Demonstrates

- buyer agent pays a real x402 URL
- seller business backend stays in control of the product surface
- unpaid access returns `402 Payment Required`
- paid access unlocks only after seller-side verification
- compute sessions, settlement summaries, and event logs persist through Redis

## Run

From the repo root:

```bash
bash scripts/start_business_compute_demo.sh
```

## Arc Vendor Mode

For the shipped Arc-specific flow, use:

```bash
bash scripts/start_arc_vendor_demo.sh
```

This mode is different from the older local demo in one important way:

- the buyer is not a bundled local test button
- the buyer is your real external CLI agent, for example Telegram/OpenClaw
- the launcher deploys the buyer policy engine and seller policy engine
- the browser app acts as the vendor-facing seller surface
- `ARC-TESTNET` is the default network

The launcher prints the buyer policy engine details you need to configure the external CLI agent.

Open in the browser:

```text
http://127.0.0.1:8010
```

The launcher prints the current buyer-pay URL base for the local Docker network.

## Architecture

Components:
- buyer OmniClaw server: `http://localhost:9090`
- seller OmniClaw server: `http://localhost:9091`
- business web app: `http://127.0.0.1:8010`
- business Redis state: `business-compute-redis`

The browser uses `127.0.0.1:8010`, but the buyer agent pays the business app through its Docker-network URL, for example:

```text
http://172.18.0.5:8010/compute?job=prime-count&size=1000
```

## Example Buyer Prompts

Direct compute:

```text
pay for this url: http://172.18.0.5:8010/compute?job=prime-count&size=1000
```

Compute session:

```text
pay for this url: http://172.18.0.5:8010/compute/session?tier=starter
```

Research paper:

```text
pay for this url: http://172.18.0.5:8010/papers/agentic-wallet-control-plane
```

Note: the `172.18.x.x` address can change on restart. Use the URL printed by the launcher or shown on the page.

## Persistence

The following business-app state is persisted in Redis:
- sessions
- session job history
- recent settlements
- seller event log
- revenue and delivery counters
- download counters

This state survives business app restarts.

## Seller Logs

The launcher streams the business container logs. You will see seller-side proof such as:
- `402 Payment Required`
- `200 OK` after payment
- delivery events
- PDF download events

## Product Surface

This example is intentionally business-first.

The business is not presented as another agent using `omniclaw-cli`.
The business owns the API surface, while OmniClaw provides the payment and control layer underneath.

In Arc vendor mode:

- the buyer uses `omniclaw-cli` externally
- the seller is a vendor web app
- both policy engines run on `ARC-TESTNET`
- the business app shows the payment flow, deliveries, and settlement visibility
