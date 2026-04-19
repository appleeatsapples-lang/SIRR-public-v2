"""Tests for sanitize.py — traceback PII redaction (§16.5)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web_backend"))
from sanitize import (  # noqa: E402
    sanitize_line,
    sanitize_traceback,
    sanitize_exception,
    sanitize_exc_now,
)


def test_empty_inputs():
    assert sanitize_line("") == ""
    assert sanitize_traceback("") == ""
    assert sanitize_traceback(None) == ""  # type: ignore
    assert sanitize_exception(None) == ""  # type: ignore


def test_file_paths_preserved():
    line = 'File "/app/engine/runner.py", line 42, in compute'
    assert "/app/engine/runner.py" in sanitize_line(line)


def test_quoted_name_redacted():
    line = 'ValueError: name="Fatima Alkatib"'
    out = sanitize_line(line)
    assert "Fatima" not in out
    assert "<redacted>" in out


def test_email_redacted():
    line = "ConnectionError: reach user@example.com failed"
    out = sanitize_line(line)
    assert "user@example.com" not in out
    assert "<redacted-email>" in out


def test_iso_date_redacted():
    line = "born 1990-03-15 rejected"
    out = sanitize_line(line)
    assert "1990-03-15" not in out
    assert "<redacted-date>" in out


def test_nonascii_burst_redacted():
    line = "name: فاطمة أحمد"
    out = sanitize_line(line)
    # Arabic chars must not survive
    assert "فاطمة" not in out
    assert "<redacted-nonascii>" in out


def test_long_digits_redacted():
    assert "<redacted-digits>" in sanitize_line("phone=1234567890 id")
    # Short digits allowed (line numbers, years alone)
    assert "42" in sanitize_line("line 42 in foo")


def test_sanitize_exception_drops_message_entirely():
    try:
        name = "Fatima Ahmed Omar Alkatib"
        raise ValueError(f"invalid name: {name} dob 1990-03-15")
    except ValueError as e:
        out = sanitize_exception(e)
    # Class name kept
    assert "ValueError" in out
    # Placeholder kept
    assert "<message-redacted>" in out
    # The actual name must not survive
    assert "Fatima" not in out
    # The actual date must not survive
    assert "1990-03-15" not in out


def test_sanitize_exception_handles_chained():
    try:
        try:
            raise RuntimeError("inner with email foo@bar.com")
        except RuntimeError as inner:
            raise ValueError("outer") from inner
    except ValueError as e:
        out = sanitize_exception(e)
    # Must not contain the unredacted email from inner
    assert "foo@bar.com" not in out


def test_max_chars_truncation():
    big = "a" * 10000
    out = sanitize_traceback(big, max_chars=100)
    assert len(out) <= 200  # 100 + truncation marker allowance
    assert out.endswith("a" * 100)
    assert "[truncated]" in out


def test_structural_debug_info_preserved():
    tb = 'File "/app/code.py", line 99, in process_request\n  raise SomeError'
    out = sanitize_traceback(tb)
    assert "/app/code.py" in out
    assert "line 99" in out
    assert "process_request" in out


def test_path_with_spaces_not_overredacted():
    # Paths with slashes survive even if they're quoted
    line = 'File "/Users/muhab/my project/code.py"'
    out = sanitize_line(line)
    assert "/Users/muhab/my project/code.py" in out
