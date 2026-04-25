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


def test_runner_error_field_uses_class_name_only():
    """The runner.py semantic/psych error fields must store only the
    exception class name — never str(e), which could carry user input."""

    class FakePipelineError(ValueError):
        pass

    err = FakePipelineError("leaked user input: muhab-akif-23sep1996")
    # Simulate the runner.py error-field pattern
    out = {"error": type(err).__name__, "status": "PIPELINE_ERROR"}
    assert out["error"] == "FakePipelineError"
    assert "muhab-akif" not in out["error"]
    assert "23sep1996" not in out["error"]


def test_server_exception_prints_route_through_sanitize_exception():
    """The 3 exception prints in server.py (_generate_unified_view,
    _generate_merged_view, _generate_reading_background legacy block)
    must wrap the exception in sanitize_exception(e) before stderr.
    Source-level check — stable across pytest isolation modes."""
    import re
    server_path = os.path.join(
        os.path.dirname(__file__), "..", "web_backend", "server.py"
    )
    src = open(server_path).read()

    # Each of these tag prefixes must appear with sanitize_exception(e) in
    # the same f-string, not bare {e}.
    tags = ["[unified_view]", "[merged_view]", "[legacy_reading]"]
    for tag in tags:
        # Find every print line containing the tag
        pattern = re.compile(
            r'print\(f"\[' + re.escape(tag[1:-1]) + r'\][^"]*"',
            re.MULTILINE,
        )
        matches = pattern.findall(src)
        assert matches, f"no print line found for tag {tag}"
        for m in matches:
            assert "sanitize_exception(e)" in m, (
                f"{tag} print must route through sanitize_exception(e): {m!r}"
            )
            # Negative: must not print bare {e} (without sanitize)
            assert "{e}" not in m or "{sanitize_exception(e)}" in m, (
                f"{tag} print still contains bare {{e}}: {m!r}"
            )


def test_p2e_str_e_sites_sanitized():
    """P2F-PR2 §E: server.py:611 (/api/analyze 500), :978 (demo render),
    :1079 (Stripe webhook sig) must not leak str(e). Source-level check."""
    import re as _re
    server_path = os.path.join(
        os.path.dirname(__file__), "..", "web_backend", "server.py"
    )
    src = open(server_path).read()

    # /api/analyze must use class-name pattern
    assert _re.search(
        r'detail=f"analysis_failed:\{type\(e\)\.__name__\}"', src
    ), "/api/analyze 500 still leaks str(e) (P2E E.1)"
    assert "raise HTTPException(500, detail=str(e))" not in src

    # Demo render must use class name
    assert _re.search(
        r'Demo render failed:\s*\{type\(e\)\.__name__\}', src
    ), "demo render still leaks {e} (P2E E.2)"
    assert 'f"Demo render failed: {e}"' not in src

    # Stripe webhook must return constant
    assert "raise HTTPException(400, \"invalid_signature\")" in src, \
        "Stripe webhook still leaks str(e) (P2E E.3)"
    # And not the old form
    assert "raise HTTPException(400, str(e))" not in src


def test_ls_checkout_error_uses_constant():
    """P2F-PR2 §F: LS checkout error must surface only a constant to the
    caller; full provider response stays in stderr only."""
    server_path = os.path.join(
        os.path.dirname(__file__), "..", "web_backend", "server.py"
    )
    src = open(server_path).read()
    assert 'raise HTTPException(500, "checkout_provider_error")' in src, \
        "LS checkout error not using constant (P2F-PR2 §F)"
    # Old leaky form must be gone
    assert 'f"Lemon Squeezy error: {resp.text[:200]}"' not in src


def test_runner_error_fields_use_type_name_not_str():
    """The 3 error-dict assignments in runner.py (semantic_reading,
    psychological_mirror, psychological_profile) must use
    type(e).__name__, not str(e). Source-level check."""
    import re
    runner_path = os.path.join(
        os.path.dirname(__file__), "..", "runner.py"
    )
    src = open(runner_path).read()

    # Each layer's error-dict assignment must use type(e).__name__
    pattern = re.compile(
        r'out\["(semantic_reading|psychological_mirror|psychological_profile)"\]\s*=\s*\{[^}]*\}',
        re.MULTILINE,
    )
    matches = pattern.findall(src)
    # We expect the 3 error-dict assignments (may also match the happy-path
    # assignments — that's fine, the check below only asserts there are no
    # str(e) uses in the *error* dicts).
    err_pattern = re.compile(
        r'out\["(?:semantic_reading|psychological_mirror|psychological_profile)"\]\s*=\s*\{"error":\s*([^,]+),',
        re.MULTILINE,
    )
    err_matches = err_pattern.findall(src)
    assert len(err_matches) == 3, (
        f"expected 3 error-dict assignments, found {len(err_matches)}: {err_matches}"
    )
    for expr in err_matches:
        assert "type(e).__name__" in expr, (
            f"runner.py error field must use type(e).__name__, got: {expr!r}"
        )
        assert "str(e)" not in expr, (
            f"runner.py error field still uses str(e): {expr!r}"
        )
