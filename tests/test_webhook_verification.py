import base64
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from omniclaw.core.events import NotificationType
from omniclaw.core.exceptions import ValidationError
from omniclaw.webhooks.parser import DuplicateWebhookError, InvalidSignatureError, WebhookParser


@pytest.fixture
def key_pair():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def parser(key_pair):
    _, public_key = key_pair
    # Use hex format for default parser
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return WebhookParser(verification_key=pub_bytes.hex())


def sign_payload(private_key, payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    signature = private_key.sign(payload)
    return base64.b64encode(signature).decode("utf-8")


def test_verify_signature_valid(parser, key_pair):
    private_key, _ = key_pair
    payload = '{"test": "data"}'
    signature = sign_payload(private_key, payload)
    headers = {"x-circle-signature": signature}

    assert parser.verify_signature(payload, headers) is True


def test_verify_signature_invalid_signature(parser, key_pair):
    _, _ = key_pair
    payload = '{"test": "data"}'
    # Random signature
    signature = base64.b64encode(b"0" * 64).decode("utf-8")
    headers = {"x-circle-signature": signature}

    with pytest.raises(InvalidSignatureError, match="Signature mismatch"):
        parser.verify_signature(payload, headers)


def test_verify_signature_tampered_payload(parser, key_pair):
    private_key, _ = key_pair
    payload = '{"test": "data"}'
    signature = sign_payload(private_key, payload)
    headers = {"x-circle-signature": signature}

    # Verify with modified payload
    with pytest.raises(InvalidSignatureError, match="Signature mismatch"):
        parser.verify_signature('{"test": "hacked"}', headers)


def test_verify_signature_missing_header(parser):
    payload = '{"test": "data"}'
    headers = {}

    with pytest.raises(InvalidSignatureError, match="Missing x-circle-signature header"):
        parser.verify_signature(payload, headers)


def test_verify_signature_base64_key(key_pair):
    private_key, public_key = key_pair
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    b64_key = base64.b64encode(pub_bytes).decode("utf-8")

    parser = WebhookParser(verification_key=b64_key)
    payload = "data"
    signature = sign_payload(private_key, payload)
    headers = {"x-circle-signature": signature}

    assert parser.verify_signature(payload, headers) is True


def test_verify_signature_pem_key(key_pair):
    private_key, public_key = key_pair
    pem_key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    parser = WebhookParser(verification_key=pem_key)
    payload = "data"
    signature = sign_payload(private_key, payload)
    headers = {"x-circle-signature": signature}

    assert parser.verify_signature(payload, headers) is True


def test_no_verification_key():
    parser = WebhookParser(verification_key=None)
    payload = "data"
    headers = {}  # No header needed
    assert parser.verify_signature(payload, headers) is True


def test_handle_valid_payload(parser, key_pair):
    private_key, _ = key_pair
    # Valid timestamp (now)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_dict = {
        "notificationType": "payment_completed",
        "notificationId": "evt_123",
        "createDate": now_iso,
        "notification": {"status": "COMPLETE"},
    }
    payload = json.dumps(payload_dict)
    signature = sign_payload(private_key, payload)
    headers = {
        "x-circle-signature": signature,
        "x-circle-timestamp": str(int(datetime.now(timezone.utc).timestamp())),
    }

    event = parser.handle(payload, headers)
    assert event.type == NotificationType.PAYMENT_COMPLETED
    assert event.id == "evt_123"


def test_handle_missing_createdate(parser, key_pair):
    private_key, _ = key_pair
    payload_dict = {
        "notificationType": "payment_completed",
        "notificationId": "evt_123",
        # missing createDate
        "notification": {"status": "COMPLETE"},
    }
    payload = json.dumps(payload_dict)
    signature = sign_payload(private_key, payload)
    headers = {"x-circle-signature": signature}

    with pytest.raises(ValidationError, match="createDate"):
        parser.handle(payload, headers)


def test_handle_replay_attack(parser, key_pair):
    private_key, _ = key_pair
    # Timestamp beyond default max replay age window (12 hours).
    old_time = datetime.now(timezone.utc) - timedelta(hours=13)
    payload_dict = {
        "notificationType": "payment_completed",
        "notificationId": "evt_123",
        "createDate": old_time.isoformat(),
        "notification": {"status": "COMPLETE"},
    }
    payload = json.dumps(payload_dict)
    signature = sign_payload(private_key, payload)
    headers = {
        "x-circle-signature": signature,
        "x-circle-timestamp": str(int(old_time.timestamp())),
    }

    with pytest.raises(InvalidSignatureError, match="replay age window"):
        parser.handle(payload, headers)


def test_handle_rejects_duplicate_notification_id(key_pair):
    private_key, public_key = key_pair
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        dedup_db = f"{tmpdir}/webhook_dedup.sqlite3"
        with patch.dict(os.environ, {"OMNICLAW_WEBHOOK_DEDUP_DB_PATH": dedup_db}, clear=False):
            parser = WebhookParser(verification_key=pub_bytes.hex())

            now_iso = datetime.now(timezone.utc).isoformat()
            payload_dict = {
                "notificationType": "payment_completed",
                "notificationId": "evt_duplicate_1",
                "createDate": now_iso,
                "notification": {"status": "COMPLETE"},
            }
            payload = json.dumps(payload_dict)
            signature = sign_payload(private_key, payload)
            headers = {
                "x-circle-signature": signature,
                "x-circle-timestamp": str(int(datetime.now(timezone.utc).timestamp())),
            }

            parser.handle(payload, headers)

            parser_again = WebhookParser(verification_key=pub_bytes.hex())
            with pytest.raises(DuplicateWebhookError, match="Duplicate webhook notificationId"):
                parser_again.handle(payload, headers)
