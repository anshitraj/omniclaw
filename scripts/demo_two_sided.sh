#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR_DEFAULT="$ROOT_DIR/logs/demo_$RUN_TS"

ENV_FILE="$ROOT_DIR/.env"
NETWORK="ETH-SEPOLIA"
RPC_URL="${OMNICLAW_RPC_URL:-}"
PRICE="0.01"
ENDPOINT="/api/data"
SELLER_EXEC_CMD='echo "{\"result\":\"premium data from seller\"}"'
SELLER_CP_PORT=8081
BUYER_CP_PORT=8082
SELLER_GATE_PORT=9001
LOG_DIR="$LOG_DIR_DEFAULT"
RUN_PAYMENT=0
AUTO_DEPOSIT_AMOUNT=""
CHECK_ONLY=0
HOLD=0

PIDS=()
PID_NAMES=()

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
section() { color "1;36" "== $1 =="; }
info() { color "0;37" "[info] $1"; }
ok() { color "0;32" "[ok] $1"; }
warn() { color "1;33" "[warn] $1"; }
err() { color "0;31" "[err] $1"; }

usage() {
  cat <<'EOF'
Usage: scripts/demo_two_sided.sh [options]

Options:
  --env-file <path>          Path to env file (default: .env)
  --network <name>           ETH-SEPOLIA or BASE-SEPOLIA (default: ETH-SEPOLIA)
  --rpc-url <url>            Override RPC URL
  --price <usd>              Seller endpoint price in USDC (default: 0.01)
  --endpoint <path>          Seller gated path (default: /api/data)
  --seller-exec <command>    Command seller runs after payment
  --seller-cp-port <port>    Seller control plane port (default: 8081)
  --buyer-cp-port <port>     Buyer control plane port (default: 8082)
  --seller-gate-port <port>  Seller x402 gate port (default: 9001)
  --log-dir <path>           Log directory (default: logs/demo_<timestamp>)
  --auto-deposit <amount>    Buyer auto deposit amount before payment
  --run-payment              Execute buyer pay step
  --hold                     Keep processes alive after setup until Ctrl-C
  --check-only               Validate config and exit
  -h, --help                 Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --network) NETWORK="$2"; shift 2 ;;
    --rpc-url) RPC_URL="$2"; shift 2 ;;
    --price) PRICE="$2"; shift 2 ;;
    --endpoint) ENDPOINT="$2"; shift 2 ;;
    --seller-exec) SELLER_EXEC_CMD="$2"; shift 2 ;;
    --seller-cp-port) SELLER_CP_PORT="$2"; shift 2 ;;
    --buyer-cp-port) BUYER_CP_PORT="$2"; shift 2 ;;
    --seller-gate-port) SELLER_GATE_PORT="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --auto-deposit) AUTO_DEPOSIT_AMOUNT="$2"; shift 2 ;;
    --run-payment) RUN_PAYMENT=1; shift ;;
    --hold) HOLD=1; shift ;;
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown option: $1"; usage; exit 1 ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  err "Env file not found: $ENV_FILE"
  exit 1
fi

if [[ "$NETWORK" != "ETH-SEPOLIA" && "$NETWORK" != "BASE-SEPOLIA" ]]; then
  err "Unsupported network: $NETWORK (use ETH-SEPOLIA or BASE-SEPOLIA)"
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
    err "Missing required command: $1"
    exit 1
  fi
}

require_cmd uv
require_cmd curl
require_cmd python3

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

SELLER_CIRCLE_API_KEY="$(pick_env SELLER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
BUYER_CIRCLE_API_KEY="$(pick_env BUYER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
SELLER_ENTITY_SECRET="$(pick_env SELLER_ENTITY_SECRET ENTITY_SECRET || true)"
BUYER_ENTITY_SECRET="$(pick_env BUYER_ENTITY_SECRET ENTITY_SECRET || true)"
SELLER_PRIVATE_KEY="$(pick_env SELLER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"
BUYER_PRIVATE_KEY="$(pick_env BUYER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"

SELLER_POLICY="$ROOT_DIR/examples/agent/seller/policy.json"
BUYER_POLICY="$ROOT_DIR/examples/agent/buyer/policy.json"
SELLER_POLICY_RUNTIME=""
BUYER_POLICY_RUNTIME=""
SELLER_TOKEN="seller-agent-token"
BUYER_TOKEN="buyer-agent-token"
OMNICLAW_STORAGE_BACKEND="${OMNICLAW_STORAGE_BACKEND:-memory}"
OMNICLAW_LOG_LEVEL="${OMNICLAW_LOG_LEVEL:-INFO}"

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    err "Missing required value: $name"
    exit 1
  fi
}

require_value "SELLER_CIRCLE_API_KEY or CIRCLE_API_KEY" "$SELLER_CIRCLE_API_KEY"
require_value "BUYER_CIRCLE_API_KEY or CIRCLE_API_KEY" "$BUYER_CIRCLE_API_KEY"
require_value "SELLER_ENTITY_SECRET or ENTITY_SECRET" "$SELLER_ENTITY_SECRET"
require_value "BUYER_ENTITY_SECRET or ENTITY_SECRET" "$BUYER_ENTITY_SECRET"
require_value "SELLER_OMNICLAW_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY" "$SELLER_PRIVATE_KEY"
require_value "BUYER_OMNICLAW_PRIVATE_KEY or OMNICLAW_PRIVATE_KEY" "$BUYER_PRIVATE_KEY"

if [[ ! -f "$SELLER_POLICY" ]]; then
  err "Seller policy file not found: $SELLER_POLICY"
  exit 1
fi
if [[ ! -f "$BUYER_POLICY" ]]; then
  err "Buyer policy file not found: $BUYER_POLICY"
  exit 1
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  section "Preflight OK"
  info "env-file: $ENV_FILE"
  info "network: $NETWORK"
  info "rpc-url: $RPC_URL"
  info "seller policy: $SELLER_POLICY"
  info "buyer policy: $BUYER_POLICY"
  info "buyer/seller creds: found"
  exit 0
fi

mkdir -p "$LOG_DIR"
SELLER_CP_LOG="$LOG_DIR/seller-control-plane.log"
BUYER_CP_LOG="$LOG_DIR/buyer-control-plane.log"
SELLER_GATE_LOG="$LOG_DIR/seller-gateway.log"
BUYER_CLI_LOG="$LOG_DIR/buyer-cli.log"
SELLER_CLI_LOG="$LOG_DIR/seller-cli.log"
SELLER_POLICY_RUNTIME="$LOG_DIR/seller-policy.runtime.json"
BUYER_POLICY_RUNTIME="$LOG_DIR/buyer-policy.runtime.json"
cp "$SELLER_POLICY" "$SELLER_POLICY_RUNTIME"
cp "$BUYER_POLICY" "$BUYER_POLICY_RUNTIME"

cleanup() {
  local code=$?
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    section "Cleanup"
    for idx in "${!PIDS[@]}"; do
      local pid="${PIDS[$idx]}"
      local name="${PID_NAMES[$idx]}"
      if kill -0 "$pid" >/dev/null 2>&1; then
        info "Stopping $name (pid $pid)"
        kill "$pid" >/dev/null 2>&1 || true
      fi
    done
    for pid in "${PIDS[@]}"; do
      wait "$pid" 2>/dev/null || true
    done
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

start_bg() {
  local name="$1"
  local logfile="$2"
  shift 2
  ("$@") >"$logfile" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  PID_NAMES+=("$name")
  sleep 0.4
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    err "$name exited immediately. Tail of $logfile:"
    tail -n 80 "$logfile" || true
    exit 1
  fi
  ok "Started $name (pid $pid)"
  info "log: $logfile"
}

wait_for_http_ok() {
  local name="$1"
  local url="$2"
  local timeout_secs="${3:-90}"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      ok "$name is ready"
      return 0
    fi
    if (( "$(date +%s)" - start_ts >= timeout_secs )); then
      err "$name did not become ready in ${timeout_secs}s"
      return 1
    fi
    sleep 1
  done
}

wait_for_http_status() {
  local name="$1"
  local url="$2"
  local expected_status="$3"
  local timeout_secs="${4:-90}"
  local start_ts http_code
  start_ts="$(date +%s)"
  while true; do
    http_code="$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)"
    if [[ "$http_code" == "$expected_status" ]]; then
      ok "$name returned expected HTTP $expected_status"
      return 0
    fi
    if (( "$(date +%s)" - start_ts >= timeout_secs )); then
      err "$name did not return HTTP $expected_status in ${timeout_secs}s (last: $http_code)"
      return 1
    fi
    sleep 1
  done
}

run_cli() {
  local side="$1"
  shift
  local server_url token config_dir log_file circle_key entity_secret private_key pyhashseed
  if [[ "$side" == "seller" ]]; then
    server_url="http://127.0.0.1:$SELLER_CP_PORT"
    token="$SELLER_TOKEN"
    config_dir="$LOG_DIR/seller-cli-config"
    log_file="$SELLER_CLI_LOG"
    circle_key="$SELLER_CIRCLE_API_KEY"
    entity_secret="$SELLER_ENTITY_SECRET"
    private_key="$SELLER_PRIVATE_KEY"
  else
    server_url="http://127.0.0.1:$BUYER_CP_PORT"
    token="$BUYER_TOKEN"
    config_dir="$LOG_DIR/buyer-cli-config"
    log_file="$BUYER_CLI_LOG"
    circle_key="$BUYER_CIRCLE_API_KEY"
    entity_secret="$BUYER_ENTITY_SECRET"
    private_key="$BUYER_PRIVATE_KEY"
  fi
  pyhashseed="${OMNICLAW_DEMO_PYTHONHASHSEED:-}"

  mkdir -p "$config_dir"
  {
    echo
    echo ">>> [$side] omniclaw-cli $*"
  } >>"$log_file"

  (
    cd "$ROOT_DIR"
    OMNICLAW_SERVER_URL="$server_url" \
    OMNICLAW_TOKEN="$token" \
    OMNICLAW_CONFIG_DIR="$config_dir" \
    OMNICLAW_CLI_HUMAN=1 \
    OMNICLAW_CLI_NO_BANNER=1 \
    CIRCLE_API_KEY="$circle_key" \
    ENTITY_SECRET="$entity_secret" \
    OMNICLAW_PRIVATE_KEY="$private_key" \
    OMNICLAW_NETWORK="$NETWORK" \
    OMNICLAW_RPC_URL="$RPC_URL" \
    PYTHONHASHSEED="$pyhashseed" \
    uv run python -m omniclaw.cli_agent "$@"
  ) 2>&1 | tee -a "$log_file"
}

run_cli_try() {
  local side="$1"
  shift
  local rc log_file
  set +e
  run_cli "$side" "$@"
  rc=$?
  set -e
  if [[ "$side" == "seller" ]]; then
    log_file="$SELLER_CLI_LOG"
  else
    log_file="$BUYER_CLI_LOG"
  fi
  if [[ $rc -eq 139 ]] || ([[ $rc -ne 0 ]] && tail -n 160 "$log_file" | rg -q "OverflowError: Python int too large to convert to C int"); then
    warn "Detected transient CLI/runtime failure. Retrying once with PYTHONHASHSEED=0."
    set +e
    OMNICLAW_DEMO_PYTHONHASHSEED=0 run_cli "$side" "$@"
    rc=$?
    set -e
  fi
  if [[ $rc -ne 0 ]]; then
    warn "Command failed (side=$side): omniclaw-cli $* (exit $rc)"
  fi
  return $rc
}

run_api() {
  local side="$1"
  local method="$2"
  local path="$3"
  local query="${4:-}"
  local json_body="${5:-}"
  local server_url token log_file url tmp status

  if [[ "$side" == "seller" ]]; then
    server_url="http://127.0.0.1:$SELLER_CP_PORT"
    token="$SELLER_TOKEN"
    log_file="$SELLER_CLI_LOG"
  else
    server_url="http://127.0.0.1:$BUYER_CP_PORT"
    token="$BUYER_TOKEN"
    log_file="$BUYER_CLI_LOG"
  fi

  url="$server_url$path"
  if [[ -n "$query" ]]; then
    url="$url?$query"
  fi

  {
    echo
    echo ">>> [$side-api] $method $url"
  } >>"$log_file"

  tmp="$(mktemp)"
  if [[ -n "$json_body" ]]; then
    status="$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "$json_body" \
      "$url")"
  else
    status="$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $token" \
      "$url")"
  fi

  cat "$tmp" | python3 -m json.tool 2>/dev/null | tee -a "$log_file" || cat "$tmp" | tee -a "$log_file"
  rm -f "$tmp"

  if [[ "$status" -ge 400 ]]; then
    warn "API call failed (side=$side, status=$status): $method $path"
    return 1
  fi
  return 0
}

section "Config"
info "network: $NETWORK"
info "rpc-url: $RPC_URL"
info "seller control plane: http://127.0.0.1:$SELLER_CP_PORT"
info "buyer control plane:  http://127.0.0.1:$BUYER_CP_PORT"
info "seller paid URL:      http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT"
info "logs:                 $LOG_DIR"
info "seller policy copy:   $SELLER_POLICY_RUNTIME"
info "buyer policy copy:    $BUYER_POLICY_RUNTIME"

for port in "$SELLER_CP_PORT" "$BUYER_CP_PORT" "$SELLER_GATE_PORT"; do
  state="$(port_in_use "$port")"
  if [[ "$state" == "in-use" ]]; then
    err "Port $port is already in use. Free it or override with --seller-cp-port/--buyer-cp-port/--seller-gate-port."
    exit 1
  fi
done

section "Start Control Planes"
start_bg "seller-control-plane" "$SELLER_CP_LOG" env \
  CIRCLE_API_KEY="$SELLER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$SELLER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$SELLER_PRIVATE_KEY" \
  OMNICLAW_AGENT_POLICY_PATH="$SELLER_POLICY_RUNTIME" \
  OMNICLAW_AGENT_TOKEN="$SELLER_TOKEN" \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_STORAGE_BACKEND="$OMNICLAW_STORAGE_BACKEND" \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  PYTHONUNBUFFERED=1 \
  uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port "$SELLER_CP_PORT" --log-level info

start_bg "buyer-control-plane" "$BUYER_CP_LOG" env \
  CIRCLE_API_KEY="$BUYER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$BUYER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$BUYER_PRIVATE_KEY" \
  OMNICLAW_AGENT_POLICY_PATH="$BUYER_POLICY_RUNTIME" \
  OMNICLAW_AGENT_TOKEN="$BUYER_TOKEN" \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_STORAGE_BACKEND="$OMNICLAW_STORAGE_BACKEND" \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  PYTHONUNBUFFERED=1 \
  uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port "$BUYER_CP_PORT" --log-level info

wait_for_http_ok "seller-control-plane" "http://127.0.0.1:$SELLER_CP_PORT/api/v1/health" || {
  tail -n 80 "$SELLER_CP_LOG" || true
  exit 1
}
wait_for_http_ok "buyer-control-plane" "http://127.0.0.1:$BUYER_CP_PORT/api/v1/health" || {
  tail -n 80 "$BUYER_CP_LOG" || true
  exit 1
}

section "Start Seller x402 Gate"
start_bg "seller-gateway" "$SELLER_GATE_LOG" env \
  CIRCLE_API_KEY="$SELLER_CIRCLE_API_KEY" \
  ENTITY_SECRET="$SELLER_ENTITY_SECRET" \
  OMNICLAW_PRIVATE_KEY="$SELLER_PRIVATE_KEY" \
  OMNICLAW_SERVER_URL="http://127.0.0.1:$SELLER_CP_PORT" \
  OMNICLAW_TOKEN="$SELLER_TOKEN" \
  OMNICLAW_CLI_HUMAN=1 \
  OMNICLAW_CLI_NO_BANNER=1 \
  OMNICLAW_NETWORK="$NETWORK" \
  OMNICLAW_RPC_URL="$RPC_URL" \
  OMNICLAW_LOG_LEVEL="$OMNICLAW_LOG_LEVEL" \
  OMNICLAW_CONFIG_DIR="$LOG_DIR/seller-gate-config" \
  PYTHONUNBUFFERED=1 \
  uv run python -m omniclaw.cli_agent serve --price "$PRICE" --endpoint "$ENDPOINT" --exec "$SELLER_EXEC_CMD" --port "$SELLER_GATE_PORT"

wait_for_http_status \
  "seller-gateway (payment required check)" \
  "http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT" \
  "402" || {
  tail -n 120 "$SELLER_GATE_LOG" || true
  exit 1
}

section "Demo Snapshot"
run_api seller GET "/api/v1/health" || true
run_api seller GET "/api/v1/balance" || true
run_api seller GET "/api/v1/address" || true
run_api buyer GET "/api/v1/health" || true
run_api buyer GET "/api/v1/balance" || true
run_api buyer GET "/api/v1/address" || true
run_api buyer GET "/api/v1/can-pay" "recipient=http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT" || true

if [[ -n "$AUTO_DEPOSIT_AMOUNT" ]]; then
  section "Buyer Deposit"
  run_api buyer POST "/api/v1/deposit" "amount=$AUTO_DEPOSIT_AMOUNT" || true
fi

if [[ "$RUN_PAYMENT" -eq 1 ]]; then
  section "Buyer Pays Seller"
  IDEMPOTENCY_KEY="demo-${NETWORK,,}-${RUN_TS}"
  PAYLOAD="{\"url\":\"http://127.0.0.1:$SELLER_GATE_PORT$ENDPOINT\",\"method\":\"GET\",\"idempotency_key\":\"$IDEMPOTENCY_KEY\"}"
  run_api buyer POST "/api/v1/x402/pay" "" "$PAYLOAD" || true

  section "Ledger Snapshot"
  run_api buyer GET "/api/v1/transactions" "limit=20" || true
  run_api seller GET "/api/v1/transactions" "limit=20" || true
fi

section "Done"
ok "Two-sided OmniClaw demo environment is up."
info "Seller logs: $SELLER_GATE_LOG"
info "Buyer logs:  $BUYER_CP_LOG and $BUYER_CLI_LOG"
info "To tail all logs:"
printf '  tail -f %q %q %q %q %q\n' "$SELLER_CP_LOG" "$BUYER_CP_LOG" "$SELLER_GATE_LOG" "$BUYER_CLI_LOG" "$SELLER_CLI_LOG"

if [[ "$HOLD" -eq 1 ]]; then
  warn "Hold mode enabled. Press Ctrl-C to stop."
  while true; do
    sleep 1
  done
fi
