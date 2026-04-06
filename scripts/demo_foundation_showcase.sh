#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR_DEFAULT="$ROOT_DIR/logs/foundation_demo_$RUN_TS"

ENV_FILE="$ROOT_DIR/.env"
NETWORK="ETH-SEPOLIA"
RPC_URL="${OMNICLAW_RPC_URL:-}"
LOG_DIR="$LOG_DIR_DEFAULT"

BUYER_CP_PORT=9190
SELLER_CP_PORT=9191
SELLER_GATE_PORT=9291

BUYER_TOKEN="payment-agent-token"
BUYER_ALIAS="omni-bot-v4"
SELLER_TOKEN="seller-agent-token"
SELLER_ALIAS="seller-api"
OWNER_TOKEN="foundation-demo-owner"

BLOCKED_URL="https://sensayhack-402.onrender.com"
ALLOWED_URL="https://api.stripe.com"
PRICE="0.01"
ENDPOINT="/api/data"
SELLER_EXEC_CMD='printf "{\"result\":\"premium data unlocked\",\"provider\":\"agent-a\",\"settlement\":\"gateway-batched\",\"transport\":\"x402\"}\n"'
CLI_RETRY_ATTEMPTS=5

HOLD=0

PIDS=()

usage() {
  cat <<'EOF'
Usage: scripts/demo_foundation_showcase.sh [options]

Options:
  --env-file <path>           Path to env file (default: .env)
  --network <name>            ETH-SEPOLIA or BASE-SEPOLIA
  --base                      Shortcut for --network BASE-SEPOLIA
  --eth                       Shortcut for --network ETH-SEPOLIA
  --rpc-url <url>             Override RPC URL
  --buyer-cp-port <port>      Buyer control plane port (default: 9190)
  --seller-cp-port <port>     Seller control plane port (default: 9191)
  --seller-gate-port <port>   Seller gate port (default: 9291)
  --blocked-url <url>         URL that should be blocked by policy
  --allowed-url <url>         URL that should be allowed by policy
  --price <usd>               Price for seller endpoint (default: 0.01)
  --endpoint <path>           Seller gated path (default: /api/data)
  --seller-exec <command>     Command executed after successful payment
  --log-dir <path>            Log directory
  --owner-token <token>       Owner token used for confirmation step
  --hold                      Keep processes alive after the showcase
  -h, --help                  Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --network) NETWORK="$2"; shift 2 ;;
    --base) NETWORK="BASE-SEPOLIA"; shift ;;
    --eth) NETWORK="ETH-SEPOLIA"; shift ;;
    --rpc-url) RPC_URL="$2"; shift 2 ;;
    --buyer-cp-port) BUYER_CP_PORT="$2"; shift 2 ;;
    --seller-cp-port) SELLER_CP_PORT="$2"; shift 2 ;;
    --seller-gate-port) SELLER_GATE_PORT="$2"; shift 2 ;;
    --blocked-url) BLOCKED_URL="$2"; shift 2 ;;
    --allowed-url) ALLOWED_URL="$2"; shift 2 ;;
    --price) PRICE="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --seller-exec) SELLER_EXEC_CMD="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --owner-token) OWNER_TOKEN="$2"; shift 2 ;;
    --hold) HOLD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

if [[ "$NETWORK" != "ETH-SEPOLIA" && "$NETWORK" != "BASE-SEPOLIA" ]]; then
  echo "Unsupported network: $NETWORK" >&2
  exit 1
fi

if [[ -z "$RPC_URL" ]]; then
  if [[ "$NETWORK" == "ETH-SEPOLIA" ]]; then
    RPC_URL="https://ethereum-sepolia-rpc.publicnode.com"
  else
    RPC_URL="https://base-sepolia-rpc.publicnode.com"
  fi
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd uv
require_cmd curl
require_cmd jq
require_cmd python3
require_cmd base64
require_cmd awk
require_cmd omniclaw-cli

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

pick_env() {
  local preferred="$1"
  local fallback="$2"
  if [[ -n "${!preferred:-}" ]]; then
    printf "%s" "${!preferred}"
    return 0
  fi
  if [[ -n "${!fallback:-}" ]]; then
    printf "%s" "${!fallback}"
    return 0
  fi
  return 1
}

BUYER_CIRCLE_API_KEY="$(pick_env BUYER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
SELLER_CIRCLE_API_KEY="$(pick_env SELLER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
BUYER_ENTITY_SECRET="$(pick_env BUYER_ENTITY_SECRET ENTITY_SECRET || true)"
SELLER_ENTITY_SECRET="$(pick_env SELLER_ENTITY_SECRET ENTITY_SECRET || true)"
BUYER_PRIVATE_KEY="$(pick_env BUYER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"
SELLER_PRIVATE_KEY="$(pick_env SELLER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"
OMNICLAW_LOG_LEVEL="${OMNICLAW_LOG_LEVEL:-INFO}"

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Missing required value: $name" >&2
    exit 1
  fi
}

require_value "BUYER_CIRCLE_API_KEY or CIRCLE_API_KEY" "$BUYER_CIRCLE_API_KEY"
require_value "SELLER_CIRCLE_API_KEY or CIRCLE_API_KEY" "$SELLER_CIRCLE_API_KEY"
require_value "BUYER_ENTITY_SECRET or ENTITY_SECRET" "$BUYER_ENTITY_SECRET"
require_value "SELLER_ENTITY_SECRET or ENTITY_SECRET" "$SELLER_ENTITY_SECRET"
require_value "BUYER_OMNICLAW_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY" "$BUYER_PRIVATE_KEY"
require_value "SELLER_OMNICLAW_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY" "$SELLER_PRIVATE_KEY"

mkdir -p "$LOG_DIR"

BUYER_POLICY_SRC="$ROOT_DIR/examples/demo/foundation/buyer-policy.json"
SELLER_POLICY_SRC="$ROOT_DIR/examples/demo/foundation/seller-policy.json"
BUYER_POLICY_RUNTIME="$LOG_DIR/buyer-policy.runtime.json"
SELLER_POLICY_RUNTIME="$LOG_DIR/seller-policy.runtime.json"
cp "$BUYER_POLICY_SRC" "$BUYER_POLICY_RUNTIME"
cp "$SELLER_POLICY_SRC" "$SELLER_POLICY_RUNTIME"

BUYER_CONFIG_DIR="$LOG_DIR/buyer-cli-config"
SELLER_CONFIG_DIR="$LOG_DIR/seller-cli-config"
mkdir -p "$BUYER_CONFIG_DIR" "$SELLER_CONFIG_DIR"

BUYER_CP_LOG="$LOG_DIR/buyer-control-plane.log"
SELLER_CP_LOG="$LOG_DIR/seller-control-plane.log"
SELLER_GATE_LOG="$LOG_DIR/seller-gateway.log"
BUYER_CLI_LOG="$LOG_DIR/buyer-cli.log"
SELLER_CLI_LOG="$LOG_DIR/seller-cli.log"

banner() {
  printf '\n================================================================\n'
  printf ' %s\n' "$1"
  printf '================================================================\n'
}

section() {
  printf '\n%s\n' "$1"
}

kv() {
  printf '  %-18s %s\n' "$1" "$2"
}

show_cmd() {
  printf '\n$ %s\n' "$1"
}

port_in_use() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", port))
except OSError:
    print("in-use")
    sys.exit(0)
finally:
    s.close()
print("free")
PY
}

cleanup() {
  local rc=$?
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  if [[ $rc -ne 0 ]]; then
    printf '\nDemo failed. Logs: %s\n' "$LOG_DIR" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

start_bg() {
  local logfile="$1"
  shift
  ("$@") >"$logfile" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  sleep 0.4
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    tail -n 80 "$logfile" >&2 || true
    exit 1
  fi
}

wait_for_http_ok() {
  local url="$1"
  local timeout_secs="${2:-90}"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if (( "$(date +%s)" - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

wait_for_http_status() {
  local url="$1"
  local expected_status="$2"
  local timeout_secs="${3:-90}"
  local start_ts http_code
  start_ts="$(date +%s)"
  while true; do
    http_code="$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)"
    if [[ "$http_code" == "$expected_status" ]]; then
      return 0
    fi
    if (( "$(date +%s)" - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

cli_json_once() {
  local side="$1"
  shift
  local config_dir server_url token owner_token wallet circle_key entity_secret private_key log_file
  if [[ "$side" == "buyer" ]]; then
    config_dir="$BUYER_CONFIG_DIR"
    server_url="http://127.0.0.1:$BUYER_CP_PORT"
    token="$BUYER_TOKEN"
    owner_token="$OWNER_TOKEN"
    wallet="$BUYER_ALIAS"
    circle_key="$BUYER_CIRCLE_API_KEY"
    entity_secret="$BUYER_ENTITY_SECRET"
    private_key="$BUYER_PRIVATE_KEY"
    log_file="$BUYER_CLI_LOG"
  else
    config_dir="$SELLER_CONFIG_DIR"
    server_url="http://127.0.0.1:$SELLER_CP_PORT"
    token="$SELLER_TOKEN"
    owner_token=""
    wallet="$SELLER_ALIAS"
    circle_key="$SELLER_CIRCLE_API_KEY"
    entity_secret="$SELLER_ENTITY_SECRET"
    private_key="$SELLER_PRIVATE_KEY"
    log_file="$SELLER_CLI_LOG"
  fi

  {
    echo
    echo ">>> [$side] omniclaw-cli $*"
  } >>"$log_file"

  (
    cd "$ROOT_DIR"
    OMNICLAW_CONFIG_DIR="$config_dir" \
    OMNICLAW_SERVER_URL="$server_url" \
    OMNICLAW_TOKEN="$token" \
    OMNICLAW_OWNER_TOKEN="$owner_token" \
    CIRCLE_API_KEY="$circle_key" \
    ENTITY_SECRET="$entity_secret" \
    OMNICLAW_PRIVATE_KEY="$private_key" \
    OMNICLAW_NETWORK="$NETWORK" \
    OMNICLAW_RPC_URL="$RPC_URL" \
    PYTHONHASHSEED=0 \
    omniclaw-cli "$@"
  ) | tee -a "$log_file"
}

cli_json() {
  local side="$1"
  shift
  local rc output attempt log_file

  if [[ "$side" == "buyer" ]]; then
    log_file="$BUYER_CLI_LOG"
  else
    log_file="$SELLER_CLI_LOG"
  fi

  for ((attempt = 1; attempt <= CLI_RETRY_ATTEMPTS; attempt++)); do
    set +e
    output="$(cli_json_once "$side" "$@" 2>&1)"
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
      printf '%s\n' "$output"
      return 0
    fi

    {
      echo
      echo ">>> [$side] retry $attempt/$CLI_RETRY_ATTEMPTS exited with code $rc"
    } >>"$log_file"

    if (( attempt < CLI_RETRY_ATTEMPTS )); then
      sleep "$attempt"
    fi
  done

  if [[ $rc -ne 0 ]]; then
    printf '%s\n' "$output" >&2
    return "$rc"
  fi
}

api_json() {
  local side="$1"
  local method="$2"
  local path="$3"
  local query="${4:-}"
  local body="${5:-}"
  local url token owner_header

  if [[ "$side" == "buyer" ]]; then
    url="http://127.0.0.1:$BUYER_CP_PORT$path"
    token="$BUYER_TOKEN"
  else
    url="http://127.0.0.1:$SELLER_CP_PORT$path"
    token="$SELLER_TOKEN"
  fi

  if [[ -n "$query" ]]; then
    url="$url?$query"
  fi

  owner_header=()
  if [[ "$method" == "OWNERPOST" ]]; then
    method="POST"
    owner_header=(-H "X-Omniclaw-Owner-Token: $OWNER_TOKEN")
  fi

  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" \
      -H "Authorization: Bearer $token" \
      "${owner_header[@]}" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "$url"
  else
    curl -fsS -X "$method" \
      -H "Authorization: Bearer $token" \
      "${owner_header[@]}" \
      "$url"
  fi
}

atomic_to_usdc() {
  awk -v a="$1" 'BEGIN {printf "%.6f", a / 1000000}'
}

atomic_delta_to_usdc_signed() {
  awk -v after="$1" -v before="$2" 'BEGIN {d=(after-before)/1000000; if (d > 0) printf "+%.6f", d; else printf "%.6f", d}'
}

short_addr() {
  local v="$1"
  if [[ ${#v} -le 12 ]]; then
    printf "%s" "$v"
  else
    printf "%s...%s" "${v:0:6}" "${v: -4}"
  fi
}

decode_payment_required() {
  local url="$1"
  local headers_file="$LOG_DIR/payment-required.headers"
  local body_file="$LOG_DIR/payment-required.body"
  curl -sS -D "$headers_file" -o "$body_file" "$url" >/dev/null
  awk 'BEGIN{IGNORECASE=1} /^payment-required:/{sub(/^[^:]*:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit}' "$headers_file"
}

for port in "$BUYER_CP_PORT" "$SELLER_CP_PORT" "$SELLER_GATE_PORT"; do
  if [[ "$(port_in_use "$port")" == "in-use" ]]; then
    echo "Port $port is already in use. Free it or override the port flags." >&2
    exit 1
  fi
done

banner "OmniClaw Autonomous Economy Demo"
kv "Flow" "policy block -> paid API -> approval -> gasless settlement"
kv "Network" "$NETWORK"
kv "Buyer Control" "http://localhost:$BUYER_CP_PORT"
kv "Seller Control" "http://localhost:$SELLER_CP_PORT"
kv "Paid Endpoint" "http://localhost:$SELLER_GATE_PORT$ENDPOINT"
kv "Log Bundle" "$LOG_DIR"

section "1. Bring up buyer and seller agents"
start_bg "$BUYER_CP_LOG" env \
  CIRCLE_API_KEY="$BUYER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$BUYER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$BUYER_PRIVATE_KEY" \
  OMNICLAW_AGENT_POLICY_PATH="$BUYER_POLICY_RUNTIME" \
  OMNICLAW_AGENT_TOKEN="$BUYER_TOKEN" \
  OMNICLAW_OWNER_TOKEN="$OWNER_TOKEN" \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_STORAGE_BACKEND=memory \
  OMNICLAW_POLICY_RELOAD_INTERVAL=0 \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  PYTHONUNBUFFERED=1 \
  uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port "$BUYER_CP_PORT" --log-level warning

start_bg "$SELLER_CP_LOG" env \
  CIRCLE_API_KEY="$SELLER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$SELLER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$SELLER_PRIVATE_KEY" \
  OMNICLAW_AGENT_POLICY_PATH="$SELLER_POLICY_RUNTIME" \
  OMNICLAW_AGENT_TOKEN="$SELLER_TOKEN" \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_STORAGE_BACKEND=memory \
  OMNICLAW_POLICY_RELOAD_INTERVAL=0 \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  PYTHONUNBUFFERED=1 \
  uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port "$SELLER_CP_PORT" --log-level warning

wait_for_http_ok "http://127.0.0.1:$BUYER_CP_PORT/api/v1/health" || { tail -n 80 "$BUYER_CP_LOG" >&2; exit 1; }
wait_for_http_ok "http://127.0.0.1:$SELLER_CP_PORT/api/v1/health" || { tail -n 80 "$SELLER_CP_LOG" >&2; exit 1; }
printf 'Buyer and seller control planes are live.\n'

show_cmd "omniclaw-cli configure --server-url http://localhost:$BUYER_CP_PORT --token $BUYER_TOKEN --wallet $BUYER_ALIAS --owner-token <hidden>"
cli_json buyer configure \
  --server-url "http://localhost:$BUYER_CP_PORT" \
  --token "$BUYER_TOKEN" \
  --wallet "$BUYER_ALIAS" \
  --owner-token "$OWNER_TOKEN" \
  >/dev/null
kv "Buyer Agent" "$BUYER_ALIAS connected"

show_cmd "omniclaw-cli configure --server-url http://localhost:$SELLER_CP_PORT --token $SELLER_TOKEN --wallet $SELLER_ALIAS"
cli_json seller configure \
  --server-url "http://localhost:$SELLER_CP_PORT" \
  --token "$SELLER_TOKEN" \
  --wallet "$SELLER_ALIAS" \
  >/dev/null
kv "Seller Agent" "$SELLER_ALIAS connected"

section "2. Guard rails block the wrong counterparty"
show_cmd "omniclaw-cli status"
BUYER_STATUS="$(cli_json buyer status)"
BUYER_WALLET="$(printf '%s' "$BUYER_STATUS" | jq -r '.Wallet')"
BUYER_BALANCE_LINE="$(printf '%s' "$BUYER_STATUS" | jq -r '.Balance')"
kv "Buyer Wallet" "$(short_addr "$BUYER_WALLET")"
kv "Buyer Balance" "$BUYER_BALANCE_LINE"

show_cmd "omniclaw-cli can-pay --recipient $BLOCKED_URL"
BLOCKED_RESULT="$(cli_json buyer can-pay --recipient "$BLOCKED_URL")"
if [[ "$(printf '%s' "$BLOCKED_RESULT" | jq -r '.can_pay')" == "true" ]]; then
  echo "Blocked URL unexpectedly allowed." >&2
  exit 1
fi
kv "Blocked URL" "$BLOCKED_URL"
kv "Policy Result" "blocked before any spend"
kv "Reason" "$(printf '%s' "$BLOCKED_RESULT" | jq -r '.reason')"

show_cmd "omniclaw-cli can-pay --recipient $ALLOWED_URL"
ALLOWED_RESULT="$(cli_json buyer can-pay --recipient "$ALLOWED_URL")"
if [[ "$(printf '%s' "$ALLOWED_RESULT" | jq -r '.can_pay')" != "true" ]]; then
  echo "Allowed URL was not permitted by policy." >&2
  exit 1
fi
kv "Allowed URL" "$ALLOWED_URL"
kv "Policy Result" "allowed by whitelist"

section "3. Seller opens a paid API"
start_bg "$SELLER_GATE_LOG" env \
  CIRCLE_API_KEY="$SELLER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$SELLER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$SELLER_PRIVATE_KEY" \
  OMNICLAW_SERVER_URL="http://127.0.0.1:$SELLER_CP_PORT" \
  OMNICLAW_TOKEN="$SELLER_TOKEN" \
  OMNICLAW_CONFIG_DIR="$SELLER_CONFIG_DIR" \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  PYTHONHASHSEED=0 \
  PYTHONUNBUFFERED=1 \
  uv run python -m omniclaw.cli_agent serve \
    --price "$PRICE" \
    --endpoint "$ENDPOINT" \
    --exec "$SELLER_EXEC_CMD" \
    --port "$SELLER_GATE_PORT"

wait_for_http_status "http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT" "402" || { tail -n 120 "$SELLER_GATE_LOG" >&2; exit 1; }
SELLER_402_HEADER="$(decode_payment_required "http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT")"
printf '%s' "$SELLER_402_HEADER" | base64 -d >"$LOG_DIR/payment-required.json"

REQ_SCHEME="$(jq -r '.accepts[0].extra.name' "$LOG_DIR/payment-required.json")"
REQ_NETWORK="$(jq -r '.accepts[0].network' "$LOG_DIR/payment-required.json")"
REQ_PAY_TO="$(jq -r '.accepts[0].payTo' "$LOG_DIR/payment-required.json")"
REQ_ATOMIC="$(jq -r '.accepts[0].amount' "$LOG_DIR/payment-required.json")"
REQ_USD="$(awk -v atomic="$REQ_ATOMIC" 'BEGIN {printf "%.2f", atomic / 1000000}')"
REQ_CONTRACT="$(jq -r '.accepts[0].extra.verifyingContract' "$LOG_DIR/payment-required.json")"

SELLER_BEFORE_DETAIL="$(api_json seller GET /api/v1/balance-detail)"
BUYER_BEFORE_DETAIL="$(api_json buyer GET /api/v1/balance-detail)"
SELLER_BEFORE_GATEWAY="$(printf '%s' "$SELLER_BEFORE_DETAIL" | jq -r '.gateway_balance')"
BUYER_BEFORE_GATEWAY="$(printf '%s' "$BUYER_BEFORE_DETAIL" | jq -r '.gateway_balance')"
SELLER_BEFORE_GATEWAY_ATOMIC="$(printf '%s' "$SELLER_BEFORE_DETAIL" | jq -r '.gateway_balance_atomic')"
BUYER_BEFORE_GATEWAY_ATOMIC="$(printf '%s' "$BUYER_BEFORE_DETAIL" | jq -r '.gateway_balance_atomic')"
SELLER_EOA="$(printf '%s' "$SELLER_BEFORE_DETAIL" | jq -r '.eoa_address')"
SELLER_CIRCLE="$(printf '%s' "$SELLER_BEFORE_DETAIL" | jq -r '.circle_wallet_address')"
BUYER_EOA="$(printf '%s' "$BUYER_BEFORE_DETAIL" | jq -r '.eoa_address')"
BUYER_CIRCLE="$(printf '%s' "$BUYER_BEFORE_DETAIL" | jq -r '.circle_wallet_address')"

kv "Paid URL" "http://localhost:$SELLER_GATE_PORT$ENDPOINT"
kv "Seller Model" "Circle Gateway gasless x402, batch-settled by GatewayMiddleware"
kv "HTTP Probe" "402 Payment Required"
kv "Scheme" "$REQ_SCHEME"
kv "Network" "$REQ_NETWORK"
kv "Seller Address" "$(short_addr "$REQ_PAY_TO")"
kv "Price" "$REQ_USD USDC"
kv "Verifying Contract" "$(short_addr "$REQ_CONTRACT")"
kv "Buyer EOA" "$(short_addr "$BUYER_EOA")"
kv "Buyer Circle" "$(short_addr "$BUYER_CIRCLE")"
kv "Seller EOA" "$(short_addr "$SELLER_EOA")"
kv "Seller Circle" "$(short_addr "$SELLER_CIRCLE")"

section "4. Buyer reviews budget and asks for approval"
show_cmd "POST /api/v1/simulate recipient=http://localhost:$SELLER_GATE_PORT$ENDPOINT amount=$PRICE"
SIMULATE_RESULT="$(api_json buyer POST /api/v1/simulate "" "$(jq -nc --arg recipient "http://localhost:$SELLER_GATE_PORT$ENDPOINT" --arg amount "$PRICE" '{recipient: $recipient, amount: $amount}')")"
SIMULATE_WOULD_SUCCEED="$(printf '%s' "$SIMULATE_RESULT" | jq -r '.would_succeed')"
SIMULATE_ROUTE="$(printf '%s' "$SIMULATE_RESULT" | jq -r '.route')"
SIMULATE_REASON="$(printf '%s' "$SIMULATE_RESULT" | jq -r '.reason // empty')"
kv "Buyer Gateway" "$(atomic_to_usdc "$BUYER_BEFORE_GATEWAY_ATOMIC") USDC in Gateway before payment"
kv "Seller Gateway" "$(atomic_to_usdc "$SELLER_BEFORE_GATEWAY_ATOMIC") USDC in Gateway before payment"
kv "Route" "$SIMULATE_ROUTE"
if [[ "$SIMULATE_WOULD_SUCCEED" == "true" ]]; then
  kv "Budget Check" "ready to execute immediately"
elif [[ "$SIMULATE_REASON" == *"requires confirmation"* ]]; then
  kv "Budget Check" "within policy, but owner approval required"
elif [[ "$SIMULATE_REASON" == *"Insufficient available balance"* ]]; then
  kv "Budget Check" "insufficient Gateway balance on $NETWORK"
  if [[ "$NETWORK" == "BASE-SEPOLIA" ]]; then
    kv "Funding Hint" "fund Base Sepolia via the Circle faucet, then rerun with --base"
  fi
  exit 1
else
  echo "Simulation failed. Buyer is not ready to pay." >&2
  exit 1
fi

PAY_IDEMPOTENCY_KEY="foundation-demo-$RUN_TS"
show_cmd "omniclaw-cli pay --recipient http://localhost:$SELLER_GATE_PORT$ENDPOINT --idempotency-key $PAY_IDEMPOTENCY_KEY"
PAY_ATTEMPT_ONE="$(cli_json buyer pay --recipient "http://localhost:$SELLER_GATE_PORT$ENDPOINT" --idempotency-key "$PAY_IDEMPOTENCY_KEY")"
CONFIRM_REQUIRED="$(printf '%s' "$PAY_ATTEMPT_ONE" | jq -r '.requires_confirmation')"
CONFIRMATION_ID="$(printf '%s' "$PAY_ATTEMPT_ONE" | jq -r '.confirmation_id // empty')"

if [[ "$CONFIRM_REQUIRED" != "true" || -z "$CONFIRMATION_ID" ]]; then
  echo "Expected an approval step, but the payment did not require confirmation." >&2
  exit 1
fi

kv "Approval" "required before spend"
kv "Confirmation ID" "$CONFIRMATION_ID"

show_cmd "omniclaw-cli confirmations approve --id $CONFIRMATION_ID"
APPROVAL_RESULT="$(cli_json buyer confirmations approve --id "$CONFIRMATION_ID")"
if [[ "$(printf '%s' "$APPROVAL_RESULT" | jq -r '.status')" != "APPROVED" ]]; then
  echo "Confirmation approval failed." >&2
  exit 1
fi
kv "Owner Decision" "approved"

section "5. Buyer pays and the seller unlocks the API"
show_cmd "omniclaw-cli pay --recipient http://localhost:$SELLER_GATE_PORT$ENDPOINT --idempotency-key $PAY_IDEMPOTENCY_KEY"
PAY_ATTEMPT_TWO="$(cli_json buyer pay --recipient "http://localhost:$SELLER_GATE_PORT$ENDPOINT" --idempotency-key "$PAY_IDEMPOTENCY_KEY")"
if [[ "$(printf '%s' "$PAY_ATTEMPT_TWO" | jq -r '.success')" != "true" ]]; then
  printf '%s\n' "$PAY_ATTEMPT_TWO" >&2
  exit 1
fi

BUYER_AFTER_DETAIL="$(api_json buyer GET /api/v1/balance-detail)"
SELLER_AFTER_DETAIL="$(api_json seller GET /api/v1/balance-detail)"
BUYER_AFTER_GATEWAY="$(printf '%s' "$BUYER_AFTER_DETAIL" | jq -r '.gateway_balance')"
SELLER_AFTER_GATEWAY="$(printf '%s' "$SELLER_AFTER_DETAIL" | jq -r '.gateway_balance')"
BUYER_AFTER_GATEWAY_ATOMIC="$(printf '%s' "$BUYER_AFTER_DETAIL" | jq -r '.gateway_balance_atomic')"
SELLER_AFTER_GATEWAY_ATOMIC="$(printf '%s' "$SELLER_AFTER_DETAIL" | jq -r '.gateway_balance_atomic')"
WAITED_FOR_SETTLEMENT=0
for ((attempt = 1; attempt <= 90; attempt++)); do
  if [[ "$BUYER_AFTER_GATEWAY_ATOMIC" != "$BUYER_BEFORE_GATEWAY_ATOMIC" || "$SELLER_AFTER_GATEWAY_ATOMIC" != "$SELLER_BEFORE_GATEWAY_ATOMIC" ]]; then
    break
  fi
  if [[ "$WAITED_FOR_SETTLEMENT" -eq 0 ]]; then
    kv "Settlement Sync" "waiting for Gateway contract balances to update"
    WAITED_FOR_SETTLEMENT=1
  fi
  sleep 1
  BUYER_AFTER_DETAIL="$(api_json buyer GET /api/v1/balance-detail)"
  SELLER_AFTER_DETAIL="$(api_json seller GET /api/v1/balance-detail)"
  BUYER_AFTER_GATEWAY="$(printf '%s' "$BUYER_AFTER_DETAIL" | jq -r '.gateway_balance')"
  SELLER_AFTER_GATEWAY="$(printf '%s' "$SELLER_AFTER_DETAIL" | jq -r '.gateway_balance')"
  BUYER_AFTER_GATEWAY_ATOMIC="$(printf '%s' "$BUYER_AFTER_DETAIL" | jq -r '.gateway_balance_atomic')"
  SELLER_AFTER_GATEWAY_ATOMIC="$(printf '%s' "$SELLER_AFTER_DETAIL" | jq -r '.gateway_balance_atomic')"
done

UNLOCKED_PRETTY="$(printf '%s' "$PAY_ATTEMPT_TWO" | jq -c '.response_data // "seller response unavailable"' )"

kv "Settlement Status" "$(printf '%s' "$PAY_ATTEMPT_TWO" | jq -r '.status')"
kv "Payment Method" "$(printf '%s' "$PAY_ATTEMPT_TWO" | jq -r '.method')"
kv "Gateway Ref" "$(printf '%s' "$PAY_ATTEMPT_TWO" | jq -r '.transaction_id')"
kv "Unlocked Payload" "$UNLOCKED_PRETTY"

section "6. Gateway contract balances before and after"
if [[ "$BUYER_AFTER_GATEWAY_ATOMIC" != "$BUYER_BEFORE_GATEWAY_ATOMIC" || "$SELLER_AFTER_GATEWAY_ATOMIC" != "$SELLER_BEFORE_GATEWAY_ATOMIC" ]]; then
  kv "Settlement Mirror" "Gateway contract balances updated"
else
  kv "Settlement Mirror" "Gateway contract balances did not update within 90 seconds"
fi
kv "Buyer Gateway Before" "$(atomic_to_usdc "$BUYER_BEFORE_GATEWAY_ATOMIC") USDC"
kv "Buyer Gateway After" "$(atomic_to_usdc "$BUYER_AFTER_GATEWAY_ATOMIC") USDC"
kv "Buyer Delta" "$(atomic_delta_to_usdc_signed "$BUYER_AFTER_GATEWAY_ATOMIC" "$BUYER_BEFORE_GATEWAY_ATOMIC") USDC"
kv "Seller Gateway Before" "$(atomic_to_usdc "$SELLER_BEFORE_GATEWAY_ATOMIC") USDC"
kv "Seller Gateway After" "$(atomic_to_usdc "$SELLER_AFTER_GATEWAY_ATOMIC") USDC"
kv "Seller Delta" "$(atomic_delta_to_usdc_signed "$SELLER_AFTER_GATEWAY_ATOMIC" "$SELLER_BEFORE_GATEWAY_ATOMIC") USDC"

section "Evidence"
kv "Log Bundle" "$LOG_DIR"
kv "Buyer Control Log" "$BUYER_CP_LOG"
kv "Seller Control Log" "$SELLER_CP_LOG"
kv "Seller Gate Log" "$SELLER_GATE_LOG"
kv "Payment Terms" "$LOG_DIR/payment-required.json"

if [[ "$HOLD" -eq 1 ]]; then
  printf '\nDemo complete. Processes are still running. Press Ctrl-C to stop.\n'
  while true; do
    sleep 1
  done
fi
