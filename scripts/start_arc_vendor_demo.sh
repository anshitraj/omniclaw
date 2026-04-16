#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

export OMNICLAW_NETWORK="ARC-TESTNET"
export OMNICLAW_RPC_URL="https://rpc.testnet.arc.network"
export BUSINESS_COMPUTE_NETWORK="ARC-TESTNET"
export BUSINESS_COMPUTE_EXPLORER_BASE_URL="https://testnet.arcscan.app"
export BUSINESS_COMPUTE_ENABLE_LOCAL_BUYER="false"
# Demo-only cleanup: strip persisted wallet bindings from copied example policies
# so Arc runs start from a clean runtime state.
export OMNICLAW_DEMO_RESET_POLICY_WALLETS="1"

HOST_IP=$(hostname -I | awk '{print $1}')
PUBLIC_BASE="${BUSINESS_COMPUTE_PUBLIC_BASE_URL:-http://${HOST_IP}:8010}"

docker rm -f omniclaw-business-compute-demo business-compute-redis >/dev/null 2>&1 || true
docker compose -p omniclaw-buyer -f examples/local-economy/docker-compose.payment-agent.yml down -v >/dev/null 2>&1 || true
docker compose -p omniclaw-seller -f examples/local-economy/docker-compose.seller-agent.yml down -v >/dev/null 2>&1 || true

bash scripts/start_local_economy.sh >/dev/null

export PAYMENT_AGENT_POLICY_FILE="${PAYMENT_AGENT_POLICY_FILE:-$ROOT/.runtime/payment-agent.policy.runtime.json}"
export SELLER_AGENT_POLICY_FILE="${SELLER_AGENT_POLICY_FILE:-$ROOT/.runtime/seller-agent.policy.runtime.json}"

docker rm -f omniclaw-business-compute-demo >/dev/null 2>&1 || true
docker rm -f business-compute-redis >/dev/null 2>&1 || true
docker run -d --name business-compute-redis --network omniclaw-buyer_default redis:7-alpine >/dev/null

docker run -d \
  --name omniclaw-business-compute-demo \
  --network omniclaw-buyer_default \
  -p 8010:8010 \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e SELLER_OMNICLAW_SERVER_URL="http://seller-agent:9091" \
  -e SELLER_OMNICLAW_TOKEN="seller-agent-token" \
  -e BUYER_OMNICLAW_SERVER_URL="http://payment-agent:9090" \
  -e BUYER_OMNICLAW_TOKEN="payment-agent-token" \
  -e BUSINESS_COMPUTE_PORT="8010" \
  -e BUSINESS_COMPUTE_REDIS_URL="redis://business-compute-redis:6379/0" \
  -e BUSINESS_COMPUTE_PUBLIC_BASE_URL="$PUBLIC_BASE" \
  -e BUSINESS_COMPUTE_NETWORK="$BUSINESS_COMPUTE_NETWORK" \
  -e BUSINESS_COMPUTE_EXPLORER_BASE_URL="$BUSINESS_COMPUTE_EXPLORER_BASE_URL" \
  -e BUSINESS_COMPUTE_ENABLE_LOCAL_BUYER="false" \
  -e UV_PROJECT_ENVIRONMENT="/tmp/omniclaw-business-demo-venv" \
  omniclaw-agent:local \
  sh -lc 'PYTHONPATH=/workspace/src:/workspace uvx --from uvicorn --with fastapi[standard] --with httpx --with redis uvicorn examples.business-compute.app:app --host 0.0.0.0 --port 8010' >/dev/null

docker network connect omniclaw-seller_default omniclaw-business-compute-demo >/dev/null 2>&1 || true

BUSINESS_IP=$(docker inspect omniclaw-business-compute-demo --format '{{with index .NetworkSettings.Networks "omniclaw-buyer_default"}}{{.IPAddress}}{{end}}')
AGENT_BASE="http://${BUSINESS_IP}:8010"
python3 - <<PY
import json
from pathlib import Path
p = Path('.runtime/payment-agent.policy.runtime.json')
data = json.loads(p.read_text())
domains = data['wallets']['payment-agent']['recipients']['domains']
for value in ['${BUSINESS_IP}'.strip(), '${HOST_IP}'.strip(), 'host.docker.internal', '172.17.0.1', '172.18.0.1']:
    if value and value not in domains:
        domains.append(value)
p.write_text(json.dumps(data, indent=2) + '\\n')
PY

docker compose -p omniclaw-buyer -f examples/local-economy/docker-compose.payment-agent.yml up -d --no-build --force-recreate --remove-orphans >/dev/null

printf '\nArc vendor demo is live.\n\n'
printf 'Network: %s\n' "$OMNICLAW_NETWORK"
printf 'RPC: %s\n' "$OMNICLAW_RPC_URL"
printf 'Explorer: %s\n' "$BUSINESS_COMPUTE_EXPLORER_BASE_URL"
printf '\nSeller vendor app:\n'
printf '  Browser URL: http://127.0.0.1:8010\n'
printf '  Buyer-facing base: %s\n' "$PUBLIC_BASE"
printf '  Buyer execution base: %s\n' "$AGENT_BASE"
printf '  Example paid URL: %s/compute?job=prime-count&size=1000\n' "$PUBLIC_BASE"
printf '  Example buyer CLI URL: %s/compute?job=prime-count&size=1000\n' "$AGENT_BASE"
printf '\nBuyer policy engine for Telegram/OpenClaw CLI:\n'
printf '  Server URL: http://%s:9090\n' "$HOST_IP"
printf '  Token: payment-agent-token\n'
printf '  Wallet alias: payment-agent\n'
printf '  Network: %s\n' "$OMNICLAW_NETWORK"
printf '\nSeller policy engine:\n'
printf '  Server URL: http://%s:9091\n' "$HOST_IP"
printf '  Token: seller-agent-token\n'
printf '  Wallet alias: seller-agent\n'
printf '\nOpenClaw prompt:\n'
printf '  pay for this url: %s/compute?job=prime-count&size=1000\n' "$AGENT_BASE"
printf '\nBusiness logs:\n'
printf '  docker logs -f omniclaw-business-compute-demo\n\n'

exec docker logs -f omniclaw-business-compute-demo
