# SIRR Master Registry

This file is the source-of-truth summary for SIRR's privacy doctrine state, the closures that have shipped, and the items that are explicitly deferred. It is updated each time a doctrine-affecting PR merges.

---

## §16.5 doctrine state — post-P2F closure (2026-04-25)

**Headline (honest scope):** name+DOB does not appear in any URL, response body, server runtime log line, or `_reading.md` plaintext intermediate. Tier 2 reading artifacts (output JSON, legacy `.html`, `_unified.html`, `_merged.html`) are AES-256-GCM encrypted at rest with atomic plaintext cleanup on encryption failure. Token URLs are opaque ciphertext.

**Two known plaintext surfaces remain — explicitly deferred to P2G (not closed by P2F):**

- `Engine/web_backend/order_store.py:36` — `create_order()` writes the order row (containing `name_latin`, `name_arabic`, `dob`, `birth_time`, `birth_location`) as plaintext JSON to `ORDERS_DIR/<order_id>.json`. This is the source-of-record for the order metadata; the encryption work in P2F-PR2 only covered the reading artifacts (`_output.json`, `.html`, `_unified.html`, `_merged.html`), not this row.
- `Engine/web_backend/order_store.py:52` — `get_order()` reads the same plaintext row at request time. The /api/r/{token}/status path therefore touches a plaintext disk file on every poll.
- Related deletion gap at `Engine/web_backend/server.py:869`: `POST /api/delete` truncates the order row's PII fields via `update_order(profile=None, email_hash=None, ...)`, but the original plaintext bytes may persist in filesystem unallocated space until overwritten — and the row file itself is NOT unlinked, only re-written with PII fields nulled.

The P2G arc will introduce per-order encryption for the `order_store` rows (likely re-using `crypto.encrypt_bytes` with `context=order_id`, mirroring the Tier 2 pattern). Until then, the runtime threat model assumes filesystem confidentiality of `/data/orders/`.

### Closures by phase

**P2D (narrow §16.5 closure, 2026-04-19 — through 2026-04-25 recovery arc):**
- `/reading/{order_id}`, `/reading/{order_id}/unified`, `/reading/{order_id}/merged` → 410 Gone (commit `070f931`)
- `_resolve_token_or_order_id` grandfather removed — raw order_ids no longer accepted on `/r/` (commit `070f931`)
- 6 `sanitize_exception()` sites in `server.py` (commit `070f931`)
- 3 `runner.py` error fields use `type(e).__name__` instead of `str(e)` (commit `070f931`)
- uvicorn `--no-access-log` flag (Procfile + railway.toml + CI guard step) — fixed forward after the `--access-log false` access-log incident (commits `92b95b4` revert + `1384053` correction)

**P2F-PR1 (broader §16.5 closure — token opacity + 4 surfaces, 2026-04-25 commit `538ab8d`):**
- Tokens AES-256-GCM AEAD-encrypted via `crypto.encrypt_bytes` with context `"sirr-token-v1"` (replaces HMAC-signed-payload format; payload is now opaque ciphertext to anyone without the master key)
- `/api/order-status/{order_id}` → 410 Gone; legacy logic moved to `_serve_order_status_by_id` reachable only via `/api/r/{token}/status`
- `/success?order_id=...` → 410 Gone (legacy query branch removed)
- `success.html` legacy JS code path entirely removed (no more raw `/api/order-status/{id}` or `/reading/{id}` URL construction)

**P2F-PR2 (defensive hardening + Codex Findings 1, 2 + encryption-integrity end-to-end, 2026-04-25 commit `7b675a7`):**
- `reading_url` field removed from `/api/r/{token}/status` response (Codex Finding 1)
- `order_id` field removed from `/api/checkout` response (Codex Finding 2; outbound payment-provider payloads still carry it server-to-server, intentional)
- Encryption silent-swallow → strict-fail with `update_order(status="failed", error="encryption_failed:<ExcClass>")` so `success.html`'s status-check fires correctly (FIX A)
- `_merged.html` added to `_encrypt_tier2_outputs` targets list (FIX B)
- Lazy regen paths (`_serve_reading_unified_by_id`, `_serve_reading_merged_by_id`) encrypt-after-write, strict-fail (FIX C, with round-3 enforcement)
- Atomic plaintext cleanup on encryption failure — any non-encrypted target file is `.unlink()`ed before the re-raise (FIX E)
- Production startup hard-fails on missing `SIRR_ENCRYPTION_KEY` when `RAILWAY_DEPLOYMENT_ID` is set
- 3 P2E `str(e)` sites (server.py:611 `/api/analyze`, :978 demo render, :1079 Stripe webhook sig) sanitized
- LemonSqueezy provider-controlled error body replaced with constant
- `SIRR_TOKEN_SECRET` deprecation INFO log on startup if env var still set

**P2F-PR3 (operational logs + status-aware serving + doctrine cleanup, 2026-04-25):**
- `hash_oid` helper in `sanitize.py` — non-reversible 12-char SHA-256 prefix for log correlation IDs
- Log scrubs at all known sites that interpolated raw `order_id`:
  - `Engine/web_backend/server.py` × 5 (`[tier2-encrypt]`, `[unified_view]`, `[merged_view]`, `[legacy_reading]`, plus the inner caller's `[tier2-encrypt]` log)
  - `Engine/web_backend/retention.py` × 6 (expire-order, expire-order-failed, expire-reading, expire-reading-failed, tier3-delete-queued — also strips raw filenames since they embed `order_id`)
  - `Engine/html_reading.py` × 1 (Saved-reading log)
  - `Engine/reading_generator.py` × 2 (drops `context['subject']` from generation logs entirely; operational signal preserved without the PII tail)
- `_reading.md` plaintext intermediate now unlinked after `generate_html_reading` consumes it (closes the Tier 2 plaintext residue gap that wasn't in any encryption target list)
- Status-aware serving in `_serve_tier2_html` — refuses plaintext for `status="failed"` orders (defense-in-depth for the case where FIX E's best-effort cleanup itself fails)
- Stale HMAC-token doctrine references updated to AEAD reality (`server.py` × 3 sites, `PRIVACY_TIERS.md`, `privacy.html`, `bootstrap_railway_env.sh`)
- `boot-smoke` CI step now executes `railway.toml`'s `startCommand` directly (deepest fix to the access-log-incident class — string-presence regex is no longer the only guard)
- `LANE_DOCTRINE_v2.md` codifies the multi-model lessons from this arc
- `Docs/audits/AUDIT_2026-04-24.md` superseded header

### Known plaintext surfaces NOT closed by P2F (deferred to P2G)

- **`Engine/web_backend/order_store.py:36`** (`create_order`) — order rows containing `name_latin` + `name_arabic` + `dob` + `birth_time` + `birth_location` are written as plaintext JSON to `ORDERS_DIR/<order_id>.json`. P2F-PR2's encryption-at-rest covered the reading artifacts but not the order-row file.
- **`Engine/web_backend/order_store.py:52`** (`get_order`) — reads the same plaintext row at request time. Every `/api/r/{token}/status` poll touches this file.
- **`Engine/web_backend/server.py:869`** (deletion gap) — `POST /api/delete` truncates the order row's PII fields via `update_order(profile=None, ...)`, but the file itself is NOT unlinked, only re-written with PII fields nulled. Filesystem unallocated-space carve-back is not performed; on a shared volume this leaves the original plaintext bytes recoverable until overwritten.
- **`hash_oid` truncation length** (`Engine/web_backend/sanitize.py`) — 12-char SHA-256 prefix gives ~48 bits of preimage resistance. Acceptable for the current threat model (operational log correlation, single-tenant log surface) but documented here for revisitation when the customer base grows past ~10⁵ active orders or the log surface gets multi-tenant.

### Other known deferred items

- **Stripe / LS payment metadata still carries raw `order_id`** in their internal dashboards (third-party log surface, not our control). Documented in commit messages; not a runtime leak on our side.
- **Migration race window during PR-1 deploy**: pre-existing HMAC tokens became invalid the moment the new code went live. Mitigated by minting fresh tokens for the active customer (Muhab's test order) immediately after deploy. Not a concern for new orders post-deploy.
- **`SIRR_TOKEN_SECRET` env var on Railway**: still set, now obsolete since P2F-PR1. Harmless; deprecation INFO log surfaces on every container restart. Bootstrap script no longer generates it (P2F-PR3 round 2). Will be removed from Railway at Muhab's discretion once the recommendation has been seen enough times.

### Doctrine sources of truth

- This file (registry): claims summary, deferral list
- `Docs/architecture/PRIVACY_TIERS.md`: tier definitions and rationale
- `Docs/operations/LANE_DOCTRINE_v2.md`: how multi-model work is gated and verified
- Brief archive: `SIRR_PRIVATE/Orchestration/Briefs/P2{D,F}_*.md`
- Audit history (superseded): `Docs/audits/AUDIT_2026-04-24.md`
