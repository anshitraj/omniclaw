# Local Economy Example

This is the canonical local buyer/seller OmniClaw example.

It contains:
- buyer stack: `docker-compose.payment-agent.yml`
- seller stack: `docker-compose.seller-agent.yml`
- buyer policy: `payment-agent.policy.json`
- seller policy: `seller-agent.policy.json`

Roles:
- buyer uses `omniclaw-cli pay`
- seller uses `omniclaw-cli serve`

Default ports:
- buyer Financial Policy Engine: `9090`
- seller Financial Policy Engine: `9091`
- seller paid endpoint example: `8000`

Start buyer:
```bash
docker compose -p omniclaw-buyer -f examples/local-economy/docker-compose.payment-agent.yml up -d --build --remove-orphans
```

Start seller:
```bash
docker compose -p omniclaw-seller -f examples/local-economy/docker-compose.seller-agent.yml up -d --build --remove-orphans
```
