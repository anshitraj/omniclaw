# OmniClaw Cross-Chain Usage

Use cross-chain routing when you want OmniClaw to send USDC from the source wallet network to a recipient on another supported chain.

## Basic Example

```python
from omniclaw import OmniClaw, Network

client = OmniClaw(network=Network.ETH_SEPOLIA)

result = await client.pay(
    wallet_id="wallet_123",
    recipient="0x742d35Cc6634C0532925a3b844Bc9e7595f5e4a0",
    amount="10.00",
    destination_chain=Network.BASE_SEPOLIA,
)
```

If `destination_chain` is provided, the payment router uses the gateway adapter instead of a same-chain transfer.

## Wait for Completion

```python
result = await client.pay(
    wallet_id="wallet_123",
    recipient="0xRecipientOnBase",
    amount="50.00",
    destination_chain=Network.BASE_SEPOLIA,
    wait_for_completion=True,
    timeout_seconds=180,
)
```

## Simulation

```python
sim = await client.simulate(
    wallet_id="wallet_123",
    recipient="0xRecipientOnBase",
    amount="20.00",
    destination_chain=Network.BASE_SEPOLIA,
)
```

## Operational Notes

- Cross-chain flows depend on the source and destination networks being supported by the configured gateway/CCTP path.
- Same-chain transfers should not specify a different `destination_chain`.
- Use `wait_for_completion=True` only when the caller is prepared to block for provider-side polling.
- Before production use, verify network support with Circle’s current chain support before relying on a pair in production.

## Result Metadata

Cross-chain executions may include adapter-specific metadata such as transfer mode, source and destination domains, or attestation-related information. Treat these as informative fields rather than a stable public contract unless your application controls the exact adapter behavior.

## Recommended Workflow

1. simulate the transfer
2. execute with a caller-supplied `idempotency_key`
3. inspect `result.status` and `result.metadata`
4. use the ledger or provider transaction lookup for reconciliation
