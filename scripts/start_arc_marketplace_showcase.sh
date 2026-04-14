#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

export OMNICLAW_NETWORK="${OMNICLAW_NETWORK:-ARC-TESTNET}"
export OMNICLAW_RPC_URL="${OMNICLAW_RPC_URL:-https://rpc.testnet.arc.network}"
export OMNICLAW_X402_EXACT_NETWORK_PROFILE="${OMNICLAW_X402_EXACT_NETWORK_PROFILE:-ARC-TESTNET}"
export OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE="${OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE:-ARC-TESTNET}"
export OMNICLAW_X402_FACILITATOR_RPC_URL="${OMNICLAW_X402_FACILITATOR_RPC_URL:-https://rpc.testnet.arc.network}"
export OMNICLAW_X402_FACILITATOR_NETWORKS="${OMNICLAW_X402_FACILITATOR_NETWORKS:-eip155:5042002}"
export OMNICLAW_X402_FACILITATOR_PORT="${OMNICLAW_X402_FACILITATOR_PORT:-4022}"
export OMNICLAW_X402_EXACT_FACILITATOR_URL="${OMNICLAW_X402_EXACT_FACILITATOR_URL:-http://127.0.0.1:${OMNICLAW_X402_FACILITATOR_PORT}}"
export ARC_MARKETPLACE_PORT="${ARC_MARKETPLACE_PORT:-8020}"
export ARC_MARKETPLACE_PUBLIC_BASE_URL="${ARC_MARKETPLACE_PUBLIC_BASE_URL:-http://127.0.0.1:${ARC_MARKETPLACE_PORT}}"
export ARC_MARKETPLACE_BUYER_BASE_URL="${ARC_MARKETPLACE_BUYER_BASE_URL:-$ARC_MARKETPLACE_PUBLIC_BASE_URL}"
export ARC_MARKETPLACE_EXPLORER_BASE_URL="${ARC_MARKETPLACE_EXPLORER_BASE_URL:-https://testnet.arcscan.app/tx/}"

if [[ -z "${OMNICLAW_X402_FACILITATOR_PRIVATE_KEY:-}" ]]; then
  export OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="${OMNICLAW_PRIVATE_KEY:-}"
fi

if [[ -z "${OMNICLAW_X402_FACILITATOR_PRIVATE_KEY:-}" ]]; then
  echo "Missing OMNICLAW_X402_FACILITATOR_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY"
  exit 1
fi

if [[ -z "${OMNICLAW_PRIVATE_KEY:-}" && -z "${OMNICLAW_X402_EXACT_PAY_TO:-}" ]]; then
  echo "Missing OMNICLAW_PRIVATE_KEY or OMNICLAW_X402_EXACT_PAY_TO for seller payTo"
  exit 1
fi

RUNTIME_DIR="$ROOT/.runtime/arc-marketplace-showcase"
mkdir -p "$RUNTIME_DIR"

cleanup() {
  if [[ -f "$RUNTIME_DIR/facilitator.pid" ]]; then
    kill "$(cat "$RUNTIME_DIR/facilitator.pid")" >/dev/null 2>&1 || true
  fi
  if [[ -f "$RUNTIME_DIR/kiosk.pid" ]]; then
    kill "$(cat "$RUNTIME_DIR/kiosk.pid")" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

cleanup

uv run python scripts/start_x402_exact_testnet_facilitator.py \
  >"$RUNTIME_DIR/facilitator.log" 2>&1 &
echo "$!" > "$RUNTIME_DIR/facilitator.pid"

sleep 2

uv run uvicorn app:app \
  --app-dir examples/arc-marketplace-showcase \
  --host 0.0.0.0 \
  --port "$ARC_MARKETPLACE_PORT" \
  >"$RUNTIME_DIR/kiosk.log" 2>&1 &
echo "$!" > "$RUNTIME_DIR/kiosk.pid"

sleep 2

cat <<EOF

OmniClaw Arc Marketplace Showcase is live.

Network:
  Profile: $OMNICLAW_X402_EXACT_NETWORK_PROFILE
  RPC:     $OMNICLAW_X402_FACILITATOR_RPC_URL
  ArcScan: $ARC_MARKETPLACE_EXPLORER_BASE_URL<tx>

Services:
  Kiosk UI:      http://127.0.0.1:$ARC_MARKETPLACE_PORT
  Facilitator:   $OMNICLAW_X402_EXACT_FACILITATOR_URL

Paid URLs:
  $ARC_MARKETPLACE_BUYER_BASE_URL/buy/prime-market-scan
  $ARC_MARKETPLACE_BUYER_BASE_URL/buy/risk-oracle-brief
  $ARC_MARKETPLACE_BUYER_BASE_URL/buy/settlement-receipt-kit

OpenClaw prompt:
  pay for this url: $ARC_MARKETPLACE_BUYER_BASE_URL/buy/prime-market-scan

Buyer CLI equivalent:
  omniclaw-cli inspect-x402 --recipient "$ARC_MARKETPLACE_BUYER_BASE_URL/buy/prime-market-scan"
  omniclaw-cli pay --recipient "$ARC_MARKETPLACE_BUYER_BASE_URL/buy/prime-market-scan" --idempotency-key "arc-kiosk-\$(date +%s)"

Logs:
  tail -f $RUNTIME_DIR/facilitator.log
  tail -f $RUNTIME_DIR/kiosk.log

Press Ctrl+C to stop both services.

EOF

tail -f "$RUNTIME_DIR/facilitator.log" "$RUNTIME_DIR/kiosk.log"
