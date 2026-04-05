#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
STATE_DIR="${STATE_DIR:-$ROOT/.runtime}"
mkdir -p "$STATE_DIR"
cp examples/local-economy/payment-agent.policy.json "$STATE_DIR/payment-agent.policy.runtime.json"
cp examples/local-economy/seller-agent.policy.json "$STATE_DIR/seller-agent.policy.runtime.json"
HOST_IP=$(hostname -I | awk '{print $1}')
python3 - <<PY
import json
from pathlib import Path
host_ip = "${HOST_IP}".strip()
p = Path("$STATE_DIR/payment-agent.policy.runtime.json")
data = json.loads(p.read_text())
domains = data["wallets"]["payment-agent"]["recipients"]["domains"]
for value in [host_ip, "host.docker.internal", "172.17.0.1", "172.18.0.1"]:
    if value and value not in domains:
        domains.append(value)
p.write_text(json.dumps(data, indent=2) + "\n")
PY
export PAYMENT_AGENT_POLICY_FILE="$STATE_DIR/payment-agent.policy.runtime.json"
export SELLER_AGENT_POLICY_FILE="$STATE_DIR/seller-agent.policy.runtime.json"

IMAGE_TAG="${OMNICLAW_AGENT_IMAGE:-omniclaw-agent:local}"
if [[ "${OMNICLAW_DEMO_REBUILD:-0}" == "1" ]] || ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "Building $IMAGE_TAG ..."
  DOCKER_BUILDKIT=0 docker build -t "$IMAGE_TAG" -f Dockerfile.agent .
fi

docker compose -p "${BUYER_PROJECT_NAME:-omniclaw-buyer}" -f examples/local-economy/docker-compose.payment-agent.yml up -d --no-build --remove-orphans
sleep 2
docker compose -p "${SELLER_PROJECT_NAME:-omniclaw-seller}" -f examples/local-economy/docker-compose.seller-agent.yml up -d --no-build --remove-orphans
HOST_IP=$(hostname -I | awk '{print $1}')
printf 'Buyer server: http://localhost:9090\n'
printf 'Buyer token: payment-agent-token\n'
printf 'Buyer wallet: payment-agent\n'
printf 'Seller server: http://localhost:9091\n'
printf 'Seller token: seller-agent-token\n'
printf 'Seller wallet: seller-agent\n'
printf 'Seller paid URL for buyer: http://172.17.0.1:8000/ping\n'
printf 'Seller paid URL for other local/LAN clients: http://%s:8000/ping\n' "$HOST_IP"
printf 'Runtime buyer policy: %s\n' "$PAYMENT_AGENT_POLICY_FILE"
printf 'Runtime seller policy: %s\n' "$SELLER_AGENT_POLICY_FILE"
