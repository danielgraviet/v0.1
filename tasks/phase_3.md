# Phase 3 — Deterministic Signal Layer

**Goal:** Extract objective facts from incident data before any AI reasoning. This is what separates Alpha from an "LLM wrapper" — and what gives it technical credibility.

---

## Learning Objectives

By the end of this phase, you should be able to:

- [ ] Explain why deterministic signal extraction happens before LLM reasoning, and why this matters
- [ ] Write a log anomaly detector that computes error rate spikes without an LLM
- [ ] Write a metrics analyzer that detects latency spikes, saturation events, and cache degradation
- [ ] Write a commit diff extractor that identifies high-risk code changes from structured commit data
- [ ] Output structured `Signal` objects (not raw text or freeform dicts) from each analyzer
- [ ] Explain the "facts vs interpretations" separation in your own words

---

## Core Concepts

### 1. Why Deterministic First?

LLMs hallucinate. If an agent reads raw logs and generates hypotheses freely, it will occasionally invent signals that don't exist — or miss real ones. This destroys trust in the output.

Alpha's defense is an architectural separation:

```
Raw data → [Deterministic analyzers] → Signals → [LLM agents] → Hypotheses
```

- **Analyzers** extract what is objectively true. No LLM. Reproducible.
- **Agents** interpret what signals mean. LLM. Probabilistic.

The result: agents can only reason about facts that were verified by deterministic code. If a hypothesis doesn't reference a real signal, the judge rejects it.

This is the claim from `runtime_outline.md`:
> Alpha is not "LLM wrapper." It is a deterministic OS for probabilistic workers.

The signal layer is the proof.

### 2. What Is a Signal?

A signal is a structured, objective observation extracted from incident data. It is not an interpretation.

```python
Signal(
    id="sig_001",
    type="log_anomaly",
    description="Error rate increased 3.1x from baseline",
    value=3.1,
    severity="high",
    source="log_analyzer"
)
```

Signals are:
- **Computed from data** — not invented
- **Reproducible** — same input always produces the same output
- **Typed** — the schema tells you exactly what `value` means
- **Referenced by ID** — hypotheses cite `"sig_001"`, not a vague description

### 3. The Four Analyzers

Each analyzer processes one slice of the incident payload:

| Analyzer | Input Field | Signal Types Produced |
|---|---|---|
| `LogAnalyzer` | `incident.logs` | Error rate spike, new error signature, dominant error type |
| `MetricsAnalyzer` | `incident.metrics` | Latency spike, DB saturation, cache hit rate drop |
| `CommitAnalyzer` | `incident.recent_commits` | Cache decorator removed, unindexed query added, pool config changed |
| `ConfigAnalyzer` | `incident.config_snapshot` | Limit reduced, feature flag changed |

These are not agents. They do not call an LLM. They run pure Python logic.

### 4. Simulated Data Strategy

For the hackathon, you are not integrating with Datadog, Prometheus, or any real observability tool. You simulate a realistic incident payload as a JSON fixture.

The fixture represents **Incident B** (locked in Phase 0):
- A deploy that removes a `@cache` decorator
- An unindexed SQL query introduced
- DB connection pool reduced from 20 to 5
- Resulting in: 4x latency spike, 3x error rate increase, cache miss cascade

Good fixture design produces clear, unambiguous signals. The analyzers should find them reliably.

---

## Module Structure to Build

```
alpha/
  signals/
    log_analyzer.py         ← LogAnalyzer
    metrics_analyzer.py     ← MetricsAnalyzer
    commit_analyzer.py      ← CommitAnalyzer
    config_analyzer.py      ← ConfigAnalyzer (optional for hackathon)
    signal_extractor.py     ← Orchestrates all analyzers

fixtures/
  incident_b.json           ← Simulated incident payload
  incident_b_baseline.json  ← "Normal" state (optional, for comparison)
```

---

## Implementation Checklist

### Step 1 — Incident Fixture (build this first — analyzers have nothing to run without it)

- [ ] Create `fixtures/incident_b.json` with the following structure:

```json
{
  "deployment_id": "deploy-2024-11-15-v2.3.1",
  "logs": [
    "INFO  GET /api/users 200 45ms",
    "ERROR GET /api/users 500 timeout after 5000ms",
    "ERROR GET /api/users 500 timeout after 5000ms",
    "ERROR DB connection pool exhausted",
    ...
  ],
  "metrics": {
    "latency_p50_ms": 280,
    "latency_p99_ms": 4800,
    "latency_baseline_p99_ms": 120,
    "error_rate": 0.31,
    "error_rate_baseline": 0.01,
    "db_query_time_ms": 2400,
    "db_connection_pool_used": 5,
    "db_connection_pool_max": 5,
    "cache_hit_rate": 0.08,
    "cache_hit_rate_baseline": 0.82
  },
  "recent_commits": [
    {
      "sha": "a1b2c3d",
      "message": "Remove cache from user profile endpoint",
      "diff_summary": "Removed @cache decorator from get_user_profile(). Added SELECT * FROM users JOIN orders query without index."
    },
    {
      "sha": "e4f5g6h",
      "message": "Reduce DB pool for cost optimization",
      "diff_summary": "Changed MAX_DB_CONNECTIONS from 20 to 5 in config.py"
    }
  ],
  "config_snapshot": {
    "MAX_DB_CONNECTIONS": 5,
    "CACHE_TTL_SECONDS": 0,
    "FEATURE_FLAGS": {
      "new_query_engine": true
    }
  }
}
```

- [ ] Include at least 50 log lines — mix of normal INFO logs and ERROR/timeout logs
- [ ] Baseline values must be present so analyzers have something to compare against

### Step 2 — Log Analyzer

- [ ] Implement `LogAnalyzer` in `signals/log_analyzer.py`
  - Method: `analyze(logs: list[str]) -> list[Signal]`
  - **Error rate spike detection:** Count `ERROR` lines vs total lines. If rate > 2x baseline (or > 10% of logs), emit a signal.
  - **Dominant error type:** Find the most frequent error message prefix. Emit a signal with the error type.
  - **New error signatures:** Compare error messages in last 80% of logs vs first 20%. New patterns are signals.
  - Return: `list[Signal]`

Example output signal:
```python
Signal(
    id="sig_001",
    type="log_anomaly",
    description="Error rate is 31% — 3.1x above baseline of 1%",
    value=3.1,
    severity="high",
    source="log_analyzer"
)
```

### Step 3 — Metrics Analyzer

- [ ] Implement `MetricsAnalyzer` in `signals/metrics_analyzer.py`
  - Method: `analyze(metrics: dict) -> list[Signal]`
  - **Latency spike:** If `latency_p99_ms > latency_baseline_p99_ms * 2`, emit signal with ratio as value
  - **DB saturation:** If `db_connection_pool_used / db_connection_pool_max >= 0.9`, emit signal with saturation % as value
  - **Cache miss:** If `cache_hit_rate < 0.5` (or drops > 50% from baseline), emit signal
  - Return: `list[Signal]`

Example output signals:
```python
Signal(id="sig_002", type="metric_spike", description="p99 latency: 4800ms vs baseline 120ms (40x spike)", value=40.0, severity="high", source="metrics_analyzer")
Signal(id="sig_003", type="resource_saturation", description="DB connection pool 100% saturated (5/5 used)", value=1.0, severity="high", source="metrics_analyzer")
Signal(id="sig_004", type="metric_degradation", description="Cache hit rate dropped from 82% to 8%", value=0.08, severity="high", source="metrics_analyzer")
```

### Step 4 — Commit Analyzer

- [ ] Implement `CommitAnalyzer` in `signals/commit_analyzer.py`
  - Method: `analyze(commits: list[dict]) -> list[Signal]`
  - **Cache removal detection:** Scan `diff_summary` for patterns like "removed @cache", "cache decorator", "cache=False"
  - **Unindexed query detection:** Scan for "SELECT *", "JOIN" without "INDEX", or SQL without WHERE clause hints
  - **Pool config change:** Scan for "MAX_DB_CONNECTIONS", "pool_size", "MAX_CONNECTIONS" reductions
  - Return: `list[Signal]`

Example output signals:
```python
Signal(id="sig_005", type="commit_change", description="Cache decorator removed from user profile endpoint (commit a1b2c3d)", value=None, severity="medium", source="commit_analyzer")
Signal(id="sig_006", type="commit_change", description="Potentially unindexed query added in commit a1b2c3d", value=None, severity="medium", source="commit_analyzer")
Signal(id="sig_007", type="commit_change", description="DB connection pool reduced from 20 to 5 in commit e4f5g6h", value=None, severity="high", source="commit_analyzer")
```

### Step 5 — Config Analyzer (optional for hackathon)

- [ ] Implement `ConfigAnalyzer` in `signals/config_analyzer.py`
  - Method: `analyze(config: dict, baseline_config: dict | None) -> list[Signal]`
  - Flag numeric limits that decreased (e.g., `MAX_DB_CONNECTIONS` went from 20 to 5)
  - Flag feature flags that changed to `true` (new code paths enabled)
  - If no baseline provided, flag anything that looks like a reduced limit

### Step 6 — Signal Extractor (Orchestrator)

- [ ] Implement `SignalExtractor` in `signals/signal_extractor.py`
  - Method: `extract(incident: IncidentInput) -> list[Signal]`
  - Instantiate and run all four analyzers
  - Assign sequential IDs to all signals: `sig_001`, `sig_002`, ... (ID assignment happens here, not in individual analyzers)
  - Return the combined signal list

```python
class SignalExtractor:
    def extract(self, incident: IncidentInput) -> list[Signal]:
        raw_signals = []
        raw_signals += LogAnalyzer().analyze(incident.logs)
        raw_signals += MetricsAnalyzer().analyze(incident.metrics)
        raw_signals += CommitAnalyzer().analyze(incident.recent_commits)
        # Assign IDs after collecting all
        for i, signal in enumerate(raw_signals, start=1):
            signal.id = f"sig_{i:03d}"
        return raw_signals
```

### Step 7 — Runtime Integration

- [ ] Update `AlphaRuntime.execute()` to call `SignalExtractor` before dispatching agents
  - Replace the placeholder from Phase 2 with a real `SignalExtractor().extract(payload)` call
  - Write extracted signals to `StructuredMemory`
  - `AgentContext` receives `memory.get_signals()` — **not the raw incident data**

---

## Expected Signal Output on `incident_b.json`

After running `SignalExtractor` on the fixture, you should have at least these signals:

| ID | Type | Description | Severity |
|---|---|---|---|
| sig_001 | log_anomaly | Error rate 3.1x above baseline | high |
| sig_002 | metric_spike | p99 latency 40x above baseline | high |
| sig_003 | resource_saturation | DB connection pool 100% saturated | high |
| sig_004 | metric_degradation | Cache hit rate dropped 90% | high |
| sig_005 | commit_change | Cache decorator removed | medium |
| sig_006 | commit_change | Unindexed query added | medium |
| sig_007 | commit_change | DB pool reduced from 20 to 5 | high |

7 signals minimum. Agents will cite these IDs in their hypotheses.

---

## Success Criteria

- [ ] `fixtures/incident_b.json` exists with realistic data (50+ log lines, baseline metrics, 2+ commits)
- [ ] `SignalExtractor.extract()` returns at least 6 signals from the fixture
- [ ] Each signal has: unique ID, type, description, severity, source
- [ ] Log anomaly signal emitted when error rate > 2x baseline
- [ ] Latency spike signal emitted when p99 > 2x baseline
- [ ] DB saturation signal emitted when pool usage >= 90%
- [ ] Cache miss signal emitted when hit rate < 50% of baseline
- [ ] Cache removal commit is detected as a signal
- [ ] Pool size reduction commit is detected as a signal
- [ ] `AlphaRuntime.execute()` calls `SignalExtractor` and agents receive signals (not raw data)
- [ ] All signal IDs are unique within a single extraction run

---

## Open Questions

1. **Baseline data:** How do analyzers know what "normal" looks like? Options:
   - Hardcode baseline values in the fixture (simplest, recommended for hackathon)
   - Derive from the first N% of the log array
   - Accept a separate `baseline` object in the incident payload
2. **Commit format:** Are commits represented as full diffs or summarized strings? What fields are required?
3. **Analyzer failures:** If `LogAnalyzer` raises an exception, should the runtime continue with partial signals or abort? (Recommendation: continue with partial signals, log the error)
4. **Signal IDs:** Sequential strings (`sig_001`) or UUIDs? Sequential is more readable in demo output.
5. **Config baseline:** Does the config analyzer need a baseline to compare against, or can it work from heuristics alone?

---

## Hackathon Priority

**Essential — build first:**
- [ ] `fixtures/incident_b.json` (all other work depends on this)
- [ ] `LogAnalyzer` (error rate spike, dominant error type)
- [ ] `MetricsAnalyzer` (latency spike, DB saturation, cache hit rate)
- [ ] `CommitAnalyzer` (cache removal, unindexed query, pool reduction)
- [ ] `SignalExtractor` orchestrator
- [ ] Runtime integration (agents receive signals, not raw data)

**Important — build second:**
- [ ] `ConfigAnalyzer`
- [ ] Baseline derivation from log data (vs hardcoded)

**Optional — skip if time-pressured:**
- [ ] Multi-incident fixture
- [ ] Signal deduplication
- [ ] Analyzer unit tests
