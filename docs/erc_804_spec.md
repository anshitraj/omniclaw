# ERC-8004 Trust Notes

This file is a historical design note for OmniClaw's trust-layer direction. It is not the canonical API reference and should not be treated as a precise description of the current Financial Policy Engine implementation.

Use these docs for the current product surface instead:

- [README](../README.md)
- [Financial Policy Engine Usage Guide](SDK_USAGE_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Architecture and Features](FEATURES.md)

## Current Reality

OmniClaw already exposes a trust layer through the Financial Policy Engine:

- trust checks can run during `pay()` and `simulate()`
- trust behavior is controlled by `check_trust`
- explicit trust checks require a real `OMNICLAW_RPC_URL`
- trust evaluation can approve, hold, or block payment execution

## What This Note Represents

The earlier internal design work explored:

- ERC-8004 identity lookup
- reputation scoring and weighted trust signals
- policy-based approval, hold, and block behavior
- trust-aware payment execution
- auditability of trust decisions

Those themes still matter, but the exact content of the original internal draft no longer maps cleanly to the current codebase.

## Recommendation

If this repo keeps evolving quickly, treat trust docs the same way as the rest of the Financial Policy Engine docs:

- keep implementation details in code and tests
- keep user-facing behavior in the API reference and usage guide
- keep speculative product thinking in the roadmap, not in protocol documentation