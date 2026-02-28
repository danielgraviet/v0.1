# Frontend Integration — Engineering Notes

## The core architectural problem

Right now the pipeline looks like this:

```
Sentry → POST /webhooks/sentry → analysis runs → result returned to Sentry
```

The result goes **back to Sentry** as the HTTP response, not to a frontend. The frontend
has no way to receive it. Before any frontend work starts, we need to decide how results
get from the runtime to the UI.

---

## Challenge 1 — Result delivery

Three options, each with tradeoffs:

| Option | How it works | Best for |
|---|---|---|
| **Polling** | Frontend hits `GET /signals/latest/` every few seconds | Simple, good enough for demo |
| **SSE (Server-Sent Events)** | Frontend subscribes once, server pushes updates | Live feel, one-way, easy to implement |
| **WebSockets** | Bidirectional connection, server pushes as agents complete | Best UX, most complex |

For the hackathon, **polling or SSE** is the right call. WebSockets are overkill unless
we're building the live agent panel from the Phase 2 spec.

---

## Challenge 2 — Result persistence

Right now results exist for the duration of the webhook call and then disappear. If the
frontend loads after the analysis completes, there's nothing to show.

We need a store. Options in order of complexity:

```
In-memory dict     → fast, lost on restart, fine for demo
SQLite             → persists across restarts, zero infrastructure
Redis              → production-ready, requires a running Redis instance
```

For the hackathon, an in-memory dict keyed by `execution_id` is fine.

---

## Challenge 3 — CORS

The frontend is on a different origin (e.g. `localhost:3000`). FastAPI will block those
requests by default. One middleware addition fixes it, but it needs to be done before the
frontend developer writes a single API call.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Challenge 4 — The async gap

The webhook handler currently runs the full pipeline inside the request and returns when
it's done. That's fine for Sentry (which just needs a 200), but it means:

- Sentry waits ~3–10 seconds for LLM calls to finish before getting its 200
- Sentry has a webhook timeout — if the pipeline is slow, Sentry will retry and flood the queue

The fix is to kick off analysis as a **background task** and return 200 to Sentry immediately:

```
POST /webhooks/sentry
  → validate signature
  → parse payload
  → start background task  ← analysis runs here, after response is sent
  → return 200 immediately to Sentry

background task:
  → fetch enrichment
  → run runtime
  → save result to store
  → frontend can now poll or receive push
```

FastAPI has built-in `BackgroundTasks` support — this is a small change to `main.py`.

---

## What needs to be built before frontend work starts

Three things the frontend developer needs on day one:

| What | Why |
|---|---|
| `GET /results/{execution_id}` | Fetch a specific analysis result by ID |
| `GET /results/latest` | Fetch the most recent result (useful for demo) |
| CORS middleware | Without this, every frontend API call will be blocked |
| Background task refactor | So Sentry gets its 200 instantly, not after LLM calls finish |

---

## What the result payload looks like

This is what the frontend receives today (with 0 agents — will have hypotheses once
Phase 4 agents are wired in):

```json
{
  "execution_id": "b95397c7-086f-41e4-a606-b3e33f069af4",
  "requires_human_review": true,
  "hypotheses": [
    {
      "label": "DB Connection Pool Exhaustion",
      "description": "Pool reduced from 20 to 5 in recent commit",
      "confidence": 0.91,
      "severity": "high",
      "supporting_signals": ["sig_003", "sig_007"],
      "contributing_agent": "metrics_agent, commit_agent"
    }
  ]
}
```

The `requires_human_review` flag is important for the UI — when `true`, the frontend
should not present the result as a definitive answer.

---

## Questions to resolve in the meeting

1. **Which result delivery method?** Polling is simplest for the demo. SSE gives a better
   live feel if the frontend can handle it.
2. **What does the frontend actually display?** The ranked hypothesis list, confidence
   scores, contributing agents, and the human review flag.
3. **How does the frontend know a new result is available?** Either it polls on an interval,
   or we push a notification when analysis completes.
4. **Authentication?** For the demo, open endpoints are fine. For anything beyond the
   hackathon, the frontend needs to authenticate before reading results.
