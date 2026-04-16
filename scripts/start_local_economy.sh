#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

preserve_env_var() {
  local name="$1"
  local sentinel="__OMNICLAW_UNSET__"
  local current="${!name-$sentinel}"
  printf '%s' "$current"
}

restore_env_var() {
  local name="$1"
  local value="$2"
  if [[ "$value" != "__OMNICLAW_UNSET__" ]]; then
    export "$name=$value"
  fi
}

PRE_OMNICLAW_NETWORK="$(preserve_env_var OMNICLAW_NETWORK)"
PRE_OMNICLAW_RPC_URL="$(preserve_env_var OMNICLAW_RPC_URL)"
PRE_CIRCLE_API_KEY="$(preserve_env_var CIRCLE_API_KEY)"
PRE_ENTITY_SECRET="$(preserve_env_var ENTITY_SECRET)"
PRE_OMNICLAW_PRIVATE_KEY="$(preserve_env_var OMNICLAW_PRIVATE_KEY)"
PRE_BUYER_CIRCLE_API_KEY="$(preserve_env_var BUYER_CIRCLE_API_KEY)"
PRE_SELLER_CIRCLE_API_KEY="$(preserve_env_var SELLER_CIRCLE_API_KEY)"
PRE_BUYER_ENTITY_SECRET="$(preserve_env_var BUYER_ENTITY_SECRET)"
PRE_SELLER_ENTITY_SECRET="$(preserve_env_var SELLER_ENTITY_SECRET)"
PRE_BUYER_OMNICLAW_PRIVATE_KEY="$(preserve_env_var BUYER_OMNICLAW_PRIVATE_KEY)"
PRE_SELLER_OMNICLAW_PRIVATE_KEY="$(preserve_env_var SELLER_OMNICLAW_PRIVATE_KEY)"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

# Restore caller-provided env so wrapper scripts can force a specific network or key set.
restore_env_var OMNICLAW_NETWORK "$PRE_OMNICLAW_NETWORK"
restore_env_var OMNICLAW_RPC_URL "$PRE_OMNICLAW_RPC_URL"
restore_env_var CIRCLE_API_KEY "$PRE_CIRCLE_API_KEY"
restore_env_var ENTITY_SECRET "$PRE_ENTITY_SECRET"
restore_env_var OMNICLAW_PRIVATE_KEY "$PRE_OMNICLAW_PRIVATE_KEY"
restore_env_var BUYER_CIRCLE_API_KEY "$PRE_BUYER_CIRCLE_API_KEY"
restore_env_var SELLER_CIRCLE_API_KEY "$PRE_SELLER_CIRCLE_API_KEY"
restore_env_var BUYER_ENTITY_SECRET "$PRE_BUYER_ENTITY_SECRET"
restore_env_var SELLER_ENTITY_SECRET "$PRE_SELLER_ENTITY_SECRET"
restore_env_var BUYER_OMNICLAW_PRIVATE_KEY "$PRE_BUYER_OMNICLAW_PRIVATE_KEY"
restore_env_var SELLER_OMNICLAW_PRIVATE_KEY "$PRE_SELLER_OMNICLAW_PRIVATE_KEY"
STATE_DIR="${STATE_DIR:-$ROOT/.runtime}"
mkdir -p "$STATE_DIR"
cp examples/local-economy/payment-agent.policy.json "$STATE_DIR/payment-agent.policy.runtime.json"
cp examples/local-economy/seller-agent.policy.json "$STATE_DIR/seller-agent.policy.runtime.json"
if [[ "${OMNICLAW_DEMO_RESET_POLICY_WALLETS:-0}" == "1" ]]; then
  python3 - <<PY
import json
from pathlib import Path
for name in ["payment-agent.policy.runtime.json", "seller-agent.policy.runtime.json"]:
    p = Path("$STATE_DIR") / name
    data = json.loads(p.read_text())
    for wallet in data.get("wallets", {}).values():
        wallet.pop("wallet_id", None)
        wallet.pop("address", None)
    p.write_text(json.dumps(data, indent=2) + "\n")
PY
fi
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
