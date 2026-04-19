# SIRR Privacy Architecture — Four-Tier Data Model

**Spec reference:** `Tools/handoff/DECISIONS_LOCKED.md §16` (internal, not shipped publicly)

This document describes how SIRR structurally separates user data into four tiers, each with different retention, encryption, and access postures. The goal is structural — not procedural — privacy: leaks should require deliberate code changes, not willpower.

---

## Tier 1 — Identity & Payment (third-party)

**Handler:** Lemon Squeezy (merchant of record, PCI-compliant)

SIRR never touches card numbers, billing addresses, or tax IDs. Lemon Squeezy issues a transaction confirmation with an opaque order ID; SIRR stores only that ID plus the customer email (needed to deliver the reading).

**Retention:** Per Lemon Squeezy's own policy — outside SIRR's direct control.

---

## Tier 2 — Reading Input & Output (encrypted, short-lived)

**Handler:** SIRR's own server, on-disk under `Engine/web_backend/orders/` and `Engine/web_backend/readings/`.

Contents:

- Submitted profile (name, DOB, time, place, mother's name)
- Computed engine output (JSON, one per order)
- Rendered reading HTML (legacy + unified view)

**Retention:** 30 days from order creation. Enforced by `Engine/web_backend/retention.py::sweep_tier2_expired()`, which walks the directories and deletes any file whose mtime is older than the cutoff.

**Access model:**

- URL tokens are signed, self-contained, and time-bounded (30 days). See `Engine/web_backend/tokens.py`. Token secret is rotated separately from other credentials (`SIRR_TOKEN_SECRET` env var).
- Reading endpoints (`/r/{token}`, `/r/{token}/unified`) resolve the token to an order ID server-side, never echoing the ID back in URLs.
- Legacy `/reading/{order_id}` routes remain for grandfathered orders but are deprecated. New checkouts mint tokens only.

**Encryption (planned, not yet enforced):**

Per-record envelope encryption using a key derived from `HKDF(master_secret, salt=order_id, info="sirr-tier2-v1")`. At rest, the JSON and HTML files will be AES-256-GCM-encrypted; decryption happens only within the running request that produced or requested them.

**Deletion flow:**

`POST /api/delete` accepts either a signed token or `(order_id, email)` for authentication. On success it unlinks Tier 2 files, truncates the order row to audit metadata only, and queues the `order_id` for Tier 3 removal.

---

## Tier 3 — Aggregate Analytics (planned)

**Handler:** SIRR's own server (not yet implemented as of v1 release).

Contents (design):

- Hashed pseudonym per user: `HMAC(email, salt=tier3_salt)`
- Archetype tags, convergence counts, meta-pattern firings
- Module distribution, element balances, numerical categories
- **Never:** raw names, dates, places, mother's names, or any identifying string

**Access rules:**

- k-anonymity: no query returns a result unless ≥5 users share the pattern
- Differential privacy noise added to all published aggregates
- No join key connects Tier 3 rows back to Tier 2 records

**Deletion flow:**

User-requested deletions append the order_id to `deletion_queue.txt`. `retention.py::drain_tier3_deletion_queue()` drains the queue and removes the pseudonymous row matching the derived hash. Must complete within 30 days of request (§16.6 commitment).

---

## Tier 4 — Operator Vault (local-only)

**Handler:** Founder's local machine. Never cloud-synced.

Contents: founder's own reference data, frozen showcase artifacts, internal docs, pre-launch drafts. Lives entirely in a local encrypted directory with a separate encrypted backup.

**Rule:** Tier 4 never enters any third-party platform. Not ChatGPT, not Grok, not Gemini, not Midjourney. The only thing that may be pasted into external AI for debugging is the synthetic demo profile (Tier 0, public).

---

## Zero-knowledge operator posture (§16.3)

The operator is structurally unable to read individual production readings:

- No admin console that surfaces reading content
- Production database credentials live only in the deployed service
- Support escalations surface as metadata-only (timestamp, error category, order ID) — never content
- To debug a specific reading, the user must re-submit in ephemeral debug mode; there is no standing key to their stored record

This is liability reduction, not just privacy discipline. If the operator cannot read the data, they cannot leak it, be compelled to produce it, or be held responsible for its contents.

---

## What's enforced today vs. what's planned

| Control | Status |
|---|---|
| Signed URL tokens for reading access | Shipped (`tokens.py`) |
| Age gate 18+ at checkout | Shipped |
| Privacy Policy + Terms of Service | Shipped (`/privacy`, `/terms`) |
| Right-to-delete endpoint | Shipped (`POST /api/delete`) |
| Retention purge job (Tier 2) | Shipped as scaffold, awaits cron wire-up |
| Tier 3 deletion queue | Stub (drains no-op until Tier 3 store lands) |
| Log hygiene (no PII in stdout) | Verified |
| No third-party client-side analytics | Verified |
| Per-record Tier 2 encryption at rest | Planned — next 2p iteration |
| Tier 3 aggregate store | Planned — requires DB migration |
| Differential-privacy noise calibration | Planned — requires real traffic |
| Zero-knowledge admin UI | Planned |

---

*Doc version 1.0 — 2026-04-19 — initial publication alongside first 2p release.*
