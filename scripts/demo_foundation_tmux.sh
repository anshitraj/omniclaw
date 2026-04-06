#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_TS="$(date +%Y%m%d_%H%M%S)"

SESSION_NAME="omniclaw-demo-$RUN_TS"
ENV_FILE="$ROOT_DIR/.env"
NETWORK="ETH-SEPOLIA"
RPC_URL="${OMNICLAW_RPC_URL:-}"
BUYER_CP_PORT=9190
SELLER_CP_PORT=9191
SELLER_GATE_PORT=9291
LOG_DIR="$ROOT_DIR/logs/foundation_demo_tmux_$RUN_TS"
ATTACH=1

BUYER_TOKEN="payment-agent-token"
BUYER_ALIAS="omni-bot-v4"
SELLER_TOKEN="seller-agent-token"
SELLER_ALIAS="seller-api"
OWNER_TOKEN="foundation-demo-owner"
BLOCKED_URL="https://sensayhack-402.onrender.com"
PRICE="0.01"
ENDPOINT="/api/data"
SELLER_EXEC_CMD="printf '{\"result\":\"premium data unlocked\",\"provider\":\"agent-a\",\"settlement\":\"gateway-batched\",\"transport\":\"x402\"}\\n'"

usage() {
  cat <<'USAGE'
Usage: scripts/demo_foundation_tmux.sh [options]

Options:
  --session-name <name>       tmux session name
  --env-file <path>           Path to env file (default: .env)
  --network <name>            ETH-SEPOLIA or BASE-SEPOLIA
  --base                      Shortcut for --network BASE-SEPOLIA
  --eth                       Shortcut for --network ETH-SEPOLIA
  --rpc-url <url>             Override RPC URL
  --buyer-cp-port <port>      Buyer control plane port (default: 9190)
  --seller-cp-port <port>     Seller control plane port (default: 9191)
  --seller-gate-port <port>   Seller gate port (default: 9291)
  --log-dir <path>            Log directory for the run
  --no-attach                 Create the session without attaching
  -h, --help                  Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-name) SESSION_NAME="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --network) NETWORK="$2"; shift 2 ;;
    --base) NETWORK="BASE-SEPOLIA"; shift ;;
    --eth) NETWORK="ETH-SEPOLIA"; shift ;;
    --rpc-url) RPC_URL="$2"; shift 2 ;;
    --buyer-cp-port) BUYER_CP_PORT="$2"; shift 2 ;;
    --seller-cp-port) SELLER_CP_PORT="$2"; shift 2 ;;
    --seller-gate-port) SELLER_GATE_PORT="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --no-attach) ATTACH=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  python3 - "$port" <<'PY_PORT'
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
PY_PORT
}

pick_env() {
  local preferred="$1"
  local fallback="$2"
  if [[ -n "${!preferred:-}" ]]; then
    printf '%s' "${!preferred}"
    return 0
  fi
  if [[ -n "${!fallback:-}" ]]; then
    printf '%s' "${!fallback}"
    return 0
  fi
  return 1
}

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Missing required value: $name" >&2
    exit 1
  fi
}

require_cmd tmux
require_cmd bash
require_cmd curl
require_cmd jq
require_cmd python3
require_cmd omniclaw-cli
require_cmd uv
require_cmd base64
require_cmd awk

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

for port in "$BUYER_CP_PORT" "$SELLER_CP_PORT" "$SELLER_GATE_PORT"; do
  if [[ "$(port_in_use "$port")" == "in-use" ]]; then
    echo "Port $port is already in use. Free it or override the port flags." >&2
    exit 1
  fi
done

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

BUYER_CIRCLE_API_KEY="$(pick_env BUYER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
SELLER_CIRCLE_API_KEY="$(pick_env SELLER_CIRCLE_API_KEY CIRCLE_API_KEY || true)"
BUYER_ENTITY_SECRET="$(pick_env BUYER_ENTITY_SECRET ENTITY_SECRET || true)"
SELLER_ENTITY_SECRET="$(pick_env SELLER_ENTITY_SECRET ENTITY_SECRET || true)"
BUYER_PRIVATE_KEY="$(pick_env BUYER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"
SELLER_PRIVATE_KEY="$(pick_env SELLER_OMNICLAW_PRIVATE_KEY OMNICLAW_PRIVATE_KEY || true)"
OMNICLAW_LOG_LEVEL="${OMNICLAW_LOG_LEVEL:-INFO}"

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
DIRECTOR_LOG="$LOG_DIR/director.log"
BUYER_PANE_LOG="$LOG_DIR/buyer-pane.log"
SELLER_PANE_LOG="$LOG_DIR/seller-pane.log"
MONITOR_PANE_LOG="$LOG_DIR/monitor-pane.log"
STAGE_PANE_LOG="$LOG_DIR/stage-pane.log"

BUYER_BEFORE_JSON="$LOG_DIR/buyer-before.json"
BUYER_AFTER_JSON="$LOG_DIR/buyer-after.json"
SELLER_BEFORE_JSON="$LOG_DIR/seller-before.json"
SELLER_AFTER_JSON="$LOG_DIR/seller-after.json"
PAY_ONE_JSON="$LOG_DIR/pay-attempt-1.json"
PAY_FINAL_JSON="$LOG_DIR/pay-final.json"
APPROVE_JSON="$LOG_DIR/approve.json"
PAYMENT_REQUIRED_JSON="$LOG_DIR/payment-required.json"

BUYER_INIT="$LOG_DIR/buyer-shell.sh"
SELLER_INIT="$LOG_DIR/seller-shell.sh"
BUYER_RCFILE="$LOG_DIR/buyer-shell.rc"
SELLER_RCFILE="$LOG_DIR/seller-shell.rc"
MONITOR_SCRIPT="$LOG_DIR/monitor.sh"
STAGE_SCRIPT="$LOG_DIR/stage-log.sh"
DIRECTOR_SCRIPT="$LOG_DIR/director.sh"

PAY_URL="http://localhost:$SELLER_GATE_PORT$ENDPOINT"
PAY_KEY="foundation-tmux-$RUN_TS"
export ROOT_DIR RUN_TS SESSION_NAME NETWORK RPC_URL BUYER_CP_PORT SELLER_CP_PORT SELLER_GATE_PORT LOG_DIR
export BUYER_TOKEN BUYER_ALIAS SELLER_TOKEN SELLER_ALIAS OWNER_TOKEN BLOCKED_URL PRICE ENDPOINT SELLER_EXEC_CMD
export BUYER_CIRCLE_API_KEY SELLER_CIRCLE_API_KEY BUYER_ENTITY_SECRET SELLER_ENTITY_SECRET BUYER_PRIVATE_KEY SELLER_PRIVATE_KEY
export BUYER_POLICY_RUNTIME SELLER_POLICY_RUNTIME BUYER_CONFIG_DIR SELLER_CONFIG_DIR
export BUYER_CP_LOG SELLER_CP_LOG DIRECTOR_LOG BUYER_PANE_LOG SELLER_PANE_LOG MONITOR_PANE_LOG STAGE_PANE_LOG
export BUYER_BEFORE_JSON BUYER_AFTER_JSON SELLER_BEFORE_JSON SELLER_AFTER_JSON PAY_ONE_JSON PAY_FINAL_JSON APPROVE_JSON PAYMENT_REQUIRED_JSON
export BUYER_INIT SELLER_INIT BUYER_RCFILE SELLER_RCFILE MONITOR_SCRIPT STAGE_SCRIPT DIRECTOR_SCRIPT PAY_URL PAY_KEY OMNICLAW_LOG_LEVEL

cat > "$BUYER_RCFILE" <<'EOF_BUYER_RC'
export PS1='buyer-agent$ '
omniclaw_cli_wrap() {
  local attempt rc
  if [[ "${1:-}" == "pay" ]]; then
    for attempt in 1 2 3 4 5; do
      command omniclaw-cli "$@" && return 0
      rc=$?
      printf '[omniclaw-cli pay retry %d/5 after transient failure]\n' "$attempt" >&2
      sleep "$attempt"
    done
    return "$rc"
  fi
  command omniclaw-cli "$@"
}
alias omniclaw-cli='omniclaw_cli_wrap'
EOF_BUYER_RC
chmod +x "$BUYER_RCFILE"

cat > "$SELLER_RCFILE" <<'EOF_SELLER_RC'
export PS1='seller-agent$ '
EOF_SELLER_RC
chmod +x "$SELLER_RCFILE"

cat > "$BUYER_INIT" <<EOF_BUYER
#!/usr/bin/env bash
cd "$ROOT_DIR"
export OMNICLAW_CONFIG_DIR="$BUYER_CONFIG_DIR"
export OMNICLAW_SERVER_URL="http://127.0.0.1:$BUYER_CP_PORT"
export OMNICLAW_TOKEN="$BUYER_TOKEN"
export OMNICLAW_OWNER_TOKEN="$OWNER_TOKEN"
export CIRCLE_API_KEY="$BUYER_CIRCLE_API_KEY"
export ENTITY_SECRET="$BUYER_ENTITY_SECRET"
export OMNICLAW_PRIVATE_KEY="$BUYER_PRIVATE_KEY"
export OMNICLAW_NETWORK="$NETWORK"
export OMNICLAW_RPC_URL="$RPC_URL"
export PYTHONHASHSEED=0
clear
printf '\nBuyer Agent\n'
printf 'Same CLI. Buyer role. Command that matters: omniclaw-cli pay\n\n'
exec bash --noprofile --rcfile "$BUYER_RCFILE" -i
EOF_BUYER
chmod +x "$BUYER_INIT"

cat > "$SELLER_INIT" <<EOF_SELLER
#!/usr/bin/env bash
cd "$ROOT_DIR"
export OMNICLAW_CONFIG_DIR="$SELLER_CONFIG_DIR"
export OMNICLAW_SERVER_URL="http://127.0.0.1:$SELLER_CP_PORT"
export OMNICLAW_TOKEN="$SELLER_TOKEN"
export CIRCLE_API_KEY="$SELLER_CIRCLE_API_KEY"
export ENTITY_SECRET="$SELLER_ENTITY_SECRET"
export OMNICLAW_PRIVATE_KEY="$SELLER_PRIVATE_KEY"
export OMNICLAW_NETWORK="$NETWORK"
export OMNICLAW_RPC_URL="$RPC_URL"
export PYTHONHASHSEED=0
clear
printf '\nSeller Agent\n'
printf 'Same CLI. Seller role. Command that matters: omniclaw-cli serve\n\n'
exec bash --noprofile --rcfile "$SELLER_RCFILE" -i
EOF_SELLER
chmod +x "$SELLER_INIT"

cat > "$MONITOR_SCRIPT" <<'EOF_MONITOR'
#!/usr/bin/env bash
set -euo pipefail
buyer_url="http://127.0.0.1:$BUYER_CP_PORT/api/v1/balance-detail"
seller_url="http://127.0.0.1:$SELLER_CP_PORT/api/v1/balance-detail"
pay_url="$PAY_URL"
while true; do
  clear
  printf 'Circle Settlement Monitor\n\n'
  printf 'Thesis: same omniclaw-cli, two roles\n'
  printf 'buyer -> omniclaw-cli pay\n'
  printf 'seller -> omniclaw-cli serve\n\n'
  printf 'Network: %s\n' "$NETWORK"
  printf 'Paid Endpoint: %s\n\n' "$PAY_URL"

  gate_code="$(curl -s -o /dev/null -w '%{http_code}' "$pay_url" || true)"
  printf 'Seller Gate HTTP: %s\n\n' "$gate_code"

  if [[ -f "$PAYMENT_REQUIRED_JSON" ]]; then
    printf 'Seller Accepts GatewayWalletBatched\n'
    jq -C '{scheme: .accepts[0].extra.name, network: .accepts[0].network, pay_to: .accepts[0].payTo, amount_atomic: .accepts[0].amount, verifying_contract: .accepts[0].extra.verifyingContract}' "$PAYMENT_REQUIRED_JSON"
    printf '\n'
  else
    printf 'Seller Accepts GatewayWalletBatched\nwaiting for seller gate\n\n'
  fi

  if curl -fsS "$buyer_url" -H "Authorization: Bearer $BUYER_TOKEN" >/tmp/omniclaw-buyer-monitor.json 2>/dev/null; then
    buyer_now="$(jq -r '.gateway_balance_atomic' /tmp/omniclaw-buyer-monitor.json)"
    buyer_before=""
    if [[ -f "$BUYER_BEFORE_JSON" ]]; then
      buyer_before="$(jq -r '.gateway_balance_atomic' "$BUYER_BEFORE_JSON")"
    fi
    buyer_delta='n/a'
    if [[ -n "$buyer_before" ]]; then
      buyer_delta="$(awk -v a="$buyer_now" -v b="$buyer_before" 'BEGIN {printf "%+.6f", (a-b)/1000000}')"
    fi
    printf 'Buyer Gateway\n'
    jq -C '{eoa_address, gateway_balance, gateway_balance_atomic}' /tmp/omniclaw-buyer-monitor.json
    printf 'buyer delta: %s USDC\n\n' "$buyer_delta"
  else
    printf 'Buyer Gateway\nwaiting for buyer control plane\n\n'
  fi

  if curl -fsS "$seller_url" -H "Authorization: Bearer $SELLER_TOKEN" >/tmp/omniclaw-seller-monitor.json 2>/dev/null; then
    seller_now="$(jq -r '.gateway_balance_atomic' /tmp/omniclaw-seller-monitor.json)"
    seller_before=""
    if [[ -f "$SELLER_BEFORE_JSON" ]]; then
      seller_before="$(jq -r '.gateway_balance_atomic' "$SELLER_BEFORE_JSON")"
    fi
    seller_delta='n/a'
    if [[ -n "$seller_before" ]]; then
      seller_delta="$(awk -v a="$seller_now" -v b="$seller_before" 'BEGIN {printf "%+.6f", (a-b)/1000000}')"
    fi
    printf 'Seller Gateway\n'
    jq -C '{eoa_address, gateway_balance, gateway_balance_atomic}' /tmp/omniclaw-seller-monitor.json
    printf 'seller delta: %s USDC\n\n' "$seller_delta"
  else
    printf 'Seller Gateway\nwaiting for seller control plane\n\n'
  fi

  if [[ -f "$PAY_ONE_JSON" ]]; then
    printf 'Approval Envelope\n'
    jq -C '{status, method, requires_confirmation, confirmation_id}' "$PAY_ONE_JSON"
    printf '\n'
  fi

  if [[ -f "$PAY_FINAL_JSON" ]]; then
    printf 'Final Settlement\n'
    jq -C '{status, method, transaction_id}' "$PAY_FINAL_JSON"
    printf '\n'
  fi

  sleep 2
done
EOF_MONITOR
chmod +x "$MONITOR_SCRIPT"

cat > "$STAGE_SCRIPT" <<'EOF_STAGE'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$LOG_DIR"
touch "$DIRECTOR_LOG"
clear
printf 'Stage Log\n\n'
exec tail -n +1 -F "$DIRECTOR_LOG"
EOF_STAGE
chmod +x "$STAGE_SCRIPT"

cat > "$DIRECTOR_SCRIPT" <<'EOF_DIRECTOR'
#!/usr/bin/env bash
set -euo pipefail
buyer_pane="$BUYER_PANE_ID"
seller_pane="$SELLER_PANE_ID"

director_log="$DIRECTOR_LOG"
payment_required_json="$PAYMENT_REQUIRED_JSON"
pay_one_json="$PAY_ONE_JSON"
pay_final_json="$PAY_FINAL_JSON"
approve_json="$APPROVE_JSON"
buyer_before_json="$BUYER_BEFORE_JSON"
buyer_after_json="$BUYER_AFTER_JSON"
seller_before_json="$SELLER_BEFORE_JSON"
seller_after_json="$SELLER_AFTER_JSON"
pay_url="$PAY_URL"
pay_key="$PAY_KEY"
serve_exec_quoted="$(printf '%q' "$SELLER_EXEC_CMD")"

msg() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >> "$director_log"
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
    if (( $(date +%s) - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

wait_for_http_status() {
  local url="$1"
  local expected="$2"
  local timeout_secs="${3:-120}"
  local start_ts code
  start_ts="$(date +%s)"
  while true; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "$expected" ]]; then
      return 0
    fi
    if (( $(date +%s) - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

wait_for_file() {
  local path="$1"
  local timeout_secs="${2:-120}"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if [[ -s "$path" ]]; then
      return 0
    fi
    if (( $(date +%s) - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

api_balance_detail() {
  local side="$1"
  local url token
  if [[ "$side" == "buyer" ]]; then
    url="http://127.0.0.1:$BUYER_CP_PORT/api/v1/balance-detail"
    token="$BUYER_TOKEN"
  else
    url="http://127.0.0.1:$SELLER_CP_PORT/api/v1/balance-detail"
    token="$SELLER_TOKEN"
  fi
  curl -fsS -H "Authorization: Bearer $token" "$url"
}

decode_payment_required() {
  local url="$1"
  local headers_file="$LOG_DIR/payment-required.headers"
  local body_file="$LOG_DIR/payment-required.body"
  curl -sS -D "$headers_file" -o "$body_file" "$url" >/dev/null
  awk 'BEGIN{IGNORECASE=1} /^payment-required:/{sub(/^[^:]*:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit}' "$headers_file"
}

escape_squote() {
  printf '%s' "$1" | sed "s/'/'\\''/g"
}

send_text() {
  local pane="$1"
  local text="$2"
  local delay="${3:-0.012}"
  local i ch
  for ((i=0; i<${#text}; i++)); do
    ch="${text:i:1}"
    tmux send-keys -t "$pane" -l "$ch"
    sleep "$delay"
  done
}

run_cmd() {
  local pane="$1"
  local cmd="$2"
  send_text "$pane" "$cmd"
  tmux send-keys -t "$pane" Enter
}

wait_for_prompt() {
  local pane="$1"
  local prompt_prefix="$2"
  local timeout_secs="${3:-120}"
  local start_ts
  start_ts="$(date +%s)"
  while true; do
    if tmux capture-pane -p -t "$pane" | tail -n 40 | grep -Fq "$prompt_prefix"; then
      return 0
    fi
    if (( $(date +%s) - start_ts >= timeout_secs )); then
      return 1
    fi
    sleep 1
  done
}

note() {
  local pane="$1"
  local text="$2"
  local escaped
  escaped="$(escape_squote "$text")"
  run_cmd "$pane" "printf '\\n%s\\n\\n' '$escaped'"
}

sleep 2
msg 'Waiting for buyer and seller control planes'
wait_for_http_ok "http://127.0.0.1:$BUYER_CP_PORT/api/v1/health"
wait_for_http_ok "http://127.0.0.1:$SELLER_CP_PORT/api/v1/health"
msg 'Control planes live'

note "$buyer_pane" 'Buyer side: same CLI, using omniclaw-cli pay'
note "$seller_pane" 'Seller side: same CLI, using omniclaw-cli serve'
wait_for_prompt "$buyer_pane" "buyer-agent$" 30
wait_for_prompt "$seller_pane" "seller-agent$" 30
sleep 1

msg 'Configure buyer and seller through the same CLI'
run_cmd "$buyer_pane" "omniclaw-cli configure --server-url http://localhost:$BUYER_CP_PORT --token $BUYER_TOKEN --wallet $BUYER_ALIAS --owner-token $OWNER_TOKEN | jq -C '{ok, server_url, wallet}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 1
run_cmd "$seller_pane" "omniclaw-cli configure --server-url http://localhost:$SELLER_CP_PORT --token $SELLER_TOKEN --wallet $SELLER_ALIAS | jq -C '{ok, server_url, wallet}'"
wait_for_prompt "$seller_pane" "seller-agent$" 120
sleep 2

msg 'Both agents inspect their Gateway balances via omniclaw-cli'
run_cmd "$seller_pane" "omniclaw-cli balance-detail | tee '$SELLER_BEFORE_JSON' | jq -C '{eoa_address, gateway_balance, gateway_balance_atomic, circle_wallet_address}'"
wait_for_prompt "$seller_pane" "seller-agent$" 120
sleep 1
run_cmd "$buyer_pane" "omniclaw-cli balance-detail | tee '$BUYER_BEFORE_JSON' | jq -C '{eoa_address, gateway_balance, gateway_balance_atomic, circle_wallet_address}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 2

msg 'Buyer tries a malicious URL and policy blocks it before spend'
run_cmd "$buyer_pane" "omniclaw-cli can-pay --recipient '$BLOCKED_URL' | jq -C '{can_pay, reason}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 3

msg 'Seller publishes a paid endpoint with omniclaw-cli serve'
note "$seller_pane" 'Seller opens the API gate with omniclaw-cli serve'
wait_for_prompt "$seller_pane" "seller-agent$" 30
sleep 1
run_cmd "$seller_pane" "omniclaw-cli serve --price $PRICE --endpoint '$ENDPOINT' --exec $serve_exec_quoted --port $SELLER_GATE_PORT"
wait_for_http_status "$pay_url" 402 120
seller_402_header="$(decode_payment_required "$pay_url")"
printf '%s' "$seller_402_header" | base64 -d > "$payment_required_json"
msg 'Seller now accepts GatewayWalletBatched. Without seller serve, buyer pay is meaningless.'
sleep 2

msg 'Buyer confirms the seller endpoint is allowed by policy'
run_cmd "$buyer_pane" "omniclaw-cli can-pay --recipient '$pay_url' | jq -C '{can_pay, reason}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 2

msg 'Buyer requests payment through omniclaw-cli pay'
note "$buyer_pane" 'Buyer pays through omniclaw-cli pay'
wait_for_prompt "$buyer_pane" "buyer-agent$" 30
run_cmd "$buyer_pane" "omniclaw-cli pay --recipient '$pay_url' --idempotency-key '$pay_key' | tee '$pay_one_json' | jq -C '{success, status, method, requires_confirmation, confirmation_id}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 180
wait_for_file "$pay_one_json" 120
confirmation_id="$(jq -r '.confirmation_id // empty' "$pay_one_json")"
if [[ -z "$confirmation_id" || "$confirmation_id" == "null" ]]; then
  msg 'No confirmation id returned. Stopping demo.'
  exit 1
fi
sleep 2

msg 'Owner approves the spend envelope'
run_cmd "$buyer_pane" "omniclaw-cli confirmations approve --id '$confirmation_id' | tee '$approve_json' | jq -C '{status, recipient, amount, confirmation_id}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 2

msg 'Buyer retries omniclaw-cli pay and seller unlocks immediately'
run_cmd "$buyer_pane" "omniclaw-cli pay --recipient '$pay_url' --idempotency-key '$pay_key' | tee '$pay_final_json' | jq -C '{success, status, method, transaction_id, unlocked: (.response_data | (fromjson? // .))}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 180
wait_for_file "$pay_final_json" 180
sleep 4

buyer_before_gateway_atomic="$(jq -r '.gateway_balance_atomic' "$buyer_before_json")"
seller_before_gateway_atomic="$(jq -r '.gateway_balance_atomic' "$seller_before_json")"
buyer_after_detail=""
seller_after_detail=""
buyer_after_gateway_atomic="$buyer_before_gateway_atomic"
seller_after_gateway_atomic="$seller_before_gateway_atomic"
if [[ "$buyer_after_gateway_atomic" == "$buyer_before_gateway_atomic" && "$seller_after_gateway_atomic" == "$seller_before_gateway_atomic" ]]; then
  msg 'Waiting for Gateway contract balances to update'
fi
for ((attempt = 1; attempt <= 90; attempt++)); do
  buyer_after_detail="$(api_balance_detail buyer 2>/dev/null || true)"
  seller_after_detail="$(api_balance_detail seller 2>/dev/null || true)"
  if [[ -n "$buyer_after_detail" ]]; then
    buyer_after_candidate="$(printf '%s' "$buyer_after_detail" | jq -r '.gateway_balance_atomic' 2>/dev/null || true)"
    if [[ -n "$buyer_after_candidate" && "$buyer_after_candidate" != "null" ]]; then
      buyer_after_gateway_atomic="$buyer_after_candidate"
    fi
  fi
  if [[ -n "$seller_after_detail" ]]; then
    seller_after_candidate="$(printf '%s' "$seller_after_detail" | jq -r '.gateway_balance_atomic' 2>/dev/null || true)"
    if [[ -n "$seller_after_candidate" && "$seller_after_candidate" != "null" ]]; then
      seller_after_gateway_atomic="$seller_after_candidate"
    fi
  fi
  if [[ "$buyer_after_gateway_atomic" != "$buyer_before_gateway_atomic" || "$seller_after_gateway_atomic" != "$seller_before_gateway_atomic" ]]; then
    break
  fi
  sleep 1
done
if [[ -z "$buyer_after_detail" ]]; then
  buyer_after_detail="$(cat "$buyer_before_json")"
fi
if [[ -z "$seller_after_detail" ]]; then
  seller_after_detail="$(cat "$seller_before_json")"
fi
printf '%s\n' "$buyer_after_detail" > "$buyer_after_json"
printf '%s\n' "$seller_after_detail" > "$seller_after_json"

msg 'Buyer checks post-payment Gateway balance'
run_cmd "$buyer_pane" "omniclaw-cli balance-detail | tee '$buyer_after_json' | jq -C '{eoa_address, gateway_balance, gateway_balance_atomic, circle_wallet_address}'"
wait_for_prompt "$buyer_pane" "buyer-agent$" 120
sleep 2

msg 'Seller stops serve and checks earned Gateway balance'
tmux send-keys -t "$seller_pane" C-c
wait_for_prompt "$seller_pane" "seller-agent$" 60
sleep 2
run_cmd "$seller_pane" "omniclaw-cli balance-detail | tee '$seller_after_json' | jq -C '{eoa_address, gateway_balance, gateway_balance_atomic, circle_wallet_address}'"
wait_for_prompt "$seller_pane" "seller-agent$" 120
sleep 2
run_cmd "$seller_pane" "omniclaw-cli ledger --limit 1 | jq -C '.transactions[0] // {}'"
wait_for_prompt "$seller_pane" "seller-agent$" 120

msg 'Demo sequence complete'
EOF_DIRECTOR
chmod +x "$DIRECTOR_SCRIPT"

TMUX='' tmux new-session -d -s "$SESSION_NAME" -n demo -c "$ROOT_DIR" "bash '$BUYER_INIT'"
BUYER_PANE_ID="$(TMUX='' tmux display-message -p -t "$SESSION_NAME:0.0" '#{pane_id}')"
SELLER_PANE_ID="$(TMUX='' tmux split-window -h -P -F '#{pane_id}' -t "$BUYER_PANE_ID" -c "$ROOT_DIR" "bash '$SELLER_INIT'")"
MONITOR_PANE_ID="$(TMUX='' tmux split-window -v -P -F '#{pane_id}' -t "$BUYER_PANE_ID" -c "$ROOT_DIR" "env BUYER_CP_PORT='$BUYER_CP_PORT' SELLER_CP_PORT='$SELLER_CP_PORT' PAY_URL='$PAY_URL' NETWORK='$NETWORK' PAYMENT_REQUIRED_JSON='$PAYMENT_REQUIRED_JSON' BUYER_BEFORE_JSON='$BUYER_BEFORE_JSON' SELLER_BEFORE_JSON='$SELLER_BEFORE_JSON' PAY_ONE_JSON='$PAY_ONE_JSON' PAY_FINAL_JSON='$PAY_FINAL_JSON' BUYER_TOKEN='$BUYER_TOKEN' SELLER_TOKEN='$SELLER_TOKEN' bash '$MONITOR_SCRIPT'")"
STAGE_PANE_ID="$(TMUX='' tmux split-window -v -P -F '#{pane_id}' -t "$SELLER_PANE_ID" -c "$ROOT_DIR" "env LOG_DIR='$LOG_DIR' DIRECTOR_LOG='$DIRECTOR_LOG' bash '$STAGE_SCRIPT'")"
TMUX='' tmux select-layout -t "$SESSION_NAME:0" tiled
TMUX='' tmux set-window-option -t "$SESSION_NAME:0" pane-border-status top >/dev/null
TMUX='' tmux select-pane -t "$BUYER_PANE_ID" -T 'buyer-agent / omniclaw-cli'
TMUX='' tmux select-pane -t "$SELLER_PANE_ID" -T 'seller-agent / omniclaw-cli'
TMUX='' tmux select-pane -t "$MONITOR_PANE_ID" -T 'circle settlement'
TMUX='' tmux select-pane -t "$STAGE_PANE_ID" -T 'stage log'
TMUX='' tmux set-option -t "$SESSION_NAME" status-position top >/dev/null
TMUX='' tmux set-option -t "$SESSION_NAME" status-style 'bg=colour236,fg=colour255' >/dev/null
TMUX='' tmux set-option -t "$SESSION_NAME" status-left ' OmniClaw Live Demo ' >/dev/null
TMUX='' tmux set-option -t "$SESSION_NAME" status-right " $NETWORK | buyer:$BUYER_CP_PORT seller:$SELLER_CP_PORT gate:$SELLER_GATE_PORT " >/dev/null
TMUX='' tmux set-option -t "$SESSION_NAME" pane-active-border-style 'fg=colour45' >/dev/null
TMUX='' tmux set-option -t "$SESSION_NAME" pane-border-style 'fg=colour240' >/dev/null
TMUX='' tmux pipe-pane -o -t "$BUYER_PANE_ID" "cat >> '$BUYER_PANE_LOG'"
TMUX='' tmux pipe-pane -o -t "$SELLER_PANE_ID" "cat >> '$SELLER_PANE_LOG'"
TMUX='' tmux pipe-pane -o -t "$MONITOR_PANE_ID" "cat >> '$MONITOR_PANE_LOG'"
TMUX='' tmux pipe-pane -o -t "$STAGE_PANE_ID" "cat >> '$STAGE_PANE_LOG'"

TMUX='' tmux new-window -d -t "$SESSION_NAME" -n infra -c "$ROOT_DIR" "env CIRCLE_API_KEY='$BUYER_CIRCLE_API_KEY' ENTITY_SECRET='$BUYER_ENTITY_SECRET' OMNICLAW_PRIVATE_KEY='$BUYER_PRIVATE_KEY' OMNICLAW_AGENT_POLICY_PATH='$BUYER_POLICY_RUNTIME' OMNICLAW_AGENT_TOKEN='$BUYER_TOKEN' OMNICLAW_OWNER_TOKEN='$OWNER_TOKEN' OMNICLAW_NETWORK='$NETWORK' OMNICLAW_RPC_URL='$RPC_URL' OMNICLAW_STORAGE_BACKEND=memory OMNICLAW_POLICY_RELOAD_INTERVAL=0 OMNICLAW_LOG_LEVEL='$OMNICLAW_LOG_LEVEL' PYTHONUNBUFFERED=1 uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port '$BUYER_CP_PORT' --log-level warning 2>&1 | tee '$BUYER_CP_LOG'"
TMUX='' tmux split-window -h -t "$SESSION_NAME:1.0" -c "$ROOT_DIR" "env CIRCLE_API_KEY='$SELLER_CIRCLE_API_KEY' ENTITY_SECRET='$SELLER_ENTITY_SECRET' OMNICLAW_PRIVATE_KEY='$SELLER_PRIVATE_KEY' OMNICLAW_AGENT_POLICY_PATH='$SELLER_POLICY_RUNTIME' OMNICLAW_AGENT_TOKEN='$SELLER_TOKEN' OMNICLAW_NETWORK='$NETWORK' OMNICLAW_RPC_URL='$RPC_URL' OMNICLAW_STORAGE_BACKEND=memory OMNICLAW_POLICY_RELOAD_INTERVAL=0 OMNICLAW_LOG_LEVEL='$OMNICLAW_LOG_LEVEL' PYTHONUNBUFFERED=1 uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port '$SELLER_CP_PORT' --log-level warning 2>&1 | tee '$SELLER_CP_LOG'"
for kv in \
  "BUYER_PANE_ID=$BUYER_PANE_ID" \
  "SELLER_PANE_ID=$SELLER_PANE_ID" \
  "SESSION_NAME=$SESSION_NAME" \
  "BUYER_CP_PORT=$BUYER_CP_PORT" \
  "SELLER_CP_PORT=$SELLER_CP_PORT" \
  "SELLER_GATE_PORT=$SELLER_GATE_PORT" \
  "DIRECTOR_LOG=$DIRECTOR_LOG" \
  "PAYMENT_REQUIRED_JSON=$PAYMENT_REQUIRED_JSON" \
  "PAY_ONE_JSON=$PAY_ONE_JSON" \
  "PAY_FINAL_JSON=$PAY_FINAL_JSON" \
  "APPROVE_JSON=$APPROVE_JSON" \
  "BUYER_BEFORE_JSON=$BUYER_BEFORE_JSON" \
  "BUYER_AFTER_JSON=$BUYER_AFTER_JSON" \
  "SELLER_BEFORE_JSON=$SELLER_BEFORE_JSON" \
  "SELLER_AFTER_JSON=$SELLER_AFTER_JSON" \
  "PAY_URL=$PAY_URL" \
  "PAY_KEY=$PAY_KEY" \
  "BLOCKED_URL=$BLOCKED_URL" \
  "PRICE=$PRICE" \
  "ENDPOINT=$ENDPOINT" \
  "SELLER_EXEC_CMD=$SELLER_EXEC_CMD" \
  "BUYER_TOKEN=$BUYER_TOKEN" \
  "BUYER_ALIAS=$BUYER_ALIAS" \
  "SELLER_TOKEN=$SELLER_TOKEN" \
  "SELLER_ALIAS=$SELLER_ALIAS" \
  "OWNER_TOKEN=$OWNER_TOKEN" \
  "LOG_DIR=$LOG_DIR"
do
  TMUX='' tmux set-environment -t "$SESSION_NAME" "${kv%%=*}" "${kv#*=}"
done
TMUX='' tmux new-window -d -t "$SESSION_NAME" -n director -c "$ROOT_DIR" "bash '$DIRECTOR_SCRIPT' 2>&1 | tee -a '$DIRECTOR_LOG'"
TMUX='' tmux select-window -t "$SESSION_NAME:0"

echo "tmux session: $SESSION_NAME"
echo "log bundle: $LOG_DIR"
echo "attach: tmux attach -t $SESSION_NAME"

if [[ "$ATTACH" -eq 1 ]]; then
  tmux attach -t "$SESSION_NAME"
fi
