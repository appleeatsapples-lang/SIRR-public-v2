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
    hash_oid,
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


def test_encryption_failure_marks_order_failed_with_prefix():
    """P2F-PR2 FIX A: when Tier 2 encryption fails, _encrypt_tier2_outputs
    must downgrade the order to status='failed' (not a custom string like
    'encryption_failed') so success.html's failed-status branch fires.
    The error field carries an 'encryption_failed:' prefix so ops can
    distinguish encryption failures from engine failures."""
    import inspect
    from server import _encrypt_tier2_outputs
    src = inspect.getsource(_encrypt_tier2_outputs)
    # Must use status="failed" (the string success.html recognizes)
    assert 'status="failed"' in src, \
        "encryption failure must set status='failed' (FIX A)"
    # Must NOT use the rejected custom status string
    assert 'status="encryption_failed"' not in src, \
        "encryption failure still uses custom status string success.html ignores"
    # Must carry the error prefix for operational distinction
    assert '"encryption_failed:"' in src, \
        "error field missing encryption_failed: prefix (FIX A)"
    # And include the exception class name (not the full message)
    assert 'type(enc_err).__name__' in src, \
        "error field must use exception class name only (no str(e) leaks)"


def test_lazy_regen_paths_encrypt_after_write():
    """P2F-PR2 FIX C: lazy regen paths must invoke _encrypt_tier2_outputs
    after writing, otherwise plaintext sits unencrypted indefinitely.
    Strict-fail: NO try/except: pass wrapper around the call (Codex
    round 3 confirmation).

    Two surfaces are affected:
      - _serve_reading_unified_by_id: regenerates when file is missing
        (legacy orders pre-unified-view).
      - _serve_reading_merged_by_id: regenerates when file is missing
        OR when merged_view.py mtime is newer than the cached HTML
        (PR #20's F7.3 cache invalidation). The mtime path means EVERY
        code-update served-after-deploy re-wrote plaintext under the
        old code.
    """
    import inspect
    import re as _re
    from server import _serve_reading_unified_by_id, _serve_reading_merged_by_id

    unified_src = inspect.getsource(_serve_reading_unified_by_id)
    merged_src = inspect.getsource(_serve_reading_merged_by_id)

    # Positive: the call must be present in both helpers
    assert "_encrypt_tier2_outputs(order_id)" in unified_src, \
        "unified lazy regen missing post-regen encryption (FIX C)"
    assert "_encrypt_tier2_outputs(order_id)" in merged_src, \
        "merged lazy regen missing post-regen encryption (FIX C)"

    # Negative: the call must NOT be wrapped in try/except: pass.
    # Strict-fail per Codex round 3 — encryption errors propagate as
    # 500 so we never serve a reading we couldn't seal.
    swallow_pattern = _re.compile(
        r"try:\s*\n\s*_encrypt_tier2_outputs\(order_id\)\s*\n\s*except[^\n]*:\s*\n\s*pass",
        _re.MULTILINE,
    )
    assert not swallow_pattern.search(unified_src), \
        "unified lazy regen wraps _encrypt_tier2_outputs in try/except: pass (must strict-fail per Codex round 3)"
    assert not swallow_pattern.search(merged_src), \
        "merged lazy regen wraps _encrypt_tier2_outputs in try/except: pass (must strict-fail per Codex round 3)"


def test_encryption_failure_cleans_up_plaintext():
    """P2F-PR2 FIX E (Codex round 4): on encryption failure,
    _encrypt_tier2_outputs must delete any remaining plaintext target
    files. Without this, token-gated serve helpers would later return
    the leftover plaintext via _serve_tier2_html's FileResponse
    fallthrough — FIX A's status update is informational; the on-disk
    state is what serve helpers actually check.

    Source-level inspect over the except block:
      1. is_encrypted(...) check appears (so we don't delete encrypted
         orphans by mistake)
      2. .unlink() appears (the actual delete)
      3. Cleanup comes AFTER the status update (ordering matters —
         status must be set even if cleanup fails)
    """
    import inspect
    from server import _encrypt_tier2_outputs
    src = inspect.getsource(_encrypt_tier2_outputs)

    # Locate the start of the except block
    except_idx = src.find("except Exception as enc_err:")
    assert except_idx >= 0, "could not locate except block in _encrypt_tier2_outputs"
    except_body = src[except_idx:]

    # 1. is_encrypted check (so already-encrypted orphans are left alone)
    assert "is_encrypted(" in except_body, \
        "FIX E: cleanup loop missing is_encrypted() guard"
    # 2. unlink call (the actual delete)
    assert ".unlink()" in except_body, \
        "FIX E: cleanup loop missing .unlink() call"

    # 3. Ordering: the status update must occur BEFORE the cleanup loop.
    #    If cleanup blows up before the update, the customer's poll
    #    sees stale "ready" and the serve still has plaintext to read.
    status_update_idx = except_body.find('status="failed"')
    unlink_idx = except_body.find(".unlink()")
    assert status_update_idx >= 0, "FIX E: status update missing in except block"
    assert unlink_idx >= 0
    assert status_update_idx < unlink_idx, \
        "FIX E: cleanup must come AFTER status update (ordering matters)"


def test_encryption_targets_include_merged_html():
    """P2F-PR2 FIX B: _encrypt_tier2_outputs must encrypt the canonical
    customer-facing merged view (_merged.html). Without this, the
    primary post-checkout reading surface lives unencrypted on disk."""
    import inspect
    from server import _encrypt_tier2_outputs
    src = inspect.getsource(_encrypt_tier2_outputs)
    # All four expected targets — by suffix-string presence in the source
    expected_suffixes = [
        '_output.json',
        '.html',
        '_unified.html',
        '_merged.html',
    ]
    for suffix in expected_suffixes:
        assert suffix in src, \
            f"_encrypt_tier2_outputs targets list missing {suffix} (FIX B)"
    # Stronger assertion: the merged.html line must explicitly appear in
    # the targets list literal (not just elsewhere in the function body)
    assert 'f"{order_id}_merged.html"' in src, \
        "_merged.html target literal not in targets list (FIX B)"


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


# ── P2F-PR3 §A: hash_oid helper ──────────────────────────────────────────


def test_hash_oid_stable_and_short():
    """Same input → same 12-char hex; different inputs → different."""
    a = hash_oid("muhab-akif-23sep1996-9376")
    b = hash_oid("muhab-akif-23sep1996-9376")
    c = hash_oid("other-order-id-1234")
    assert a == b
    assert a != c
    assert len(a) == 12
    assert all(ch in "0123456789abcdef" for ch in a)
    # Empty / None handling
    assert hash_oid("") == "<empty>"


def test_hash_oid_does_not_leak_order_id():
    """Hash must not contain any plaintext fragment of the order_id.
    This is the entire reason hash_oid exists: log lines downstream
    must not allow a name+DOB substring to be recovered by grep."""
    oid = "muhab-akif-23sep1996-9376"
    h = hash_oid(oid)
    for fragment in ["muhab", "akif", "1996", "9376"]:
        assert fragment not in h, f"hash leaks {fragment}"


# ── P2F-PR3 §B: log scrubs at named sites ────────────────────────────────


def test_named_log_sites_scrub_order_id():
    """P2F-PR3 §B: named log sites must hash order_id rather than
    interpolate it raw. Scans each named file for the bad pattern and
    confirms hash_oid() is used at the appropriate sites.

    This test is intentionally pattern-based (not line-anchored) so it
    survives line-number drift after future edits."""
    import re as _re
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    targets = [
        ("Engine/web_backend/server.py", 5),       # 5 known log sites (P2D + P2F)
        ("Engine/web_backend/retention.py", 5),    # 4 sweep log lines + tier3 queue
        ("Engine/html_reading.py", 0),             # uses inlined hashlib (cross-import gap)
    ]
    for rel, expected_min_uses in targets:
        path = os.path.join(repo_root, rel)
        with open(path) as f:
            content = f.read()
        # The bad pattern: print/log calls that interpolate {order_id} raw
        bad_pattern = _re.compile(
            r'(?:print|_log)\([^)]*\{order_id\}[^)]*\)',
        )
        bad_matches = bad_pattern.findall(content)
        assert not bad_matches, \
            f"{rel} still has raw {{order_id}} log interpolations: {bad_matches}"
        # And hash_oid usage should appear at least the expected number of times
        # (we count helper-call sites in log lines, not just any reference)
        hash_uses = len(_re.findall(r'hash_oid\(', content))
        assert hash_uses >= expected_min_uses, (
            f"{rel} expected ≥{expected_min_uses} hash_oid() uses, "
            f"found {hash_uses}"
        )


def test_reading_generator_drops_subject_from_logs():
    """P2F-PR3 §B.1: reading_generator.py logs must not interpolate
    context['subject'] (the user's name)."""
    import re as _re
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    with open(os.path.join(repo_root, "Engine/reading_generator.py")) as f:
        content = f.read()
    # The bad pattern: log lines interpolating context['subject']
    bad = _re.findall(r'print\([^)]*context\[.subject.\][^)]*\)', content)
    assert not bad, f"reading_generator.py still logs context['subject']: {bad}"


# ── P2F-PR3 §C: _reading.md unlink-after-use ─────────────────────────────


def test_reading_md_cleanup_in_finally():
    """P2F-PR3 §C (round 2): _reading.md cleanup must be in a finally
    block wrapped around generate_html_reading, so the unlink runs even
    if generate_html_reading raises. A bare unlink-after-call would
    leak plaintext on the exceptional path; round-1 was that pattern,
    Codex round 1 caught it."""
    import inspect
    import server
    src = inspect.getsource(server._generate_reading_background)
    # The write and the unlink must both still be present
    assert "_reading.md" in src
    assert "reading_md_path" in src
    # generate_html_reading must be inside a try block whose finally
    # contains the unlink. We check by ordering: try → generate_html
    # → finally → unlink, all in the same window.
    try_idx = src.find("try:\n                generate_html_reading(output_path, reading_md_path")
    if try_idx < 0:
        # Allow whitespace flexibility
        import re as _re
        m = _re.search(
            r"try:\s*\n\s+generate_html_reading\(output_path, reading_md_path",
            src,
        )
        try_idx = m.start() if m else -1
    assert try_idx >= 0, \
        "generate_html_reading must be wrapped in `try:` (P2F-PR3 §C round 2)"
    finally_idx = src.find("finally:", try_idx)
    unlink_idx = src.find("Path(reading_md_path).unlink", try_idx)
    assert finally_idx > try_idx, \
        "missing `finally:` after the try wrapping generate_html_reading"
    assert unlink_idx > finally_idx, \
        "unlink must be inside the finally block (Codex round 1 finding)"


# ── P2F-PR3 §D: status-aware serving ─────────────────────────────────────


def test_serve_tier2_html_refuses_failed_orders_on_plaintext():
    """P2F-PR3 §D: when encryption failed AND cleanup also failed, a
    plaintext file may survive alongside status='failed'. _serve_tier2_html
    must refuse to serve plaintext for failed orders. Encrypted content
    paths are unaffected (always safe at rest)."""
    import inspect
    import server
    src = inspect.getsource(server._serve_tier2_html)
    # The status check must be present
    status_check_pattern_dq = 'order.get("status") == "failed"'
    status_check_pattern_sq = "order.get('status') == 'failed'"
    assert (status_check_pattern_dq in src or status_check_pattern_sq in src), \
        "_serve_tier2_html missing status='failed' refusal (P2F-PR3 §D)"
    # And it must come AFTER the is_encrypted branch (encrypted serves
    # bypass the status check; only plaintext fallthrough is gated).
    # Compare positions of the actual code patterns, NOT bare "failed"
    # which would also match the docstring explanation above the function
    # body.
    is_enc_idx = src.find("if is_encrypted(raw):")
    check_idx = src.find(status_check_pattern_dq)
    if check_idx < 0:
        check_idx = src.find(status_check_pattern_sq)
    assert is_enc_idx > 0 and check_idx > is_enc_idx, \
        "status check must come AFTER is_encrypted branch in code body"
