#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8010}"

curl -fsS -X POST "${BASE_URL}/api/admin/reset" >/dev/null

printf 'Arc vendor demo state reset at %s\n' "$BASE_URL"
printf 'Summary:\n'
curl -fsS "${BASE_URL}/api/summary"
printf '\n'
