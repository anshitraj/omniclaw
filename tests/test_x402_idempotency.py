"""Test that x402 idempotency key derivation is deterministic."""

from omniclaw.core.idempotency import derive_idempotency_key


def test_x402_idempotency_key_is_deterministic():
    """Same inputs should always produce the same idempotency key."""
    key_a = derive_idempotency_key(
        "x402",
        "wallet-1",
        "https://api.example.com/data",
        "GET",
        {"query": "a"},
        None,
        "eip155:11155111",
    )
    key_b = derive_idempotency_key(
        "x402",
        "wallet-1",
        "https://api.example.com/data",
        "GET",
        {"query": "a"},
        None,
        "eip155:11155111",
    )
    assert key_a == key_b


def test_x402_idempotency_key_changes_with_inputs():
    """Different inputs should produce different idempotency keys."""
    key_a = derive_idempotency_key(
        "x402",
        "wallet-1",
        "https://api.example.com/data",
        "GET",
        {"query": "a"},
        None,
        "eip155:11155111",
    )
    key_b = derive_idempotency_key(
        "x402",
        "wallet-1",
        "https://api.example.com/data",
        "GET",
        {"query": "b"},
        None,
        "eip155:11155111",
    )
    assert key_a != key_b
