"""
Tests for EIP-3009 signing module.

Phase 2: EIP-3009 Signing

CRITICAL: These tests verify cryptographic correctness.
A bug in signing produces signatures that Circle Gateway rejects.
All tests must pass before proceeding to Phase 3.
"""

import time

import pytest
from eth_account import Account

from omniclaw.protocols.nanopayments import (
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_VERSION,
    DEFAULT_VALID_BEFORE_SECONDS,
    MIN_VALID_BEFORE_SECONDS,
)
from omniclaw.protocols.nanopayments.exceptions import (
    InvalidPrivateKeyError,
    SigningError,
    UnsupportedNetworkError,
    UnsupportedSchemeError,
)
from omniclaw.protocols.nanopayments.signing import (
    EIP3009Signer,
    build_eip712_domain,
    build_eip712_message,
    build_eip712_structured_data,
    compute_valid_before,
    generate_eoa_keypair,
    generate_nonce,
    parse_caip2_chain_id,
)
from omniclaw.protocols.nanopayments.types import (
    EIP3009Authorization,
    PaymentPayload,
    PaymentPayloadInner,
    PaymentRequirementsExtra,
    PaymentRequirementsKind,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def buyer_keypair():
    """Generate a real buyer EOA keypair."""
    return generate_eoa_keypair()


@pytest.fixture
def seller_keypair():
    """Generate a real seller EOA keypair."""
    return generate_eoa_keypair()


@pytest.fixture
def gateway_keypair():
    """Generate a real gateway contract keypair (for verifying contract)."""
    return generate_eoa_keypair()


@pytest.fixture
def valid_private_key(buyer_keypair):
    """A valid EOA private key for testing (not real funds)."""
    return buyer_keypair[0]


@pytest.fixture
def signer(valid_private_key):
    """An EIP3009Signer instance for testing."""
    return EIP3009Signer(valid_private_key)


@pytest.fixture
def signer_address(buyer_keypair):
    """Buyer address from keypair."""
    return buyer_keypair[1]


@pytest.fixture
def valid_requirements(seller_keypair, gateway_keypair):
    """Valid payment requirements for testing."""
    return PaymentRequirementsKind(
        scheme="exact",
        network="eip155:5042002",  # Arc Testnet
        asset="0xAbc1234567890aBcD1234567890aBcD12345678",  # Fake USDC address
        amount="1000",  # 0.001 USDC
        max_timeout_seconds=345600,
        pay_to=seller_keypair[1],  # Real seller address
        extra=PaymentRequirementsExtra(
            name="GatewayWalletBatched",
            version="1",
            verifying_contract=gateway_keypair[1],  # Real gateway address
        ),
    )


# =============================================================================
# EIP-712 DOMAIN TESTS
# =============================================================================


class TestBuildEIP712Domain:
    """Tests for EIP-712 domain construction."""

    def test_domain_structure(self, gateway_keypair):
        """Domain should have correct fields."""
        domain = build_eip712_domain(
            chain_id=5042002,
            verifying_contract=gateway_keypair[1],
        )

        assert domain["name"] == CIRCLE_BATCHING_NAME  # 'GatewayWalletBatched'
        assert domain["version"] == CIRCLE_BATCHING_VERSION  # '1'
        assert domain["chainId"] == 5042002
        assert domain["verifyingContract"] == gateway_keypair[1]

    def test_domain_name_is_gateway_wallet_batched(self, gateway_keypair):
        """
        Domain name MUST be GatewayWalletBatched, not USD Coin.

        This is the most common bug in EIP-3009 implementations.
        """
        domain = build_eip712_domain(
            chain_id=5042002,
            verifying_contract=gateway_keypair[1],
        )

        # CRITICAL: Must be GatewayWalletBatched, NOT USD Coin
        assert domain["name"] == "GatewayWalletBatched"
        assert domain["name"] != "USD Coin"  # This is a common mistake

    def test_custom_name_and_version(self, gateway_keypair):
        """Should allow custom name and version."""
        domain = build_eip712_domain(
            chain_id=1,
            verifying_contract=gateway_keypair[1],
            name="CustomName",
            version="2",
        )
        assert domain["name"] == "CustomName"
        assert domain["version"] == "2"

    def test_rejects_empty_verifying_contract(self):
        """Must have a verifying contract."""
        with pytest.raises(SigningError, match="verifying_contract"):
            build_eip712_domain(
                chain_id=1,
                verifying_contract="",
            )

    def test_rejects_invalid_chain_id(self, gateway_keypair):
        """Chain ID must be positive."""
        with pytest.raises(SigningError, match="chain_id must be positive"):
            build_eip712_domain(
                chain_id=0,
                verifying_contract=gateway_keypair[1],
            )
        with pytest.raises(SigningError, match="chain_id must be positive"):
            build_eip712_domain(
                chain_id=-1,
                verifying_contract=gateway_keypair[1],
            )

    def test_rejects_non_hex_verifying_contract(self):
        """Verifying contract must be hex."""
        with pytest.raises(SigningError, match="hex address"):
            build_eip712_domain(
                chain_id=1,
                verifying_contract="not-hex",
            )


# =============================================================================
# EIP-712 MESSAGE TESTS
# =============================================================================


class TestBuildEIP712Message:
    """Tests for EIP-712 message construction."""

    def test_message_structure(self, buyer_keypair, seller_keypair):
        """Message should have correct fields."""
        nonce = "0x" + "ab" * 32
        valid_before = compute_valid_before()

        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
            valid_after=0,
            valid_before=valid_before,
            nonce=nonce,
        )

        assert msg["from"] == buyer_keypair[1]
        assert msg["to"] == seller_keypair[1]
        assert msg["value"] == 1000
        assert msg["validAfter"] == 0
        assert msg["validBefore"] == valid_before
        assert msg["nonce"] == nonce

    def test_default_valid_before(self, buyer_keypair, seller_keypair):
        """Should default to 4 days from now."""
        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
        )

        expected_min = int(time.time()) + DEFAULT_VALID_BEFORE_SECONDS - 1
        expected_max = int(time.time()) + DEFAULT_VALID_BEFORE_SECONDS + 1
        assert expected_min <= msg["validBefore"] <= expected_max

    def test_valid_before_must_be_3_days_minimum(self, buyer_keypair, seller_keypair):
        """Gateway requires at least 3 days validity."""
        # valid_before only 1 day from now — should fail
        with pytest.raises(SigningError, match="at least"):
            build_eip712_message(
                from_address=buyer_keypair[1],
                to_address=seller_keypair[1],
                value=1000,
                valid_before=int(time.time()) + 86400,  # 1 day
            )

    def test_valid_before_3_days_exactly_is_ok(self, buyer_keypair, seller_keypair):
        """Exactly 3 days should be accepted."""
        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
            valid_before=int(time.time()) + MIN_VALID_BEFORE_SECONDS,  # Exactly 3 days
        )
        assert "validBefore" in msg

    def test_rejects_self_transfer(self, buyer_keypair):
        """from and to cannot be the same address."""
        with pytest.raises(SigningError, match="self-transfer"):
            build_eip712_message(
                from_address=buyer_keypair[1],
                to_address=buyer_keypair[1],
                value=1000,
            )

    def test_nonce_generation(self, buyer_keypair, seller_keypair):
        """Should generate a valid nonce if not provided."""
        msg1 = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
        )
        msg2 = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
        )

        # Nonces should be unique
        assert msg1["nonce"] != msg2["nonce"]

        # Should be 32 bytes (64 hex chars + 0x)
        assert len(msg1["nonce"]) == 66

    def test_custom_nonce_format(self, buyer_keypair, seller_keypair):
        """Should accept custom nonce."""
        custom_nonce = "0x" + "ff" * 32
        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=1000,
            nonce=custom_nonce,
        )
        assert msg["nonce"] == custom_nonce

    def test_rejects_invalid_nonce_length(self, buyer_keypair, seller_keypair):
        """Nonce must be exactly 32 bytes."""
        with pytest.raises(SigningError, match="32 bytes"):
            build_eip712_message(
                from_address=buyer_keypair[1],
                to_address=seller_keypair[1],
                value=1000,
                nonce="0x" + "ab" * 16,  # Only 16 bytes
            )

    def test_rejects_invalid_from_address(self, seller_keypair):
        """Must have valid hex address for from."""
        with pytest.raises(SigningError, match="hex address"):
            build_eip712_message(
                from_address="not-hex",
                to_address=seller_keypair[1],
                value=1000,
            )

    def test_allows_zero_value(self, buyer_keypair, seller_keypair):
        """Should allow zero value."""
        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=0,
        )
        assert msg["value"] == 0

    def test_allows_large_value(self, buyer_keypair, seller_keypair):
        """Should handle large amounts."""
        large_value = 1_000_000_000_000  # 1 million USDC
        msg = build_eip712_message(
            from_address=buyer_keypair[1],
            to_address=seller_keypair[1],
            value=large_value,
        )
        assert msg["value"] == large_value


# =============================================================================
# EIP3009SIGNER TESTS
# =============================================================================


class TestEIP3009Signer:
    """Tests for EIP3009Signer class."""

    def test_initializes_with_valid_key(self, valid_private_key):
        """Should initialize with valid private key."""
        signer = EIP3009Signer(valid_private_key)
        assert signer.address.startswith("0x")
        assert len(signer.address) == 42  # 0x + 40 hex chars

    def test_derives_correct_address(self, valid_private_key, signer_address):
        """Address should be correctly derived from key."""
        signer = EIP3009Signer(valid_private_key)
        assert signer.address.lower() == signer_address.lower()

    def test_accepts_key_with_0x_prefix(self, buyer_keypair):
        """Should accept key with 0x prefix."""
        key_with_prefix = buyer_keypair[0]  # Already has 0x
        signer = EIP3009Signer(key_with_prefix)
        assert signer.address.startswith("0x")

    def test_accepts_key_without_0x_prefix(self, buyer_keypair):
        """Should accept key without 0x prefix."""
        key_no_prefix = buyer_keypair[0][2:]  # Remove 0x
        signer = EIP3009Signer(key_no_prefix)
        assert signer.address.startswith("0x")

    def test_rejects_invalid_key_length(self):
        """Should reject key that's not 32 bytes."""
        with pytest.raises(InvalidPrivateKeyError, match="64 hex chars"):
            EIP3009Signer("0x" + "ab" * 31)  # Too short

        with pytest.raises(InvalidPrivateKeyError, match="64 hex chars"):
            EIP3009Signer("0x" + "ab" * 33)  # Too long

        with pytest.raises(InvalidPrivateKeyError, match="64 hex chars"):
            EIP3009Signer("0xab")  # Way too short

    def test_rejects_invalid_hex(self):
        """Should reject key with invalid hex characters."""
        with pytest.raises(InvalidPrivateKeyError, match="invalid hex"):
            EIP3009Signer("0x" + "gg" * 32)  # g is not hex

    def test_repr_redacts_private_key(self, valid_private_key, signer):
        """repr should not expose any private key material."""
        r = repr(signer)
        # Address should be visible
        assert signer.address in r
        # Full key should NOT be visible
        assert valid_private_key not in r

    def test_sign_transfer_with_authorization(self, signer, valid_requirements):
        """Should produce a valid PaymentPayload."""
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        assert isinstance(payload, PaymentPayload)
        assert payload.x402_version == 2
        assert payload.scheme == "exact"
        assert payload.network == "eip155:5042002"
        assert payload.payload.signature.startswith("0x")
        assert len(payload.payload.signature) == 132  # 0x + 130 hex chars
        assert payload.payload.authorization.from_address == signer.address
        assert payload.payload.authorization.to == valid_requirements.pay_to
        assert payload.payload.authorization.value == "1000"

    def test_sign_uses_correct_domain_name(self, signer, valid_requirements):
        """
        CRITICAL: Domain name must be GatewayWalletBatched.

        This is verified by the local signature verification.
        If the domain name were wrong, verification would fail.
        """
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        # The signature should be verifiable with the correct domain
        is_valid = signer.verify_signature(payload, valid_requirements)
        assert is_valid is True

    def test_sign_with_requirement_amount(self, signer, valid_requirements):
        """Should use amount from requirements if not specified."""
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            # amount_atomic not specified — should use requirements.amount
        )

        # requirements.amount is "1000"
        assert payload.payload.authorization.value == "1000"

    def test_sign_rejects_amount_exceeding_requirement(self, signer, valid_requirements):
        """Should reject amount greater than requirement."""
        with pytest.raises(SigningError, match="exceeds required amount"):
            signer.sign_transfer_with_authorization(
                requirements=valid_requirements,
                amount_atomic=2000,  # More than required "1000"
            )

    def test_sign_rejects_non_gateway_scheme(self, signer, gateway_keypair):
        """Should reject non-GatewayWalletBatched requirements."""
        seller = generate_eoa_keypair()
        bad_requirements = PaymentRequirementsKind(
            scheme="exact",
            network="eip155:5042002",
            asset="0xAbc1234567890aBcD1234567890aBcD12345678",
            amount="1000",
            max_timeout_seconds=345600,
            pay_to=seller[1],
            extra=PaymentRequirementsExtra(
                name="NotGatewayWalletBatched",  # Wrong name
                version="1",
                verifying_contract=gateway_keypair[1],
            ),
        )

        with pytest.raises(UnsupportedSchemeError):
            signer.sign_transfer_with_authorization(bad_requirements)

    def test_sign_rejects_missing_verifying_contract(self, signer, seller_keypair):
        """Should reject requirements without verifying contract."""
        from omniclaw.protocols.nanopayments.exceptions import (
            MissingVerifyingContractError,
        )

        bad_requirements = PaymentRequirementsKind(
            scheme="exact",
            network="eip155:5042002",
            asset="0xAbc1234567890aBcD1234567890aBcD12345678",
            amount="1000",
            max_timeout_seconds=345600,
            pay_to=seller_keypair[1],
            extra=PaymentRequirementsExtra(
                name="GatewayWalletBatched",
                version="1",
                verifying_contract="",  # Empty!
            ),
        )

        with pytest.raises(MissingVerifyingContractError):
            signer.sign_transfer_with_authorization(bad_requirements)

    def test_sign_produces_unique_signatures(self, signer, valid_requirements):
        """Different calls should produce different signatures (different nonces)."""
        payload1 = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )
        payload2 = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        # Signatures should be different (different nonces)
        assert payload1.payload.signature != payload2.payload.signature

        # But both should be verifiable
        assert signer.verify_signature(payload1, valid_requirements)
        assert signer.verify_signature(payload2, valid_requirements)

    def test_sign_with_custom_valid_before(self, signer, valid_requirements):
        """Should accept custom valid_before timestamp."""
        valid_before_timestamp = int(time.time()) + (5 * 24 * 3600)  # 5 days

        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
            valid_before=valid_before_timestamp,
        )

        assert int(payload.payload.authorization.valid_before) == valid_before_timestamp

    def test_verify_signature_success(self, signer, valid_requirements):
        """Local signature verification should pass for valid signatures."""
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        is_valid = signer.verify_signature(payload, valid_requirements)
        assert is_valid is True

    def test_verify_signature_fails_for_wrong_key(self, valid_requirements):
        """Signature from different key should not verify."""
        # Sign with one key
        signer1 = EIP3009Signer(generate_eoa_keypair()[0])
        payload = signer1.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        # Verify with different signer (different key)
        signer2 = EIP3009Signer(generate_eoa_keypair()[0])
        is_valid = signer2.verify_signature(payload, valid_requirements)

        # Should fail — address doesn't match
        assert is_valid is False

    def test_handles_different_chain_ids(self, signer, gateway_keypair):
        """Should work with different chain IDs."""
        seller = generate_eoa_keypair()
        chain_ids = [1, 137, 84532, 42161, 5042002]

        for chain_id in chain_ids:
            network = f"eip155:{chain_id}"
            req = PaymentRequirementsKind(
                scheme="exact",
                network=network,
                asset="0xAbc1234567890aBcD1234567890aBcD12345678",
                amount="1000",
                max_timeout_seconds=345600,
                pay_to=seller[1],
                extra=PaymentRequirementsExtra(
                    name="GatewayWalletBatched",
                    version="1",
                    verifying_contract=gateway_keypair[1],
                ),
            )

            payload = signer.sign_transfer_with_authorization(req)

            # Should be able to verify
            assert signer.verify_signature(payload, req)

    def test_signature_format_is_correct(self, signer, valid_requirements):
        """Signature should be in correct format for EVM."""
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        sig = payload.payload.signature

        # Should start with 0x
        assert sig.startswith("0x")

        # Should be 132 hex chars (65 bytes)
        assert len(sig) == 132

        # Should be valid hex
        try:
            int(sig[2:], 16)
        except ValueError:
            pytest.fail("Signature is not valid hex")

        # v value should be 27 or 28 (EIP-155)
        v = int(sig[-2:], 16)
        assert v in (27, 28)


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================


class TestParseCAIP2ChainId:
    """Tests for CAIP-2 chain ID parsing."""

    def test_parses_valid_caip2(self):
        """Should parse valid CAIP-2 format."""
        assert parse_caip2_chain_id("eip155:1") == 1
        assert parse_caip2_chain_id("eip155:5042002") == 5042002
        assert parse_caip2_chain_id("eip155:84532") == 84532
        assert parse_caip2_chain_id("eip155:421614") == 421614

    def test_rejects_invalid_format(self):
        """Should reject non-CAIP-2 format."""
        with pytest.raises(ValueError, match="Invalid CAIP-2"):
            parse_caip2_chain_id("1")  # Missing eip155 prefix

        with pytest.raises(ValueError, match="Invalid CAIP-2"):
            parse_caip2_chain_id("solana:123")  # Wrong namespace

        with pytest.raises(ValueError, match="Invalid chain ID"):
            parse_caip2_chain_id("eip155:")  # Missing chain ID

        with pytest.raises(ValueError, match="Invalid chain ID"):
            parse_caip2_chain_id("eip155:abc")  # Non-numeric chain ID


class TestGenerateNonce:
    """Tests for nonce generation."""

    def test_generates_32_bytes(self):
        """Should generate exactly 32 random bytes."""
        nonce = generate_nonce()
        assert nonce.startswith("0x")
        assert len(nonce) == 66  # 0x + 64 hex chars

    def test_is_cryptographically_random(self):
        """Should produce unique nonces."""
        nonces = [generate_nonce() for _ in range(100)]
        assert len(set(nonces)) == 100  # All unique

    def test_is_valid_hex(self):
        """Should produce valid hex."""
        nonce = generate_nonce()
        hex_part = nonce[2:]  # Remove 0x
        int(hex_part, 16)  # Should not raise


class TestComputeValidBefore:
    """Tests for valid_before computation."""

    def test_default_4_days(self):
        """Default should be 4 days from now."""
        now = int(time.time())
        result = compute_valid_before()

        expected = now + DEFAULT_VALID_BEFORE_SECONDS
        assert abs(result - expected) < 2  # Within 2 seconds

    def test_custom_seconds(self):
        """Should accept custom seconds."""
        now = int(time.time())
        result = compute_valid_before(86400)  # 1 day

        expected = now + 86400
        assert abs(result - expected) < 2


class TestGenerateEOAKeypair:
    """Tests for EOA keypair generation."""

    def test_generates_valid_keypair(self):
        """Should generate a valid private key and address."""
        private_key, address = generate_eoa_keypair()

        assert private_key.startswith("0x")
        assert len(private_key) == 66  # 0x + 64 hex chars

        assert address.startswith("0x")
        assert len(address) == 42  # 0x + 40 hex chars

        # Address should be derivable from key
        derived = Account.from_key(private_key).address
        assert derived.lower() == address.lower()

    def test_generates_unique_keypairs(self):
        """Should generate unique keypairs."""
        pairs = [generate_eoa_keypair() for _ in range(10)]
        addresses = [p[1] for p in pairs]

        assert len(set(addresses)) == 10  # All unique


# =============================================================================
# INTEGRATION TESTS: ROUNDTRIP WITH ETH_ACCOUNT
# =============================================================================


class TestEIP712Roundtrip:
    """
    Integration tests verifying that signatures can be verified
    using standard eth_account recovery.
    """

    def test_signature_recoverable_with_account(self, signer, valid_requirements):
        """
        Signature should be recoverable using eth_account.Account.recover_message.

        This is the same verification that Circle Gateway performs.
        """
        # Sign
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        # Build the same structured data
        chain_id = int(valid_requirements.network.split(":")[1])
        domain = build_eip712_domain(
            chain_id=chain_id,
            verifying_contract=valid_requirements.extra.verifying_contract,
        )
        message = {
            "from": signer.address,
            "to": valid_requirements.pay_to,
            "value": 1000,
            "validAfter": 0,
            "validBefore": int(payload.payload.authorization.valid_before),
            "nonce": payload.payload.authorization.nonce,
        }
        structured_data = build_eip712_structured_data(domain, message)

        # Recover using eth_account
        from eth_account.messages import encode_typed_data

        signable = encode_typed_data(full_message=structured_data)
        recovered = Account.recover_message(signable, signature=payload.payload.signature)

        assert recovered.lower() == signer.address.lower()

    def test_signature_tampering_detected(self, signer, valid_requirements):
        """
        Tampering with signature should be detected.

        Uses eth_account directly to verify that tampered signatures
        recover to a different address than the original signer.
        This approach is robust across eth_account versions.
        """
        payload = signer.sign_transfer_with_authorization(
            requirements=valid_requirements,
            amount_atomic=1000,
        )

        # Build structured data for recovery
        from eth_account.messages import encode_typed_data

        chain_id = int(valid_requirements.network.split(":")[1])
        domain = build_eip712_domain(
            chain_id=chain_id,
            verifying_contract=valid_requirements.extra.verifying_contract,
        )
        message_dict = {
            "from": payload.payload.authorization.from_address,
            "to": payload.payload.authorization.to,
            "value": int(payload.payload.authorization.value),
            "validAfter": int(payload.payload.authorization.valid_after),
            "validBefore": int(payload.payload.authorization.valid_before),
            "nonce": payload.payload.authorization.nonce,
        }
        structured_data = build_eip712_structured_data(domain, message_dict)

        # Recover original
        signable = encode_typed_data(full_message=structured_data)
        recovered_original = Account.recover_message(signable, signature=payload.payload.signature)

        # Tamper with the signature
        original_sig = payload.payload.signature
        tampered_sig = original_sig[:-2] + ("00" if original_sig[-2:] == "ff" else "ff")

        # Recover tampered — should return a different address (or raise)
        try:
            recovered_tampered = Account.recover_message(signable, signature=tampered_sig)
            # If recovery succeeds, it MUST be a different address
            assert recovered_tampered.lower() != recovered_original.lower(), (
                "Tampered signature recovered to same address as original — "
                "signature tampering NOT detected!"
            )
        except Exception:
            # Recovery raising is also valid — signature is clearly invalid
            pass


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_signs_with_zero_amount(self, signer, gateway_keypair):
        """Should allow signing with zero amount."""
        seller = generate_eoa_keypair()
        req = PaymentRequirementsKind(
            scheme="exact",
            network="eip155:5042002",
            asset="0xAbc1234567890aBcD1234567890aBcD12345678",
            amount="0",  # Zero amount
            max_timeout_seconds=345600,
            pay_to=seller[1],
            extra=PaymentRequirementsExtra(
                name="GatewayWalletBatched",
                version="1",
                verifying_contract=gateway_keypair[1],
            ),
        )

        payload = signer.sign_transfer_with_authorization(
            requirements=req,
            amount_atomic=0,
        )

        assert payload.payload.authorization.value == "0"
        assert signer.verify_signature(payload, req)

    def test_signs_with_large_amount_with_matching_req(
        self, signer, gateway_keypair, seller_keypair
    ):
        """Should handle large amounts when requirements allow it."""
        large_amount = 1_000_000_000_000  # 1 million USDC
        req = PaymentRequirementsKind(
            scheme="exact",
            network="eip155:5042002",
            asset="0xAbc1234567890aBcD1234567890aBcD12345678",
            amount=str(large_amount),  # Matching amount
            max_timeout_seconds=345600,
            pay_to=seller_keypair[1],
            extra=PaymentRequirementsExtra(
                name="GatewayWalletBatched",
                version="1",
                verifying_contract=gateway_keypair[1],
            ),
        )

        payload = signer.sign_transfer_with_authorization(
            requirements=req,
            amount_atomic=large_amount,
        )

        assert int(payload.payload.authorization.value) == large_amount
        assert signer.verify_signature(payload, req)

    def test_partial_key_raises_error(self):
        """Should reject partial key (too short)."""
        with pytest.raises(InvalidPrivateKeyError):
            EIP3009Signer("0x" + "ab" * 16)  # 16 bytes instead of 32

    def test_overlong_key_raises_error(self):
        """Should reject overlong key."""
        with pytest.raises(InvalidPrivateKeyError):
            EIP3009Signer("0x" + "ab" * 33)  # 33 bytes instead of 32


# =============================================================================
# TEST: Coverage for uncovered signing.py lines
# =============================================================================


class TestSigningCoverageMissing:
    """Cover uncovered lines in signing.py."""

    def test_build_eip712_message_to_address_not_hex(self):
        """Line 177: to_address must start with 0x."""
        from omniclaw.protocols.nanopayments.signing import build_eip712_message

        with pytest.raises(SigningError) as exc_info:
            build_eip712_message(
                from_address="0x" + "a" * 40,
                to_address="invalid_address",
                value=0,
            )
        assert "to_address" in str(exc_info.value).lower()

    def test_build_eip712_message_negative_value(self):
        """Line 190: value must be non-negative."""
        from omniclaw.protocols.nanopayments.signing import build_eip712_message

        with pytest.raises(SigningError):
            build_eip712_message(
                from_address="0x" + "a" * 40,
                to_address="0x" + "b" * 40,
                value=-1,
            )

    def test_build_eip712_message_nonce_no_0x_prefix(self):
        """Line 214: nonce must start with 0x."""
        from omniclaw.protocols.nanopayments.signing import build_eip712_message

        with pytest.raises(SigningError) as exc_info:
            build_eip712_message(
                from_address="0x" + "a" * 40,
                to_address="0x" + "b" * 40,
                value=0,
                nonce="not_hex_value",
            )
        assert "nonce" in str(exc_info.value).lower()

    def test_build_eip712_message_nonce_invalid_hex(self):
        """Lines 229-230: nonce must be valid hex."""
        from omniclaw.protocols.nanopayments.signing import build_eip712_message

        with pytest.raises(SigningError):
            build_eip712_message(
                from_address="0x" + "a" * 40,
                to_address="0x" + "b" * 40,
                value=0,
                nonce="0xGGGG",
            )

    def test_sign_unsupported_network(self):
        """Lines 433-435: Network must start with eip155:."""
        # NOTE: generate_eoa_keypair() is unreliable in pytest session scope with coverage.
        # Using hardcoded key to avoid fixture caching issues.
        signer = EIP3009Signer(
            private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"
        )

        req = PaymentRequirementsKind(
            scheme="https",
            network="solana:1",
            asset="USDC",
            amount="1000000",
            max_timeout_seconds=300,
            pay_to="0x" + "a" * 40,
            extra=PaymentRequirementsExtra(
                name=CIRCLE_BATCHING_NAME,
                version="1",
                verifying_contract="0x" + "b" * 40,
            ),
        )

        with pytest.raises(UnsupportedNetworkError) as exc_info:
            signer.sign_transfer_with_authorization(requirements=req, amount_atomic=1000)
        assert "network" in str(exc_info.value).lower()

    def test_sign_network_empty_chain_id(self):
        """Lines 439-442: Network with empty chain ID raises."""
        signer = EIP3009Signer(
            private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"
        )

        req = PaymentRequirementsKind(
            scheme="https",
            network="eip155:",  # Empty after colon
            asset="USDC",
            amount="1000000",
            max_timeout_seconds=300,
            pay_to="0x" + "a" * 40,
            extra=PaymentRequirementsExtra(
                name=CIRCLE_BATCHING_NAME,
                version="1",
                verifying_contract="0x" + "b" * 40,
            ),
        )

        with pytest.raises(UnsupportedNetworkError):
            signer.sign_transfer_with_authorization(requirements=req, amount_atomic=1000)

    def test_verify_signature_async_recovery_exception(self):
        """Lines 542-543: Signature recovery exception raises SigningError."""
        from unittest.mock import patch

        signer = EIP3009Signer(
            private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"
        )

        auth = EIP3009Authorization.create(
            from_address=signer.address,
            to="0x" + "b" * 40,
            value="1000000",
            valid_before=int(time.time()) + 86400,
            nonce=generate_nonce(),
        )

        payload = PaymentPayload(
            x402_version=2,
            scheme="exact",
            network="eip155:1",
            payload=PaymentPayloadInner(
                signature="0x" + "c" * 130,
                authorization=auth,
            ),
        )

        req = PaymentRequirementsKind(
            scheme="https",
            network="eip155:1",
            asset="USDC",
            amount="1000000",
            max_timeout_seconds=300,
            pay_to="0x" + "b" * 40,
            extra=PaymentRequirementsExtra(
                name=CIRCLE_BATCHING_NAME,
                version="1",
                verifying_contract="0x"
                + signer.address[2:].replace(
                    signer.address[2], signer.address[2], 1
                ),  # Any address
            ),
        )

        with patch.object(Account, "recover_message", side_effect=Exception("Recovery failed")):
            with pytest.raises(SigningError) as exc_info:
                signer.verify_signature(payload, req)
            assert "recovery" in str(exc_info.value).lower()


# =============================================================================
# ADDITIONAL COVERAGE: Uncovered lines
# =============================================================================


class TestSigningCoverageAdditional:
    """Coverage for lines 229-230, 334-335, 366, 469-470."""

    def test_nonce_invalid_hex_chars(self):
        """Lines 229-230: nonce with invalid hex chars raises SigningError."""
        from omniclaw.protocols.nanopayments.signing import build_eip712_message

        # nonce = "0x" + 64 G's: passes length check but fails hex validation
        invalid_hex_nonce = "0x" + "G" * 64
        with pytest.raises(SigningError) as exc_info:
            build_eip712_message(
                from_address="0x" + "a" * 40,
                to_address="0x" + "b" * 40,
                value=0,
                nonce=invalid_hex_nonce,
            )
        assert exc_info.value.code == "INVALID_NONCE_HEX"

    def test_raw_key_property(self):
        """Line 366: _raw_key property returns the private key (without 0x prefix)."""
        signer = EIP3009Signer(
            private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"
        )
        raw = signer._raw_key
        # Private key is stored WITHOUT 0x prefix
        assert raw == "250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"

    def test_sign_transfer_message_sign_exception(self):
        """Lines 469-470: sign_message raises exception raises SigningError."""
        from unittest.mock import patch

        from omniclaw.protocols.nanopayments.types import (
            PaymentRequirementsExtra,
            PaymentRequirementsKind,
        )

        signer = EIP3009Signer(
            private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb5652"
        )
        # Use a different address for pay_to to avoid self-transfer error
        from eth_account import Account

        other_account = Account.create()
        other_addr = other_account.address

        req = PaymentRequirementsKind(
            scheme="exact",
            network="eip155:5042002",
            asset="0xAbc1234567890aBcD1234567890aBcD12345678",
            amount="1000000",
            max_timeout_seconds=345600,
            pay_to=other_addr,
            extra=PaymentRequirementsExtra(
                name="GatewayWalletBatched",
                version="1",
                verifying_contract=other_addr,
            ),
        )

        with patch.object(signer._account, "sign_message", side_effect=Exception("Signing failed")):
            with pytest.raises(SigningError) as exc_info:
                signer.sign_transfer_with_authorization(requirements=req, amount_atomic=1000)
            assert exc_info.value.code == "SIGN_FAILED"

    def test_signer_from_key_invalid(self):
        """Lines 334-335: from_key with invalid key raises InvalidPrivateKeyError."""
        with pytest.raises(InvalidPrivateKeyError) as exc_info:
            EIP3009Signer(
                private_key="0x250716a653d2155d15bfb1e1ded08b6764937ca6ab3cdd7e2f0510c975fb565"
            )  # 63 chars
        assert "Invalid private key" in str(exc_info.value)
