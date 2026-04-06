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
