from omniclaw.core.migrations import (
    backfill_ledger_entries,
    normalize_ledger_entry,
    normalize_payment_status_value,
)


def test_normalize_payment_status_value_maps_legacy_values():
    assert normalize_payment_status_value("completed") == "settled"
    assert normalize_payment_status_value("processing") == "pending_settlement"
    assert normalize_payment_status_value("failed") == "failed"


def test_normalize_ledger_entry_backfills_pending_settlement_flag():
    entry = {
        "id": "e1",
        "status": "pending",
        "metadata": {"transaction_id": "tx-1"},
    }
    normalized, changed = normalize_ledger_entry(entry)
    assert changed is True
    assert normalized["metadata"]["settlement_final"] is False


def test_backfill_ledger_entries_counts_changes():
    entries = [
        {"id": "a", "status": "completed", "metadata": {}},
        {"id": "b", "status": "pending", "metadata": {"transaction_id": "tx-b"}},
        {"id": "c", "status": "pending", "metadata": {}},
    ]
    normalized, changed = backfill_ledger_entries(entries)
    assert changed == 2
    assert normalized[0]["metadata"]["settlement_final"] is True
    assert normalized[1]["metadata"]["settlement_final"] is False
    assert "settlement_final" not in normalized[2]["metadata"]
