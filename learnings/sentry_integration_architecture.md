# Sentry Integration Architecture

## The two layers

**Layer 1 — Trigger**

Sentry is already in the client's stack doing its normal job (catching errors, alerting their team). You're just adding a webhook so you *also* get notified when something goes wrong. The client doesn't change anything about how they use Sentry.

```
Client's app crashes
    → Sentry catches it (as normal)
    → Sentry alerts the client's team (as normal)
    → Sentry also POSTs to your webhook  ← the only thing you add
```

**Layer 2 — Enrichment + Analysis**

Once you receive that trigger, you do the work Sentry *can't* do — correlate the error with everything else that changed around the same time.

```
Webhook fires
    → Pull full error context from Sentry  (what broke, stack traces)
    → Pull recent commits from GitHub      (what changed before the break)
    → Pull deployment info                 (when was it deployed, which version)
    → Run Alpha SRE pipeline               (why did it break, ranked hypotheses)
    → Return actionable insight            (here's the root cause + confidence)
```

## What the client actually gets

Without Alpha SRE, when their app crashes the engineer has to manually:
1. Look at Sentry for the error
2. Go to GitHub to find recent commits
3. Check deployment logs
4. Form a hypothesis about the cause
5. Test it

That's 20–40 minutes of manual correlation. Alpha SRE compresses that into seconds by doing all of it automatically and returning a ranked answer: *"DB connection pool was reduced from 20→5 in commit e4f5g6h, 94% confidence."*

## Division of labor across sources

| Source | What it tells you |
|---|---|
| Sentry | *What* is broken — stack traces, error rate, affected users |
| GitHub | *What changed* — commits, diffs, config at deploy SHA |
| Vercel (future) | *When* it deployed and what the build looked like |

Sentry is the trigger. GitHub is the "why it might have changed" context. The Alpha SRE pipeline is the thing that connects them.

## Important distinction

Sentry is specifically an **error and performance monitoring tool** — it doesn't know about deploys unless the client explicitly sends release information to it. The deployment context (which commit, which config changed) comes from **GitHub**, not Sentry.

So when you say "Sentry receives analytics about their deployment" — be precise: Sentry receives *error events*. Deployment context is GitHub's job.
