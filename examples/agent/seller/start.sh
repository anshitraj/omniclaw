#!/bin/bash
export CIRCLE_API_KEY=${CIRCLE_API_KEY:-}
export OMNICLAW_PRIVATE_KEY=${OMNICLAW_PRIVATE_KEY:-}
export OMNICLAW_RPC_URL=${OMNICLAW_RPC_URL:-https://ethereum-sepolia-rpc.publicnode.com}
export OMNICLAW_NETWORK=${OMNICLAW_NETWORK:-ETH-SEPOLIA}
export OMNICLAW_AGENT_TOKEN=${OMNICLAW_AGENT_TOKEN:-seller-agent-token}
export OMNICLAW_AGENT_POLICY_PATH=${OMNICLAW_AGENT_POLICY_PATH:-$(pwd)/examples/agent/seller/policy.json}
exec uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port 8081
