"""Tests for Tier 2 at-rest encryption (§16.2).

Use SIRR_ENCRYPTION_KEY seeded BEFORE importing crypto so the master key
is deterministic across tests. Each test uses its own context (order_id)
to verify per-record key isolation.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Must be set before import — crypto resolves master secret at module load
os.environ["SIRR_ENCRYPTION_KEY"] = "a" * 64  # 32 bytes hex = 64 chars

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
from crypto import (  # noqa: E402
    encrypt_bytes,
    decrypt_bytes,
    encrypt_str,
    decrypt_str,
    is_encrypted,
    read_maybe_encrypted,
    write_encrypted,
    write_encrypted_str,
    DecryptionError,
    MAGIC,
    VERSION,
    HEADER_LEN,
    NONCE_LEN,
    TAG_LEN,
)


def test_round_trip_bytes():
    pt = b"hello SIRR reading"
    blob = encrypt_bytes(pt, "ord_1")
    assert decrypt_bytes(blob, "ord_1") == pt


def test_round_trip_str():
    s = "Arabic نص مختلط with 🎯 emoji and newlines\n\nok"
    blob = encrypt_str(s, "ord_utf8")
    assert decrypt_str(blob, "ord_utf8") == s


def test_round_trip_large_payload():
    # 1 MiB payload — reading JSON can be large
    pt = b"x" * (1024 * 1024)
    blob = encrypt_bytes(pt, "ord_big")
    assert decrypt_bytes(blob, "ord_big") == pt


def test_blob_format_has_magic_and_version():
    blob = encrypt_bytes(b"x", "ord_fmt")
    assert blob[:4] == MAGIC
    assert blob[4] == VERSION


def test_blob_length_invariant():
    # encrypted(N) == HEADER(5) + NONCE(12) + N + TAG(16)
    pt = b"exactly-thirty-two-bytes-plaintext"
    blob = encrypt_bytes(pt, "ord_len")
    assert len(blob) == HEADER_LEN + NONCE_LEN + len(pt) + TAG_LEN


def test_is_encrypted_true_for_ciphertext():
    blob = encrypt_bytes(b"x", "ord_isenc")
    assert is_encrypted(blob) is True


def test_is_encrypted_false_for_plaintext():
    assert is_encrypted(b"<html>not encrypted</html>") is False
    assert is_encrypted(b"{}") is False
    assert is_encrypted(b"") is False
    assert is_encrypted(b"SIR") is False  # too short


def test_cross_context_rejected():
    blob = encrypt_bytes(b"secret", "ord_A")
    try:
        decrypt_bytes(blob, "ord_B")
    except DecryptionError:
        return
    raise AssertionError("cross-context decrypt should have failed")


def test_tampered_ciphertext_rejected():
    blob = bytearray(encrypt_bytes(b"payload", "ord_tamper"))
    # Flip a byte in the ciphertext body
    blob[-5] ^= 0xFF
    try:
        decrypt_bytes(bytes(blob), "ord_tamper")
    except DecryptionError:
        return
    raise AssertionError("tampered ciphertext should have failed")


def test_truncated_blob_rejected():
    blob = encrypt_bytes(b"payload", "ord_trunc")
    try:
        decrypt_bytes(blob[:10], "ord_trunc")
    except DecryptionError:
        return
    raise AssertionError("truncated blob should have failed")


def test_missing_magic_rejected():
    bad = b"NOPE" + b"\x01" + b"\x00" * 50
    try:
        decrypt_bytes(bad, "ord_x")
    except DecryptionError:
        return
    raise AssertionError("missing magic should have failed")


def test_wrong_version_rejected():
    bad = MAGIC + bytes([0xFF]) + b"\x00" * 50
    try:
        decrypt_bytes(bad, "ord_x")
    except DecryptionError:
        return
    raise AssertionError("wrong version should have failed")


def test_empty_plaintext_round_trip():
    blob = encrypt_bytes(b"", "ord_empty")
    assert decrypt_bytes(blob, "ord_empty") == b""


def test_context_required_nonempty_string():
    for bad in ["", None, 0, [], {}]:
        try:
            encrypt_bytes(b"x", bad)  # type: ignore
        except (ValueError, TypeError, AttributeError):
            continue
        raise AssertionError(f"context {bad!r} should have been rejected")


def test_plaintext_type_enforced():
    try:
        encrypt_bytes("a string not bytes", "ord_x")  # type: ignore
    except TypeError:
        return
    raise AssertionError("str plaintext should be rejected by encrypt_bytes")


def test_nonces_are_unique():
    # Two encryptions of the same plaintext under the same context should
    # produce different ciphertexts (due to random nonce).
    pt = b"same plaintext every time"
    blob1 = encrypt_bytes(pt, "ord_nonce")
    blob2 = encrypt_bytes(pt, "ord_nonce")
    assert blob1 != blob2
    # But both decrypt to the same thing
    assert decrypt_bytes(blob1, "ord_nonce") == pt
    assert decrypt_bytes(blob2, "ord_nonce") == pt


def test_file_round_trip():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "reading.html"
        text = "<html><body>Hello FATIMA</body></html>"
        write_encrypted_str(path, text, "ord_file")
        # File must not contain plaintext
        raw = path.read_bytes()
        assert b"FATIMA" not in raw
        assert is_encrypted(raw)
        # Read helper returns plaintext
        decoded = read_maybe_encrypted(path, "ord_file").decode("utf-8")
        assert decoded == text


def test_read_maybe_encrypted_passes_plaintext_through():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "legacy.json"
        path.write_bytes(b'{"ok": true}')
        assert read_maybe_encrypted(path, "any_context") == b'{"ok": true}'


def test_atomic_write_leaves_no_tmp_on_success():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "atomic.bin"
        write_encrypted(path, b"payload", "ord_atomic")
        siblings = list(path.parent.iterdir())
        assert len(siblings) == 1
        assert siblings[0].name == "atomic.bin"


def test_associated_data_binding():
    # A blob encrypted for ord_A, if its context is lied about to decrypt,
    # must fail even if the bytes are otherwise intact.
    blob = encrypt_bytes(b"bound-data", "ord_bind_A")
    try:
        decrypt_bytes(blob, "ord_bind_B")
    except DecryptionError:
        return
    raise AssertionError("associated-data mismatch should have been detected")
