"""Tier 2 at-rest encryption (§16.2).

Envelope-encrypts reading JSON and HTML files using AES-256-GCM with
per-record keys derived via HKDF-SHA256 from a master secret.

Format on disk:
    b'SIRR' || version_byte || nonce(12) || ciphertext || tag(16)

The magic prefix 'SIRR' lets us distinguish encrypted blobs from legacy
plaintext on read, so grandfathered files remain readable during the
transition window.

Key derivation:
    record_key = HKDF-SHA256(
        input_key_material = master_secret,
        salt = order_id encoded UTF-8,
        info = b"sirr-tier2-v1",
        length = 32,
    )

This binds each order's key to that order's ID. An attacker who exfiltrated
one record's key cannot decrypt any other record. The master secret lives
only in the production environment (SIRR_ENCRYPTION_KEY); no backups, no
laptop copies, no git.

Master-secret cascade (priority order):
  1. SIRR_ENCRYPTION_KEY env (hex-encoded; min 32 bytes after decode)
  2. Derived from STRIPE_WEBHOOK_SECRET (dev-friendly; production should
     use a dedicated key)
  3. Per-process random with warning — means ciphertexts don't survive
     restart, so callers should fall back to plaintext in that mode
"""
from __future__ import annotations

import os
import secrets
import sys
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Magic header: b'SIRR' + 1 version byte
MAGIC = b"SIRR"
VERSION = 0x01
HEADER = MAGIC + bytes([VERSION])
HEADER_LEN = len(HEADER)  # 5

NONCE_LEN = 12  # AES-GCM standard
KEY_LEN = 32  # AES-256
TAG_LEN = 16  # GCM auth tag (appended automatically)

# ── Master secret derivation ──────────────────────────────────────────────

_EPHEMERAL_WARNING_PRINTED = False


def _load_master_secret() -> bytes:
    """Resolve the master secret at module import time.

    Priority:
      1. SIRR_ENCRYPTION_KEY (hex)
      2. SHA256-derivation from STRIPE_WEBHOOK_SECRET
      3. Per-process random + warning
    """
    global _EPHEMERAL_WARNING_PRINTED
    hex_key = os.environ.get("SIRR_ENCRYPTION_KEY", "").strip()
    if hex_key:
        try:
            decoded = bytes.fromhex(hex_key)
            if len(decoded) >= 32:
                return decoded[:32]
            print(
                f"[WARN] SIRR_ENCRYPTION_KEY too short "
                f"({len(decoded)} bytes, need 32). Falling back.",
                file=sys.stderr,
            )
        except ValueError:
            print(
                "[WARN] SIRR_ENCRYPTION_KEY is not valid hex. Falling back.",
                file=sys.stderr,
            )

    stripe_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if stripe_secret:
        import hashlib

        return hashlib.sha256(
            b"sirr-tier2-master-v1|" + stripe_secret.encode("utf-8")
        ).digest()

    if not _EPHEMERAL_WARNING_PRINTED:
        print(
            "[WARN] No SIRR_ENCRYPTION_KEY or STRIPE_WEBHOOK_SECRET set — "
            "Tier 2 encryption uses a per-process random master secret. "
            "Ciphertexts will NOT survive server restart. "
            "Set SIRR_ENCRYPTION_KEY in production.",
            file=sys.stderr,
        )
        _EPHEMERAL_WARNING_PRINTED = True
    return secrets.token_bytes(32)


_MASTER = _load_master_secret()


def _derive_record_key(context: str) -> bytes:
    """Derive a per-record AES-256 key from master + context (order_id)."""
    if not context or not isinstance(context, str):
        raise ValueError("context (order_id) must be a non-empty string")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=context.encode("utf-8"),
        info=b"sirr-tier2-v1",
    )
    return hkdf.derive(_MASTER)

# ── Core encrypt / decrypt primitives ─────────────────────────────────────


class DecryptionError(Exception):
    """Raised when ciphertext is malformed or authentication fails.

    Never contains plaintext or key material in its message — safe to
    surface to logs."""


def encrypt_bytes(plaintext: bytes, context: str) -> bytes:
    """Encrypt plaintext under a per-record key bound to `context` (order_id).

    Output layout:
        MAGIC(4) || VERSION(1) || NONCE(12) || CIPHERTEXT || TAG(16)
    """
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("plaintext must be bytes")
    key = _derive_record_key(context)
    nonce = secrets.token_bytes(NONCE_LEN)
    aesgcm = AESGCM(key)
    # associated_data binds context into auth tag so a blob can't be
    # cut/pasted between orders without detection
    blob = aesgcm.encrypt(nonce, bytes(plaintext), context.encode("utf-8"))
    return HEADER + nonce + blob


def decrypt_bytes(blob: bytes, context: str) -> bytes:
    """Decrypt a blob produced by encrypt_bytes.

    Raises DecryptionError on malformed input, wrong version, tamper, or
    key mismatch. Does NOT raise plaintext-bearing error messages.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("blob must be bytes")
    if len(blob) < HEADER_LEN + NONCE_LEN + TAG_LEN:
        raise DecryptionError("blob too short to be valid ciphertext")
    if bytes(blob[:4]) != MAGIC:
        raise DecryptionError("missing magic header")
    version = blob[4]
    if version != VERSION:
        raise DecryptionError(f"unsupported ciphertext version: {version}")
    nonce = bytes(blob[HEADER_LEN : HEADER_LEN + NONCE_LEN])
    ct = bytes(blob[HEADER_LEN + NONCE_LEN :])
    key = _derive_record_key(context)
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ct, context.encode("utf-8"))
    except Exception:
        # Intentionally generic — don't leak which step failed
        raise DecryptionError("decryption failed (tamper or wrong key)")


def is_encrypted(blob: bytes) -> bool:
    """Return True if `blob` starts with our magic header.

    Used for backward-compat on read: if a file is already encrypted, we
    decrypt; if it's plaintext (legacy grandfathered data), we return as-is.
    """
    if not blob or len(blob) < HEADER_LEN:
        return False
    return bytes(blob[:4]) == MAGIC and blob[4] == VERSION

# ── String / file convenience wrappers ────────────────────────────────────


def encrypt_str(text: str, context: str) -> bytes:
    """UTF-8 encode then encrypt_bytes."""
    return encrypt_bytes(text.encode("utf-8"), context)


def decrypt_str(blob: bytes, context: str) -> str:
    """decrypt_bytes then UTF-8 decode."""
    return decrypt_bytes(blob, context).decode("utf-8")


def read_maybe_encrypted(path, context: str) -> bytes:
    """Read a file, decrypting if it has our magic header, else returning
    raw bytes. Used on the read-path for grandfathered plaintext records.

    `path` may be a str or pathlib.Path."""
    from pathlib import Path

    p = Path(path) if not isinstance(path, Path) else path
    raw = p.read_bytes()
    if is_encrypted(raw):
        return decrypt_bytes(raw, context)
    return raw


def write_encrypted(path, data: bytes, context: str) -> None:
    """Encrypt then write to disk. Uses atomic-ish replace (write tmp, rename)
    so a crash mid-write doesn't leave a partially-written file."""
    from pathlib import Path

    p = Path(path) if not isinstance(path, Path) else path
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".enc-tmp")
    tmp.write_bytes(encrypt_bytes(data, context))
    tmp.replace(p)


def write_encrypted_str(path, text: str, context: str) -> None:
    write_encrypted(path, text.encode("utf-8"), context)
