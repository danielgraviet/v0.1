# Local Demo Runbook (Mock Incident + Alpha Backend + Frontend)

This runbook is for running the full demo on one machine:
- Mock incident app (your fake repo)
- Alpha SRE backend (webhook listener + analysis)
- Frontend UI
- ngrok tunnel for Sentry webhooks

---

## Architecture (local)

- Mock incident app: `http://127.0.0.1:8001`
- Alpha backend: `http://127.0.0.1:8000`
- Sentry webhook endpoint: `https://<ngrok-domain>/webhooks/sentry` (tunnels to `:8000`)
- Frontend should read from Alpha backend endpoints:
  - `GET /executions/latest`
  - `GET /executions/{execution_id}`

Important: tunnel `8000`, not `8001`.

---

## Terminal Setup

## Terminal A — Alpha backend (webhook + CLI orchestration)

```bash
cd /Users/danielgraviet/Desktop/projects/v0.1
make run-cli
```

This mode listens for Sentry webhooks and renders live agent orchestration in terminal.

## Terminal B — ngrok tunnel to Alpha backend

```bash
ngrok http 8000
```

Copy the HTTPS URL and configure Sentry webhook:

```text
https://<ngrok-domain>/webhooks/sentry
```

## Terminal C — Mock incident app

```bash
cd /Users/danielgraviet/Desktop/projects/sre_demo_repo
make run
```

This app runs on `:8001`. Trigger your spike/error scenario from here.

## Terminal D — Frontend

Run your frontend as usual. Ensure API base URL points to:

```text
http://127.0.0.1:8000
```

---

## Alpha `.env` Recommendations

At minimum:

```env
OPENROUTER_API_KEY=...
SENTRY_AUTH_TOKEN=...          # needed for live Sentry enrichment
SENTRY_CLIENT_SECRET=...       # recommended for signature verification
ALPHA_WEBHOOK_DEDUP_SECONDS=60 # dedupe burst webhooks for same issue
```

Optional CORS for local frontend ports:

```env
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

---

## Pre-Demo Smoke Checks

Run from Alpha repo:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/executions/latest
```

Expected:
- `/health` returns `{"status":"ok"}`
- `/executions/latest` may return 404 until first webhook arrives

---

## Demo Flow

1. Trigger failing requests in mock app (`:8001`)
2. Sentry sends webhook to ngrok URL
3. Alpha (`make run-cli`) shows live agent execution in terminal
4. Frontend polls Alpha and displays latest execution result

---

## Troubleshooting

- Seeing only green `POST /webhooks/sentry` lines and no CLI panels:
  - You likely started `make run` instead of `make run-cli`.

- Sentry events arrive but no analysis:
  - Check `alpha_sre.log` for parse/signature errors.

- Repeated reruns for same issue:
  - Increase `ALPHA_WEBHOOK_DEDUP_SECONDS` (e.g. `60` to `180`).

- Frontend not updating:
  - Verify frontend API base URL is `http://127.0.0.1:8000`.
  - Verify it uses `/executions/latest` or `/executions/{id}`.
