#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

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
  -e UV_PROJECT_ENVIRONMENT="/tmp/omniclaw-business-demo-venv" \
  omniclaw-agent:local \
  sh -lc 'PYTHONPATH=/workspace/src:/workspace uvx --from uvicorn --with fastapi[standard] --with httpx --with redis uvicorn examples.business-compute.app:app --host 0.0.0.0 --port 8010' >/dev/null

docker network connect omniclaw-seller_default omniclaw-business-compute-demo >/dev/null 2>&1 || true

BUSINESS_IP=$(docker inspect omniclaw-business-compute-demo --format '{{with index .NetworkSettings.Networks "omniclaw-buyer_default"}}{{.IPAddress}}{{end}}')
python3 - <<PY
import json
from pathlib import Path
p = Path('.runtime/payment-agent.policy.runtime.json')
data = json.loads(p.read_text())
domains = data['wallets']['payment-agent']['recipients']['domains']
ip = '${BUSINESS_IP}'.strip()
if ip and ip not in domains:
    domains.append(ip)
p.write_text(json.dumps(data, indent=2) + '\n')
PY

docker compose -p omniclaw-buyer -f examples/local-economy/docker-compose.payment-agent.yml up -d --no-build --force-recreate --remove-orphans >/dev/null

printf 'Business compute demo: http://127.0.0.1:8010\n'
printf 'Buyer pay URL: http://%s:8010/compute?job=prime-count&size=1000\n' "$BUSINESS_IP"
printf 'Business container logs: docker logs -f omniclaw-business-compute-demo\n'

exec docker logs -f omniclaw-business-compute-demo
