from decimal import Decimal

from omniclaw.core.idempotency import derive_idempotency_key


def test_derive_idempotency_key_normalizes_equivalent_numeric_inputs() -> None:
    key_from_decimal = derive_idempotency_key("transfer", "wallet-1", "0xabc", Decimal("1.00"))
    key_from_string = derive_idempotency_key("transfer", "wallet-1", "0xabc", "1")
    key_from_string_with_whitespace = derive_idempotency_key(
        "transfer", "wallet-1", "0xabc", " 1.0000 "
    )

    assert key_from_decimal == key_from_string
    assert key_from_string == key_from_string_with_whitespace
