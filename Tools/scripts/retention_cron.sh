#!/usr/bin/env bash
# SIRR — Retention cron trigger
# -----------------------------------------------------------------------------
# Invoked by Railway's scheduled-job service (or any external cron) to fire the
# nightly retention purge against the live server.
#
# Required env vars (set on the cron service in Railway):
#   SIRR_INTERNAL_SECRET   — must match the web service's value
#   SIRR_PURGE_URL         — default: https://web-production-ec2871.up.railway.app/api/internal/purge
#
# Exit codes:
#   0 — purge succeeded (HTTP 200, JSON body logged)
#   1 — auth failed (401) or endpoint disabled (503) — env mismatch
#   2 — network error or unexpected HTTP status
#   3 — missing SIRR_INTERNAL_SECRET
# -----------------------------------------------------------------------------
set -euo pipefail

PURGE_URL="${SIRR_PURGE_URL:-https://web-production-ec2871.up.railway.app/api/internal/purge}"

if [[ -z "${SIRR_INTERNAL_SECRET:-}" ]]; then
  echo "[retention-cron] FATAL: SIRR_INTERNAL_SECRET not set on this service" >&2
  exit 3
fi

echo "[retention-cron] $(date -u +%Y-%m-%dT%H:%M:%SZ) firing purge against $PURGE_URL"

response_file="$(mktemp)"
http_code=$(curl -s -o "$response_file" -w '%{http_code}' \
  -X POST "$PURGE_URL" \
  -H "X-Internal-Secret: $SIRR_INTERNAL_SECRET" \
  -H "Content-Type: application/json" \
  --max-time 60)

body=$(cat "$response_file")
rm -f "$response_file"

case "$http_code" in
  200)
    echo "[retention-cron] OK $body"
    exit 0
    ;;
  401)
    echo "[retention-cron] AUTH FAIL — SIRR_INTERNAL_SECRET mismatch between cron service and web service" >&2
    exit 1
    ;;
  503)
    echo "[retention-cron] ENDPOINT DISABLED — web service reports no SIRR_INTERNAL_SECRET set" >&2
    exit 1
    ;;
  *)
    echo "[retention-cron] UNEXPECTED HTTP $http_code body=$body" >&2
    exit 2
    ;;
esac
