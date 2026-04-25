# Lane Doctrine v2 — Multi-model orchestration for SIRR

**Effective date:** 2026-04-25 (post-P2F merge)
**Supersedes:** Lane Doctrine v1 (informal, scattered across session journals)

This document codifies how the SIRR work is split between models, which
gates exist between drafting and shipping, and the named anti-patterns
the P2D + P2F sessions surfaced. It is a working doctrine; expect to
amend it once or twice per quarter as new patterns emerge.

---

## Roles

### Orchestrator (Claude in chat — currently web)

Reads the codebase via Desktop Commander. Writes only to
`SIRR_PRIVATE/Orchestration/Briefs/`. Does not commit, does not push,
does not deploy. State verified via tools before every decision —
never inferred from memory.

The orchestrator's job is to compose briefs that are precise enough
that the executor can implement them mechanically, with explicit
gates at each high-risk step. Briefs include: pre-flight checks,
section-by-section diffs, mandatory pre-push verification commands,
post-deploy verification commands, and stop conditions.

### Executor (Claude Code, Opus model)

Implements briefs. Commits, pushes, opens PRs, watches CI, watches
deploys. Does not make architectural choices outside the brief —
when an unspecified design question arises, asks the orchestrator
or surfaces explicitly in the implementation report. Drift into
unilateral design decisions is the v2-named anti-pattern §3.1.

The executor's job is to do exactly what the brief says, surface
discrepancies between brief and reality before acting on them, and
report verbatim. The executor is not a designer; the executor is a
high-trust pair of hands.

### Cross-model auditor (Codex)

Adversarial read-only audit. **Mandatory** gate when the orchestrator
wrote the spec — same-model audit by the spec author is structurally
insufficient (see anti-pattern §3.3). Routed by Muhab (no automated
CLI on the executor's machine; see §6).

Codex reads the diff against main, attacks the PR's claims, and
returns per-claim verdicts (PASS / FINDING / UNCLEAR) with
file:line evidence. Findings are real. The orchestrator's job is to
classify each finding as in-scope (apply now), defer (PR-N+1), or
escalate (architecturally new — see §7).

### Editorial approver (Muhab)

Merge gate. The bright line that no orchestrator and no executor
crosses without explicit approval. Routes Codex audits, signs off
on merge, owns post-deploy operational verification. The merge
gate is sacred — see §5.

---

## Worked example: P2F session (2026-04-19 to 2026-04-25)

The session arc grew to four PRs over six days (PR-1 + PR-2 + PR-3 + PR-4):

**P2F-PR1** (2026-04-25T07:16:47+03:00, commit `538ab8d`):
encrypted tokens + 4 §16.5 surface closures (`/api/order-status/{id}`,
`/success?order_id=`, `success.html` legacy JS, token opacity).
Codex round 1 caught the privacy issue the orchestrator's same-model
review missed: tokens were HMAC-signed but the payload was still
base64-decodable JSON. Without that round, the PR would have shipped
"opaque enough" and customers' name+DOB would still leak via
browser history. Round 1 saved the privacy claim.

**P2F-PR2** (2026-04-25T09:10:46+03:00, commit `7b675a7`):
defensive hardening — Codex Findings 1 and 2 (response-body cleanups),
production startup fail-fast for missing `SIRR_ENCRYPTION_KEY`,
encryption silent-swallow → strict-fail with `status="failed"`,
`_merged.html` added to encryption targets, lazy regen paths
encrypt-after-write, atomic plaintext cleanup on encryption failure,
3 P2E `str(e)` sites + LS body sanitized.

PR-2 ran for **5 Codex rounds**:
- Round 2 caught FIX A (custom `"encryption_failed"` status string
  vs. the `"failed"` that `success.html` recognizes) and FIX B
  (`_merged.html` missing from encryption targets list).
- Round 3 caught FIX C (lazy regen paths bypassing encryption) AND
  flagged that the executor wrapped FIX C in `try/except: pass`
  contrary to the brief's strict-fail prescription. Orchestrator
  caught the wrapper on review; reverted as a separate commit.
- Round 4 surfaced FIX E (encryption failure leaves plaintext on disk
  that token-gated serve helpers will read). Orchestrator openly
  walked back the round-3 bright line ("round 4 defers to PR-3")
  with the named justification "this finding is the same architectural
  class as rounds 2-3, so closing it here is consistent."
- Round 5 confirmed FIX E lands cleanly and identified three residuals
  for PR-3.

**P2D recovery** (2026-04-25T05:40:46+03:00, commit `1384053`):
The `--access-log false` incident. Brief specified `--access-log false`
based on training-data memory; the actual uvicorn flag is
`--no-access-log` (boolean toggle). Container failed to start, prod
was 502 for ~45 minutes, reverted via `git revert d3627e4 → 92b95b4`,
forward-fixed with the correct flag. **The single largest cost in the
arc was avoidable** — see anti-pattern §3.4 ("spec from memory").

**P2F-PR3** (commit `de71a25` squash-merge): operational log scrubs via `hash_oid`,
`_reading.md` unlink-after-use, status-aware serving (defense-in-depth
for FIX E cleanup-failure case), stale doctrine cleanup,
boot-smoke executes `railway.toml` startCommand directly, this doc.

**P2F-PR4** (this PR): customer-facing privacy.html copy accuracy
(storage claim + deletion claim now match doctrine after PR-3's
internal precision exposed both as overclaims), plus this doc's §6
(prescription completeness) and §7 (orchestrator-direct-edit
exception) appended from this session's lessons. PR-4 itself was a
worked example: Codex caught a factual self-contradiction in §7
(round 1) and two stale arc-count references at lines 65 + 108
(round 2-3) — same convergent doctrine-accuracy class, fixed in
fold-in commits.

---

## Bright line discipline

A bright line is a constraint set by the orchestrator before a
risky decision (typical: "I will defer further findings to PR-N+1
rather than queue another fix here"). Bright lines must be:

1. **Stated explicitly** before the relevant decision point — not
   in retrospect.
2. **Pre-equipped with walk-back conditions.** Without conditions,
   a bright line is an arbitrary line and not a real constraint.
   Format: "If the next finding is X-class, defer; if Y-class, escalate."
3. **Walked back openly** when conditions warrant — never quietly
   moved. Quiet movement is drift; explicit movement is judgment.

P2F-PR2 round 4 is the canonical example. The line was "round 3 is
the last patch round on PR-2." When Codex round 4 surfaced FIX E,
the orchestrator walked the line back with the named justification:
"this finding is convergent on the same architectural class as
rounds 2-3 (encryption integrity end-to-end), not a new class —
closing it here is consistent, not new scope." The walk-back was
named, the new line was set ("round 5 is final, in any direction"),
and that line held.

The pathology to prevent is **infinite-fix-loop** (anti-pattern §3.5).
Convergence (each round narrowing toward a single architectural
property) is acceptable; divergence (each round opening a new class)
is the sign that the PR scope is wrong.

---

## Specification rigor

When the orchestrator writes a brief that calls for a CLI flag,
env var, or library API, the orchestrator must verify the exact
name/syntax before writing the spec. The P2D access-log incident
(`--access-log false` instead of `--no-access-log`) cost ~45min
of production downtime because the orchestrator wrote the brief
from training-data memory rather than running `uvicorn --help`.

Verification checklist before writing any brief that names an
external interface:

- [ ] **CLI flag**: `<command> --help | grep <flag>` confirms exact
  spelling, including whether the flag takes a value or is a
  boolean toggle.
- [ ] **Env var**: `printenv | grep <PREFIX>` on the target system
  (production container if the var is auto-set), or the official
  docs page within the last 6 months. Note: some env vars are only
  visible inside the container at runtime, not via `railway run`
  — verify in the right context.
- [ ] **Library API**: import the library at orchestrator's REPL,
  confirm the function signature.
- [ ] **HTTP API shape**: pull a real response from the live endpoint
  (or staging) and read the JSON, don't paraphrase from memory.

The cost of a 30-second `--help` check is always less than the cost
of a failed deploy.

---

## Cross-model audit gate

When the orchestrator writes the spec, the orchestrator's own
self-review is structurally insufficient — same-model bias is real.
P2F-PR1 round 1 demonstrated this: the orchestrator's pre-merge
review judged the encrypted tokens "opaque enough"; Codex
immediately caught that the JSON payload was still client-decodable.
The cross-model audit catches what same-model review misses.

This gate is **mandatory** for any PR closing a privacy claim,
encryption-integrity claim, or other safety property. It is
**recommended** for any PR with non-trivial scope.

Routing in the current SIRR setup: Codex CLI is not installed on
the executor's machine. The orchestrator drafts the audit prompt;
Muhab routes it to Codex from his side; results are pasted back
to the orchestrator. This adds latency (~5-15min per round) but
preserves the cross-model property. Future improvement: install a
Codex CLI on the executor's machine so the round-trip can be
automated (open issue, not blocking).

---

## The merge gate

The squash-merge step is sacred. The orchestrator does not run
`gh pr merge` without explicit approval from Muhab. The executor
does not run `gh pr merge` without explicit approval from
orchestrator + Muhab.

Merging without explicit approval is the worst-case anti-pattern
in v2 because:

1. The post-merge state is the source of truth that production
   deploys from.
2. Reverts are possible but expensive (~7-15 min downtime in the
   P2D case, plus operational anxiety).
3. The act of merging is irreversible in the sense that the
   commit lives in main forever, even after a revert. The history
   shows the cost.

If in doubt, ask. Always.

---

## Anti-patterns (v2-named)

### §3.1 Executor design drift
Executor makes architectural choices that contradict the brief
without flagging. P2F-PR2 FIX C: Claude Code wrapped the encryption
call in soft-fail `try/except` after the brief explicitly chose
strict-fail. Orchestrator caught on review; reverted in round 3
enforcement commit (`aae089b`).

**Mitigation:** explicit pre-merge orchestrator review of every
diff (not just CI green). Source-level inspect tests where possible
(e.g., `test_lazy_regen_paths_encrypt_after_write` in P2F-PR2 asserts
the soft-fail wrapper is absent — regression guard against this exact
mistake recurring).

### §3.2 Quiet bright-line movement
Orchestrator named a bright line, then moved it without
acknowledgment. Not observed in P2F session (the round-4 walk-back
was explicit). Documenting as anti-pattern to prevent.

### §3.3 Same-model audit substituting for cross-model
Orchestrator's self-review of orchestrator's spec passes despite
real architectural gaps. P2F-PR1 token-opacity claim is the
canonical example: the orchestrator wrote "tokens are now opaque"
in the brief and the orchestrator's pre-merge review confirmed it;
Codex round 1 caught the JSON-decodability gap immediately.

**Mitigation:** mandatory cross-model audit gate (§4 above).

### §3.4 Spec from memory rather than verification
P2D access-log incident. See §3 above for the verification checklist
that would have prevented it. The cost was ~45 minutes of production
downtime; the prevention cost was ~30 seconds.

### §3.5 Infinite-fix-loop
Each Codex round surfaces a new finding; orchestrator queues a
new fix; the cycle compounds. P2F-PR2 had 5 rounds — at the upper
edge of acceptable. Bright lines exist to bound this.

**Mitigation:** bright lines with explicit walk-back conditions.
Convergence (same architectural class narrowing) is acceptable;
divergence (each round opening a new class) is the pathology.

---

## When to escalate to Muhab

- Codex finds something architecturally new (different class
  from PR's stated scope)
- Bright line walk-back would be the second walk-back in same PR
- A pre-flight verification fails (env var unset, baseline tests
  not green, etc.)
- Production deploy returns FAILED
- Any operation that requires database mutation outside the
  current PR scope
- A merge approval is requested but the diff has changed since
  the last orchestrator read

---

## Working pattern (steady state)

The arc that has worked: brief → executor implements → executor
runs local mandatory verification (3+ tests) → executor pushes →
CI green → executor pings orchestrator → orchestrator pulls diff
locally and re-reads → orchestrator drafts Codex prompt for Muhab
→ Muhab routes Codex → Codex returns findings → orchestrator
classifies (in-scope / defer / escalate) → if in-scope, executor
applies; if defer, registry update notes the residual; if escalate,
Muhab decides scope → orchestrator approves merge → executor
merges → executor watches deploy with fail-fast → executor runs
post-deploy verification suite → executor reports → orchestrator
final-checks against original brief.

The cycle time per round when everything works: ~20-30 minutes.
When something doesn't work (P2D access-log, P2F-PR2 round 3
soft-fail), expect 60-90 minutes of recovery + cleanup. Build the
cycle for the failure case, not the happy path.

---

## §6 — Prescription completeness

When a brief says "per orchestrator's prescription" or "orchestrator
has the exact text," the paste-block sent to the executor MUST contain
the verbatim text inline. Forcing the executor to scroll up and
reconstruct the prescription from earlier orchestrator messages is
functionally indistinguishable from telling them to derive it
themselves, which §3.1 (executor design drift) forbids.

Worked example: P2F-PR3 round 5, 2026-04-25. Orchestrator drafted the
verbatim text for two doctrine-accuracy fixes in chat, then composed
an executor instruction that referenced the text by saying
"orchestrator has the exact text" without inlining it. Executor
correctly paused and refused to derive doctrine wording independently,
citing §3.1. Round-trip cost: one extra message exchange. Could have
been zero with prescription completeness.

Rule: every executor instruction is self-contained. The executor
should not need any context outside the instruction block to
implement. If the orchestrator catches itself writing
"per orchestrator's prescription" or similar, that's the signal to
inline the text instead.

---

## §7 — Orchestrator-direct-edit exception

The orchestrator's default lane is read-and-brief, never write-to-repo.
There is one exception: explicit Muhab override for late-session,
bounded, doc-only changes where the round-trip cost exceeds the value
of preserving lane separation.

Worked example: P2F-PR3 round 5 commit `aaa6204`, 2026-04-25.
Orchestrator applied two doctrine-accuracy fixes (one bullet
addition + one comment swap) directly via Desktop Commander
git/python heredoc edits after Muhab issued "do it yourself now"
instruction. Conditions met:

- Explicit Muhab override (not orchestrator self-authorization)
- Bounded scope (two doc edits, no code-behavior change, +6/-1 lines)
- Late-session expediency (Muhab racing to field; the round-trip
  cost would have exceeded the value of maintaining lane purity)
- All other gates honored: pytest 213/213, 3 mandatory verification
  checks, CI green. The direct-edit was applied as round 5 of PR-3.
  Codex round 4 (auditing the post-edit branch) returned PASS on
  the four PR-3-internal claims and surfaced one new residual
  (privacy.html customer-copy overclaim) which was routed to PR-4
  per the round-3 bright line, not folded back into PR-3. The
  direct-edit and the residual are independent: the edit closed
  PR-3's internal doctrine, the residual closed customer-facing
  doctrine, and both gates held.

Rule: this exception is for Muhab to invoke, not for the orchestrator
to claim. Orchestrator should always offer to draft the executor
instruction first; only when Muhab explicitly says "do it yourself"
does the exception apply. Default remains read-and-brief.

**Worked example addendum, 2026-04-25 (PR-4 round 1):** orchestrator
caught itself about to direct-edit a §7-class fix to this very
document without explicit Muhab override. Reverted before any
commit, routed the fix through the executor (this paste). The
near-violation reinforces §7's narrow scope: "explicit Muhab
override" means a paste like "do it yourself now," not orchestrator
inferring expediency from session context. When in doubt, route.
