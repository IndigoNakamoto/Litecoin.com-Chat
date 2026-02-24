# Backend Uptime Monitoring (Mac mini)

Foolproof tracking of when the backend server goes down: **local logging** on the Mac mini plus **external monitoring** for alerts even when the whole machine or network is down.

---

## 1. Local downtime log (on the Mac mini)

A script runs every minute, hits `http://localhost:8000/health`, and appends one line to a log file whenever the backend goes **DOWN** or comes back **UP**, with timestamps (and duration when it recovers).

### Install (one-time)

**Option A: Install script (recommended)**

From the project root:

```bash
./scripts/install-backend-uptime-check.sh
```

This copies the launchd plist to `~/Library/LaunchAgents`, replaces `__PROJECT_ROOT__` with your repo path, and loads it.

**Option B: Manual**

1. Copy the plist and replace the project path:

   ```bash
   PROJECT_ROOT="$(pwd)"   # or your actual path, e.g. /Users/you/Projects/Litecoin-Knowledge-Hub
   sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" monitoring/com.litecoin.backend-uptime-check.plist > ~/Library/LaunchAgents/com.litecoin.backend-uptime-check.plist
   ```

2. Load the agent:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.litecoin.backend-uptime-check.plist
   ```

### Log file

- **Path:** `monitoring/backend_downtime.log`
- **Format:** `DOWN	2026-02-14T19:00:00Z	backend health check failed (...)` and `UP	2026-02-14T19:15:00Z	backend healthy again (duration 15m)`
- **Rotation:** Not automatic. For long-lived installs, rotate or truncate the file occasionally, or tail it into your log aggregator.

### Useful commands

```bash
# View recent downtime events
tail -20 monitoring/backend_downtime.log

# Check that the agent is loaded
launchctl list | grep com.litecoin.backend-uptime-check

# Stop monitoring
launchctl unload ~/Library/LaunchAgents/com.litecoin.backend-uptime-check.plist

# Start again
launchctl load ~/Library/LaunchAgents/com.litecoin.backend-uptime-check.plist
```

### Limitation

If the **Mac mini is off or unreachable**, nothing runs, so you get no new log lines. You need **external monitoring** to know the service (or the whole box) is down.

---

## 2. External uptime monitoring (recommended)

Use a **third-party monitor** that hits your **public** backend URL (e.g. `https://api.lite.space/health`) from the internet. If the Mac mini or your network is down, the monitor will see failure and can alert you.

### Suggested services (free tiers)

| Service         | Free tier        | What it does                          |
|-----------------|------------------|----------------------------------------|
| **UptimeRobot** | 50 monitors, 5m  | HTTP(S) check, email/Slack alerts      |
| **Better Stack**| 10 monitors      | HTTP check, status page, alerts        |
| **Healthchecks.io** | Unlimited | Cron-style; backend can push heartbeat |

### Setup (e.g. UptimeRobot)

1. Sign up at [uptimerobot.com](https://uptimerobot.com).
2. Add a monitor:
   - **Monitor type:** HTTP(s)
   - **URL:** `https://api.lite.space/health` (or your public backend URL)
   - **Interval:** 5 minutes
   - **Alert contacts:** your email (and optionally Slack/Discord webhook).
3. Save. You’ll get an email when the check fails and when it recovers.

### Optional: heartbeat from the backend

For “backend process died but Mac and network are up”, you can have the backend **push** a heartbeat to [Healthchecks.io](https://healthchecks.io):

- Create a check (e.g. “Litecoin backend”).
- From the backend or a cron on the Mac mini, hit the Healthchecks.io ping URL every minute.
- If the ping stops, Healthchecks.io marks the check as down and can notify you.

This complements the **pull** check (UptimeRobot hitting your public URL), which catches “whole machine or network down”.

---

## Summary

| Layer              | What it catches                         | How |
|--------------------|-----------------------------------------|-----|
| **Local log**      | When backend was down/up (timestamps)   | Script every 60s → `monitoring/backend_downtime.log` |
| **External monitor** | Service (or Mac/network) unreachable | UptimeRobot etc. hitting `https://api.lite.space/health` |

Use both: external monitor for **alerting**, local log for **downtime duration and history** after the fact.
