# Retention Cron Service — Railway Setup

**Purpose:** A second Railway service that fires `/api/internal/purge` nightly, enforcing the §16.2 30-day retention on Tier 2 reading files.

**Why a second service:** Railway's `cronSchedule` replaces a service's long-lived run mode with scheduled invocation. The `web` service must stay long-lived, so the cron lives in its own service that shares the same repo.

## One-time setup (5 clicks in Railway dashboard)

### 1. Add a new service

Railway dashboard → project `magnificent-friendship` → **+ New** (top right) → **GitHub Repo** → pick `appleeatsapples-lang/SIRR` → name it **`retention-cron`**.

### 2. Settings → Source

- Repository: `appleeatsapples-lang/SIRR`
- Branch: `main`
- Root Directory: blank
- Watch Paths: `Tools/scripts/retention_cron.sh` (optional — redeploys only on script change)

### 3. Settings → Deploy

- **Custom Build Command:** leave blank
- **Custom Start Command:** `bash Tools/scripts/retention_cron.sh`
- **Cron Schedule:** `0 3 * * *`  *(every day at 03:00 UTC — off-peak)*
- **Healthcheck:** disable (no HTTP served)
- **Restart Policy:** `never`

### 4. Variables

Only one needed:

- `SIRR_INTERNAL_SECRET` = *same value as the web service*

**Best option:** use **Variable Reference** instead of copy-paste. Click **+ New Variable → Add Reference → pick service `web` → pick variable `SIRR_INTERNAL_SECRET`**. When you rotate the secret on `web`, the cron service auto-inherits.

Optional override:

- `SIRR_PURGE_URL` = `https://web-production-ec2871.up.railway.app/api/internal/purge` (only set if the Railway subdomain changes)

### 5. Deploy

Click **Deploy**. The service will pull the repo and then wait for the cron trigger (`0 3 * * *` UTC). At that time it runs the script and exits.

## Verification

### Manual trigger to confirm wiring

Railway dashboard → `retention-cron` service → Deployments → latest → **⋯ → Redeploy**. Check logs:

```
[retention-cron] 2026-04-19T...Z firing purge against https://web-production-ec2871.up.railway.app/api/internal/purge
[retention-cron] OK {"orders_removed":0,"readings_removed":0,"tier3_processed":0,...}
```

`AUTH FAIL` means the `SIRR_INTERNAL_SECRET` on the cron doesn't match the web service. Fix by Variable Reference.

### Web service logs during cron runs

```
[retention] sweep-tier2 orders_removed=N readings_removed=N cutoff_days=30
[retention] drain-tier3 processed=N deferred=0
```

## Rollback

Disable cron temporarily: set **Cron Schedule** to blank, or delete the service. Web service unaffected.

## Future enhancements

- **Alerting:** Railway emails deploy failures by default. For Slack/Discord, use integrations or pipe script through a webhook.
- **Dry-run in prod:** set `SIRR_RETENTION_DRY_RUN=true` on the **web** service (NOT cron). Purge logs what it would delete, doesn't actually delete. Useful for first runs with real data.
- **Split cadence:** `retention.py` exposes `sweep_tier2_expired()` and `drain_tier3_deletion_queue()` as separate callables if Tier 2 and Tier 3 need different schedules later.

---

*Written 2026-04-19 alongside the retention_cron.sh script ship.*
