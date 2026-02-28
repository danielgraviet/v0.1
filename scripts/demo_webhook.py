"""Send a local demo webhook and poll until execution completes."""

import json
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 1.0


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"Content-Type": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def main() -> int:
    payload = {
        "action": "created",
        "actor": {"name": "alpha-demo-org"},
        "data": {
            "issue": {
                "id": "4500000001",
                "project": {"slug": "alpha-demo-project"},
            }
        },
    }

    try:
        print("Posting demo webhook to /webhooks/sentry ...")
        created = _request("POST", "/webhooks/sentry", payload)
    except urllib.error.URLError as exc:
        print(f"Failed to reach API at {BASE_URL}: {exc}", file=sys.stderr)
        print("Start it first with: make run", file=sys.stderr)
        return 1

    execution_id = created.get("execution_id")
    if not execution_id:
        print(f"Unexpected webhook response: {created}", file=sys.stderr)
        return 1

    print(f"Execution created: {execution_id}")
    print("Polling for completion ...")

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        record = _request("GET", f"/executions/{execution_id}")
        status = record.get("status")
        print(f"  status={status}")

        if status in {"complete", "failed"}:
            print("\nFinal execution record:")
            print(json.dumps(record, indent=2))
            return 0 if status == "complete" else 2

        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"Timed out after {TIMEOUT_SECONDS}s waiting for completion.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
