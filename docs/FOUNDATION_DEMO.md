# Foundation Demo

Official dual-sided OmniClaw demo flow:

1. Buyer policy blocks a malicious URL instantly.
2. Seller exposes a paid API behind `omniclaw-cli serve`.
3. Buyer checks budget, triggers approval, and pays with `omniclaw-cli pay`.
4. Script waits for Circle Gateway batch settlement to update buyer/seller Gateway contract balances.

## Default Run

```bash
scripts/demo_foundation_showcase.sh
```

Defaults:

- network: `ETH-SEPOLIA`
- buyer Financial Policy Engine: `http://localhost:9190`
- seller Financial Policy Engine: `http://localhost:9191`
- seller paid endpoint: `http://localhost:9291/api/data`

## Base Mode

```bash
scripts/demo_foundation_showcase.sh --base
```

Equivalent explicit form:

```bash
scripts/demo_foundation_showcase.sh --network BASE-SEPOLIA
```

If the current wallets are not funded on Base Sepolia, the script now stops early with a clear funding hint instead of failing late in the flow.

## Ethereum Explicit

```bash
scripts/demo_foundation_showcase.sh --eth
```

## Recording Layout

One-command tmux layout:

```bash
scripts/demo_foundation_tmux.sh
```

It opens:

- top-left: buyer terminal using `omniclaw-cli pay`
- top-right: seller terminal using `omniclaw-cli serve`
- bottom-left: live Circle Gateway settlement monitor
- bottom-right: stage log with the demo narrative

There is also a hidden `infra` tmux window running the two OmniClaw Financial Policy Engine processes.

Base version:

```bash
scripts/demo_foundation_tmux.sh --base
```

## Notes

- The payment step remains `omniclaw-cli pay`.
- The budget simulation step uses the Financial Policy Engine API because `omniclaw-cli simulate` is still intermittently unstable in this environment.
- Logs are written under `logs/foundation_demo_*` or `logs/foundation_demo_tmux_*`.
