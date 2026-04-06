#!/bin/bash
export CIRCLE_API_KEY=TEST_API_KEY:511a1daf3edd65884326e8f56368088a:396b2b196a9206c435c08de607f7ee2b
export OMNICLAW_PRIVATE_KEY=0x5ec6f9922879be60d25c2d10b39a89cd8138eeffedc077296a174c2a1b9254c0
export OMNICLAW_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
export OMNICLAW_NETWORK=ETH-SEPOLIA
export OMNICLAW_AGENT_TOKEN=seller-agent-token
export OMNICLAW_AGENT_POLICY_PATH=/home/abiorh/omnuron-labs/omniclaw/examples/agent/seller/policy.json
cd /home/abiorh/omnuron-labs/omniclaw
exec uv run uvicorn omniclaw.agent.server:app --host 0.0.0.0 --port 8081
