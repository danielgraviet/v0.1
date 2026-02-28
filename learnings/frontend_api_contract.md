# Frontend API Contract

## Base URL

```
http://localhost:8000        (local dev)
https://your-domain.com     (production)
```

Interactive docs (explore without writing code): `http://localhost:8000/docs`

---

## How the system works

Sentry fires a webhook when an error occurs. Alpha SRE accepts it instantly
and runs analysis in the background. The frontend polls for results.

```
Sentry error detected
    → POST /webhooks/sentry
    → returns { execution_id, status: "pending" } immediately
    → analysis runs in background (3–10 seconds)

Frontend polls GET /executions/latest
    → status: "pending"  → keep polling
    → status: "complete" → render results
    → status: "failed"   → show error
```

---

## Endpoints

### `GET /executions/latest`

Returns the most recent execution. Poll this every 3–5 seconds after a
Sentry alert is expected.

**Response:**
```json
{
  "execution_id": "b95397c7-086f-41e4-a606-b3e33f069af4",
  "status": "complete",
  "sentry_issue_id": "7299453182",
  "deployment_id": "65069a85fff47694e92aa78e78cb180743f7981e",
  "requires_human_review": false,
  "hypotheses": [
    {
      "label": "DB Connection Pool Exhaustion",
      "description": "Pool reduced from 20 to 5 in recent commit",
      "confidence": 0.91,
      "severity": "high",
      "supporting_signals": ["sig_003", "sig_007"],
      "contributing_agent": "metrics_agent, commit_agent"
    }
  ],
  "signals": [
    {
      "id": "sig_001",
      "type": "log_anomaly",
      "description": "Error rate 3.1x above baseline",
      "value": 3.1,
      "severity": "high",
      "source": "log_analyzer"
    }
  ],
  "error": null,
  "created_at": "2026-02-28T13:41:08+00:00"
}
```

Returns `404` if no executions have run yet.

---

### `GET /executions/{execution_id}`

Returns a specific execution by ID. Use this if you stored the `execution_id`
from an earlier request and want to fetch that exact result.

**Example:** `GET /executions/b95397c7-086f-41e4-a606-b3e33f069af4`

Returns `404` if the ID is not found.

---

### `GET /health`

Liveness check. Returns `{ "status": "ok" }`. Use this to verify the server
is running before making other calls.

---

## Status field

The `status` field tells the frontend what to render:

| status | Meaning | What to show |
|---|---|---|
| `"pending"` | Analysis is running | Loading spinner |
| `"complete"` | Results are ready | Hypotheses + signals |
| `"failed"` | Analysis threw an error | `error` field message |

---

## Polling pattern (JavaScript example)

```js
async function pollForResult(intervalMs = 3000) {
  while (true) {
    const res = await fetch("http://localhost:8000/executions/latest");

    if (res.status === 404) {
      // No executions yet — keep waiting
      await sleep(intervalMs);
      continue;
    }

    const data = await res.json();

    if (data.status === "complete") return data;
    if (data.status === "failed") throw new Error(data.error);

    // Still pending — wait and try again
    await sleep(intervalMs);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

---

## Key fields to render

| Field | What it means |
|---|---|
| `hypotheses[].label` | Short name for the root cause |
| `hypotheses[].description` | Full explanation |
| `hypotheses[].confidence` | 0.0–1.0 — how confident the system is |
| `hypotheses[].severity` | `"low"` / `"medium"` / `"high"` |
| `hypotheses[].contributing_agent` | Which agents identified this |
| `requires_human_review` | `true` = do not act on this automatically |
| `signals` | The raw facts the hypotheses are based on |

---

## CORS

CORS is configured. The default allowed origin is `http://localhost:3000`.

To allow a different origin, set this in the backend `.env`:
```
ALLOWED_ORIGINS=https://your-frontend.com
```

Multiple origins (comma-separated):
```
ALLOWED_ORIGINS=http://localhost:3000,https://your-frontend.com
```

---

## Notes

- Results are held **in memory** — they are lost if the server restarts.
  This is fine for the demo. A database layer comes post-hackathon.
- The `execution_id` in the response is a UUID generated at webhook receipt,
  not the same as the Sentry issue ID.
- `sentry_issue_id` is the original Sentry issue number if you need to link back.
