#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

IMAGE_TAG="${OMNICLAW_AGENT_IMAGE:-omniclaw-agent:local}"
NETWORK_NAME="${ARC_MARKETPLACE_DOCKER_NETWORK:-omniclaw-buyer_default}"
SUBNET="${ARC_MARKETPLACE_DOCKER_SUBNET:-172.18.0.0/16}"
FACILITATOR_IP="${ARC_MARKETPLACE_FACILITATOR_IP:-172.18.0.50}"
KIOSK_IP="${ARC_MARKETPLACE_KIOSK_IP:-172.18.0.51}"
BUYER_IP="${ARC_MARKETPLACE_BUYER_IP:-172.18.0.52}"
ARC_RPC_URL="${ARC_MARKETPLACE_RPC_URL:-https://rpc.testnet.arc.network}"
ARC_USDC_ADDRESS="${ARC_MARKETPLACE_USDC_ADDRESS:-0x3600000000000000000000000000000000000000}"
SELLER_KEY="${SELLER_OMNICLAW_PRIVATE_KEY:-${OMNICLAW_X402_FACILITATOR_PRIVATE_KEY:-}}"
BUYER_KEY="${BUYER_OMNICLAW_PRIVATE_KEY:-${OMNICLAW_PRIVATE_KEY:-}}"
BUYER_TOKEN="${ARC_MARKETPLACE_BUYER_TOKEN:-payment-agent-token}"
POLICY_PATH="$ROOT/.runtime/arc-marketplace-showcase/buyer.policy.json"

if ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "Missing Docker image $IMAGE_TAG"
  echo "Build it with: DOCKER_BUILDKIT=0 docker build -t $IMAGE_TAG -f Dockerfile.agent ."
  exit 1
fi

if [[ -z "$SELLER_KEY" ]]; then
  echo "Missing SELLER_OMNICLAW_PRIVATE_KEY or OMNICLAW_X402_FACILITATOR_PRIVATE_KEY"
  exit 1
fi

if [[ -z "$BUYER_KEY" ]]; then
  echo "Missing BUYER_OMNICLAW_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY"
  exit 1
fi

if [[ -z "${BUYER_CIRCLE_API_KEY:-${CIRCLE_API_KEY:-}}" ]]; then
  echo "Missing BUYER_CIRCLE_API_KEY or CIRCLE_API_KEY"
  exit 1
fi

if [[ -z "${BUYER_ENTITY_SECRET:-${ENTITY_SECRET:-}}" ]]; then
  echo "Missing BUYER_ENTITY_SECRET or ENTITY_SECRET"
  exit 1
fi

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  docker network create --subnet "$SUBNET" "$NETWORK_NAME" >/dev/null
fi

wait_for_http() {
  local label="$1"
  local url="$2"
  local container="$3"
  local deadline=$((SECONDS + 180))

  while ((SECONDS < deadline)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for $label at $url"
  echo "Recent $container logs:"
  docker logs --tail 80 "$container" || true
  return 1
}

mkdir -p "$(dirname "$POLICY_PATH")"

SELLER_ADDR=$(SELLER_KEY="$SELLER_KEY" uv run python - <<'PY'
from eth_account import Account
import os
print(Account.from_key(os.environ["SELLER_KEY"]).address)
PY
)

BUYER_ADDR=$(BUYER_KEY="$BUYER_KEY" uv run python - <<'PY'
from eth_account import Account
import os
print(Account.from_key(os.environ["BUYER_KEY"]).address)
PY
)

BUYER_USDC_BALANCE=$(BUYER_ADDR="$BUYER_ADDR" ARC_RPC_URL="$ARC_RPC_URL" ARC_USDC_ADDRESS="$ARC_USDC_ADDRESS" uv run python - <<'PY'
import os
from decimal import Decimal

try:
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(os.environ["ARC_RPC_URL"], request_kwargs={"timeout": 5}))
    token = w3.eth.contract(
        address=Web3.to_checksum_address(os.environ["ARC_USDC_ADDRESS"]),
        abi=[
            {
                "inputs": [{"name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"type": "uint256"}],
                "stateMutability": "view",
                "type": "function",
            }
        ],
    )
    balance = token.functions.balanceOf(Web3.to_checksum_address(os.environ["BUYER_ADDR"])).call()
    print(Decimal(balance) / Decimal(10**6))
except Exception:
    print("unknown")
PY
)

SELLER_NATIVE_BALANCE=$(SELLER_ADDR="$SELLER_ADDR" ARC_RPC_URL="$ARC_RPC_URL" uv run python - <<'PY'
import os
from decimal import Decimal

try:
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(os.environ["ARC_RPC_URL"], request_kwargs={"timeout": 5}))
    balance = w3.eth.get_balance(Web3.to_checksum_address(os.environ["SELLER_ADDR"]))
    print(Decimal(balance) / Decimal(10**18))
except Exception:
    print("unknown")
PY
)

BUYER_ADDR="$BUYER_ADDR" BUYER_TOKEN="$BUYER_TOKEN" KIOSK_IP="$KIOSK_IP" python3 - <<'PY'
import json
import os
from pathlib import Path

policy = {
    "version": "2.0",
    "tokens": {
        os.environ["BUYER_TOKEN"]: {
            "wallet_alias": "payment-agent",
            "active": True,
            "label": "Arc Marketplace Buyer Agent",
        }
    },
    "wallets": {
        "payment-agent": {
            "name": "Arc Marketplace Buyer Agent",
            "address": os.environ["BUYER_ADDR"],
            "limits": {
                "daily_max": "10.00",
                "hourly_max": "5.00",
                "per_tx_max": "1.00",
                "per_tx_min": "0.01",
            },
            "rate_limits": {"per_minute": 10, "per_hour": 100},
            "recipients": {
                "mode": "whitelist",
                "addresses": [],
                "domains": [
                    "localhost",
                    "127.0.0.1",
                    os.environ["KIOSK_IP"],
                    "omniclaw-arc-kiosk",
                ],
            },
            "confirm_threshold": None,
        }
    },
}

path = Path(".runtime/arc-marketplace-showcase/buyer.policy.json")
path.write_text(json.dumps(policy, indent=2) + "\n")
PY

docker rm -f omniclaw-arc-facilitator omniclaw-arc-kiosk omniclaw-arc-buyer >/dev/null 2>&1 || true

docker run -d \
  --name omniclaw-arc-facilitator \
  --network "$NETWORK_NAME" \
  --ip "$FACILITATOR_IP" \
  -p 4022:4022 \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e OMNICLAW_X402_FACILITATOR_PRIVATE_KEY="$SELLER_KEY" \
  -e OMNICLAW_X402_FACILITATOR_NETWORK_PROFILE="ARC-TESTNET" \
  -e OMNICLAW_X402_FACILITATOR_RPC_URL="$ARC_RPC_URL" \
  -e OMNICLAW_X402_FACILITATOR_NETWORKS="eip155:5042002" \
  -e OMNICLAW_X402_FACILITATOR_PORT="4022" \
  -e UV_PROJECT_ENVIRONMENT="/tmp/omniclaw-arc-facilitator-venv" \
  "$IMAGE_TAG" \
  sh -lc 'git config --global --add safe.directory /workspace && PYTHONPATH=/workspace/src:/workspace uv run python scripts/start_x402_exact_testnet_facilitator.py' >/dev/null

docker run -d \
  --name omniclaw-arc-kiosk \
  --network "$NETWORK_NAME" \
  --ip "$KIOSK_IP" \
  -p 8020:8020 \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e OMNICLAW_X402_EXACT_PAY_TO="$SELLER_ADDR" \
  -e OMNICLAW_X402_EXACT_NETWORK_PROFILE="ARC-TESTNET" \
  -e OMNICLAW_X402_EXACT_NETWORK="eip155:5042002" \
  -e OMNICLAW_X402_EXACT_FACILITATOR_URL="http://$FACILITATOR_IP:4022" \
  -e ARC_MARKETPLACE_PORT="8020" \
  -e ARC_MARKETPLACE_PUBLIC_BASE_URL="http://127.0.0.1:8020" \
  -e ARC_MARKETPLACE_BUYER_BASE_URL="http://$KIOSK_IP:8020" \
  -e ARC_MARKETPLACE_BUYER_ENGINE_URL="http://$BUYER_IP:8080" \
  -e ARC_MARKETPLACE_BUYER_TOKEN="$BUYER_TOKEN" \
  -e ARC_MARKETPLACE_EXPLORER_BASE_URL="https://testnet.arcscan.app/tx/" \
  -e UV_PROJECT_ENVIRONMENT="/tmp/omniclaw-arc-kiosk-venv" \
  "$IMAGE_TAG" \
  sh -lc 'git config --global --add safe.directory /workspace && PYTHONPATH=/workspace/src:/workspace uv run uvicorn app:app --app-dir examples/arc-marketplace-showcase --host 0.0.0.0 --port 8020' >/dev/null

docker run -d \
  --name omniclaw-arc-buyer \
  --network "$NETWORK_NAME" \
  --ip "$BUYER_IP" \
  -p 8080:8080 \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e CIRCLE_API_KEY="${BUYER_CIRCLE_API_KEY:-$CIRCLE_API_KEY}" \
  -e ENTITY_SECRET="${BUYER_ENTITY_SECRET:-$ENTITY_SECRET}" \
  -e OMNICLAW_PRIVATE_KEY="$BUYER_KEY" \
  -e OMNICLAW_NETWORK="ARC-TESTNET" \
  -e OMNICLAW_RPC_URL="$ARC_RPC_URL" \
  -e OMNICLAW_AGENT_POLICY_PATH="/workspace/.runtime/arc-marketplace-showcase/buyer.policy.json" \
  -e OMNICLAW_AGENT_TOKEN="$BUYER_TOKEN" \
  -e OMNICLAW_STORAGE_BACKEND="memory" \
  -e OMNICLAW_POLICY_RELOAD_INTERVAL="0" \
  -e UV_PROJECT_ENVIRONMENT="/tmp/omniclaw-arc-buyer-venv" \
  "$IMAGE_TAG" \
  sh -lc 'git config --global --add safe.directory /workspace && PYTHONPATH=/workspace/src:/workspace uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port 8080 --log-level info' >/dev/null

wait_for_http "facilitator" "http://127.0.0.1:4022/supported" "omniclaw-arc-facilitator"
wait_for_http "vendor kiosk" "http://127.0.0.1:8020/api/catalog" "omniclaw-arc-kiosk"
wait_for_http "buyer policy engine" "http://127.0.0.1:8080/api/v1/health" "omniclaw-arc-buyer"

printf '\nOmniClaw Arc Marketplace Docker showcase is ready.\n\n'
printf 'Network:        %s\n' "$NETWORK_NAME"
printf 'Facilitator:    http://%s:4022\n' "$FACILITATOR_IP"
printf 'Vendor kiosk:   http://%s:8020\n' "$KIOSK_IP"
printf 'Buyer engine:   http://%s:8080\n' "$BUYER_IP"
printf 'Browser UI:     http://127.0.0.1:8020\n'
printf 'Buyer address:  %s\n' "$BUYER_ADDR"
printf 'Seller address: %s\n' "$SELLER_ADDR"
printf 'Buyer Arc USDC: %s\n' "$BUYER_USDC_BALANCE"
printf 'Seller Arc gas: %s\n' "$SELLER_NATIVE_BALANCE"
printf '\nPaid products:\n'
printf '  Prime Market Scan:       $0.25  http://%s:8020/buy/prime-market-scan\n' "$KIOSK_IP"
printf '  Risk Oracle Brief:       $0.15  http://%s:8020/buy/risk-oracle-brief\n' "$KIOSK_IP"
printf '  Settlement Receipt Kit:  $0.10  http://%s:8020/buy/settlement-receipt-kit\n' "$KIOSK_IP"
printf '\nOpenClaw config:\n'
printf '  OMNICLAW_SERVER_URL=http://%s:8080\n' "$BUYER_IP"
printf '  OMNICLAW_TOKEN=%s\n' "$BUYER_TOKEN"
printf '\nOpenClaw prompt:\n'
printf '  pay for this url: http://%s:8020/buy/prime-market-scan\n' "$KIOSK_IP"
printf '\nCLI test:\n'
printf '  OMNICLAW_SERVER_URL=http://127.0.0.1:8080 OMNICLAW_TOKEN=%s omniclaw-cli inspect-x402 --recipient "http://%s:8020/buy/prime-market-scan"\n' "$BUYER_TOKEN" "$KIOSK_IP"
printf '  OMNICLAW_SERVER_URL=http://127.0.0.1:8080 OMNICLAW_TOKEN=%s omniclaw-cli pay --recipient "http://%s:8020/buy/prime-market-scan" --idempotency-key "arc-kiosk-$(date +%%s)"\n' "$BUYER_TOKEN" "$KIOSK_IP"
printf '\nIf buyer Arc USDC is below $0.25, test the $0.10 endpoint first:\n'
printf '  OMNICLAW_SERVER_URL=http://127.0.0.1:8080 OMNICLAW_TOKEN=%s omniclaw-cli pay --recipient "http://%s:8020/buy/settlement-receipt-kit" --idempotency-key "arc-kiosk-$(date +%%s)"\n' "$BUYER_TOKEN" "$KIOSK_IP"
printf '\nLogs:\n'
printf '  docker logs -f omniclaw-arc-facilitator\n'
printf '  docker logs -f omniclaw-arc-kiosk\n'
printf '  docker logs -f omniclaw-arc-buyer\n\n'
