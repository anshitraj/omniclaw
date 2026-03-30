#!/bin/bash
set -e

# The Agent is responsible for its own environment.
# Requires environment variables: OMNICLAW_SERVER_URL, OMNICLAW_TOKEN

echo "🚀 Bootstrapping OmniClaw Agent Environment..."

# 1. Install CLI
if [ -d "/home/abiorh/omnuron-labs/omniclaw" ]; then
    pip install --break-system-packages -e /home/abiorh/omnuron-labs/omniclaw
else
    pip install --break-system-packages omniclaw
fi

# 2. Configure CLI
SERVER_URL="${OMNICLAW_SERVER_URL:-http://localhost:8080}"
TOKEN="${OMNICLAW_TOKEN:-payment-agent-token}"
WALLET="${OMNICLAW_WALLET:-primary}"

echo "⚙️ Configuring OmniClaw CLI (Target: $SERVER_URL)..."
omniclaw-cli configure \
    --server-url "$SERVER_URL" \
    --token "$TOKEN" \
    --wallet "$WALLET"

# 3. Verify Health
echo "🩺 Verifying Firewall Connectivity..."
omniclaw-cli ping

echo "✅ OmniClaw Bootstrap Complete!"
