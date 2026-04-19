"""Traceback and error-string sanitization (§16.5 log hygiene).

Engine code may raise exceptions with user input embedded in the message
(e.g., ValueError(f"invalid name: {name}")). When those exceptions are
caught and stored on the order row via `update_order(error=...)`, the
raw traceback string leaks PII into the database.

This module provides a conservative sanitizer that keeps traceback
structure (file paths, line numbers, function names, exception class)
while redacting anything that looks like user-supplied content.

Philosophy: over-redact rather than under-redact. If we can't cheaply
prove a substring is safe, we hide it. False positives just mean fewer
clues for debugging; false negatives mean a privacy leak.
"""
from __future__ import annotations

import re
import traceback as _tb_mod
from typing import Optional

# Strings we recognize as clearly NON-PII and want to preserve verbatim.
# Exception class names, common Python built-ins, module paths, and
# engine-internal tokens go here.
_SAFE_TOKENS = frozenset(
    {
        "None",
        "True",
        "False",
        "self",
        "cls",
        "args",
        "kwargs",
    }
)

# Redact quoted string literals longer than 2 chars, BUT exempt strings
# containing path separators (those are filepaths — useful for debugging).
_QUOTED_STRING = re.compile(r"""(['"])([^'"\\/]{3,}?)\1""")

# Redact numeric-heavy sequences that look like DOB, phone, or Unicode
# strings with Arabic/CJK content (names in non-Latin scripts).
_LONG_DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
_NON_ASCII_BURST = re.compile(r"[^\x00-\x7f]{3,}")

# Redact email-like tokens.
_EMAIL_LIKE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Redact ISO-8601 date fragments (YYYY-MM-DD).
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def sanitize_line(line: str) -> str:
    """Redact likely-PII fragments from a single line of text."""
    if not line:
        return line
    # Order matters: redact specific patterns before the general quoted one,
    # so the "<redacted-email>" etc. labels survive.
    s = _EMAIL_LIKE.sub("<redacted-email>", line)
    s = _ISO_DATE.sub("<redacted-date>", s)
    s = _NON_ASCII_BURST.sub("<redacted-nonascii>", s)
    s = _LONG_DIGIT_SEQ.sub("<redacted-digits>", s)
    s = _QUOTED_STRING.sub(r"\1<redacted>\1", s)
    return s


def sanitize_traceback(tb_text: str, max_chars: int = 500) -> str:
    """Return a sanitized, length-capped version of a traceback string.

    - Strips any line looking like it carries a quoted user-input fragment.
    - Redacts email addresses, date strings, long digit sequences, and
      non-ASCII bursts (likely names in Arabic / other scripts).
    - Keeps the last N characters (default 500) so the tail — which is
      usually the most recent / relevant frame and the exception class —
      is what's preserved when truncation happens.
    - If empty/None is passed, returns empty string.
    """
    if not tb_text:
        return ""
    cleaned_lines = [sanitize_line(line) for line in tb_text.splitlines()]
    cleaned = "\n".join(cleaned_lines)
    if len(cleaned) > max_chars:
        cleaned = "...[truncated]..." + cleaned[-max_chars:]
    return cleaned


def sanitize_exception(exc: BaseException, max_chars: int = 500) -> str:
    """Format and sanitize an exception for storage.

    Strategy: preserve traceback frames (file paths + line numbers + function
    names — all debug-useful, no PII risk) but REPLACE the exception's message
    entirely with just the class name. The message often embeds user input
    that the regex-based line sanitizer can miss when it's unquoted.
    """
    if exc is None:
        return ""
    try:
        frames = "".join(_tb_mod.format_tb(exc.__traceback__))
        # Deliberately drop str(exc); keep only the class name so no message
        # content from the exception value is stored.
        final_line = f"{type(exc).__name__}: <message-redacted>"
        raw = frames + final_line
    except Exception:
        return f"{type(exc).__name__}: <sanitizer-failed>"
    return sanitize_traceback(raw, max_chars=max_chars)


def sanitize_exc_now(max_chars: int = 500) -> str:
    """Sanitize the CURRENT exception (called from inside `except` block).

    Unlike sanitize_exception, this uses format_exc() so it captures what
    Python's traceback module would produce at this stack point. The message
    line is NOT aggressively stripped here — callers in legacy code paths
    may rely on seeing the message tail. For new code, prefer
    sanitize_exception(exc) which drops the message entirely.
    """
    return sanitize_traceback(_tb_mod.format_exc(), max_chars=max_chars)
