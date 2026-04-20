# Railway Persistent Volume Setup

**Problem this solves:** Railway's Nixpacks containers have an ephemeral filesystem by default. Every deploy starts with a clean disk. Without a persistent volume attached, any customer orders + rendered readings written to local paths get **wiped on the next deploy**.

This is invisible during pre-launch testing (no real orders). The moment Lemon Squeezy delivers a real customer's reading, the next code push would delete it.

## Fix — 6 clicks in the Railway dashboard

### 1. Open the web service
Railway → `magnificent-friendship` project → click the `web` service tile.

### 2. Volumes tab
Top tabs: Deployments · Variables · Metrics · **Settings** · … — actually volumes live under the service view. Look for a **Volumes** tab or section (newer Railway UIs have it alongside Variables).

If no Volumes tab is visible: Settings → scroll to **Volumes** section.

### 3. Create a volume
Click **+ New Volume** (or **Attach Volume**).

- **Name:** `sirr-data`
- **Mount path:** `/data`
- **Size:** 1 GB is plenty to start (Railway Trial allows up to 5 GB). Can scale later.

Click **Create** / **Attach**.

### 4. Tell the app to use the volume

Variables tab → add:

```
SIRR_DATA_DIR=/data
```

That's the env var the `paths.py` module reads. With it set, all order rows, reading HTMLs, and the deletion queue land in `/data` — which is the volume mount. Without it, the app falls back to writing next to the code (ephemeral behavior preserved for dev/CI).

### 5. Redeploy
Railway redeploys automatically when you add an env var. Watch the deploy log for the healthcheck to pass (~2-3 min).

### 6. Verify persistence

After redeploy, hit the admin dashboard:

```
https://web-production-ec2871.up.railway.app/admin
```

Click **Run retention purge**. Response should show `orders_removed=0 readings_removed=0` — same as before, but now that purge is touching the persistent volume, not the container's ephemeral disk.

Then push an unrelated commit (e.g., a README typo fix) to main. Railway will redeploy. Hit the admin again — counts should still be `0`, confirming the volume survived the deploy. Once you have real orders, this verification becomes "orders counter stays the same across deploys" instead of "stays 0."

## What's in the volume

```
/data/
├── orders/              ← per-order JSON rows + engine output JSONs
│   └── {order_id}.json
│   └── {order_id}_output.json
├── readings/            ← rendered HTML readings
│   └── {order_id}.html
│   └── {order_id}_unified.html
└── deletion_queue.txt   ← right-to-delete queue file
```

Tier 2 encryption (PR #2) encrypts files individually before writing — so the volume holds ciphertext, not plaintext. The master key lives in `SIRR_ENCRYPTION_KEY` (Railway env, separate from the volume). An attacker with access to only one of (volume, env vars) can decrypt nothing.

## Backup story

Railway volumes don't have automatic snapshots. For real customer data, use one of:

1. **Railway CLI**: `railway run tar -czf /tmp/backup.tgz /data` to a workstation
2. **Scheduled export service**: second Railway service that periodically uploads `/data` to S3/R2
3. **Operator-triggered dump**: a future `/api/internal/export` endpoint (not yet built)

For pre-launch / first-customer era, option 1 is fine. Once you have a handful of paying customers, automate option 2.

## Reverting (if this goes wrong)

Unset `SIRR_DATA_DIR` in Railway Variables. The app reverts to the legacy ephemeral behavior. The volume still exists (detach via dashboard) — no data loss.

## Local dev & CI

Both ignore `SIRR_DATA_DIR`. Local runs write to `Engine/web_backend/orders/` and `readings/` as before. CI doesn't set the variable. Only production Railway uses `/data`.

---

*Shipped 2026-04-20 in PR fixing the ephemeral-filesystem issue.*
