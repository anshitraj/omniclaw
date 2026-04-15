# ERC-8004 Trust Notes

This document explains how ERC-8004 concepts show up in OmniClaw today.

It is a trust-layer overview, not the canonical SDK or API reference. For the main product surface, use:

- [README](../README.md)
- [Developer Guide](developer-guide.md)
- [API Reference](API_REFERENCE.md)
- [Architecture and Features](FEATURES.md)

## How OmniClaw Uses ERC-8004

OmniClaw exposes trust evaluation through the Financial Policy Engine:

- trust checks can run during `pay()` and `simulate()`
- trust behavior is controlled by `check_trust`
- explicit trust checks require a real `OMNICLAW_RPC_URL`
- trust evaluation can approve, hold, or block payment execution

## What The Trust Layer Covers

The trust system is built around:

- ERC-8004 identity lookup
- reputation scoring and weighted trust signals
- policy-based approval, hold, and block behavior
- trust-aware payment execution
- auditability of trust decisions

## Practical Guidance

Treat this file as conceptual background.

Use:

- the SDK and API docs for integration details
- the code and tests for implementation behavior
- the roadmap for future trust-layer expansion
