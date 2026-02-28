# Phase 4 — What's Left

## Done

| Component | Status |
|---|---|
| `utils/parse.py` — LLM JSON parser | ✅ |
| `sre/agents/log_agent.py` — Claude, log_anomaly signals | ✅ |
| `sre/agents/metrics_agent.py` — Gemini, metric signals | ✅ |
| `sre/agents/commit_agent.py` — Claude, commit_change signals | ✅ |
| `sre/agents/config_agent.py` — Gemini, config_change signals | ✅ |
| `sre/prompts/*.txt` — system prompts for all 4 agents | ✅ |
| CLI wired to real agents | ✅ |

---

## Remaining: Synthesis Agent

The Synthesis Agent is the final step. It runs **after** the 4 parallel agents finish and the aggregator ranks hypotheses.

**What it does:** reads all signals + the ranked hypothesis list and writes a plain English incident summary. Think of it as a senior SRE writing the executive summary after reviewing the investigation.

**Why it matters for the demo:** right now the output is a table of ranked hypotheses. The synthesis turns that into a human-readable explanation — much more impressive to show.

### 1. Add `SynthesisResult` to `schemas/result.py`

```python
class SynthesisResult(BaseModel):
    summary: str                    # 2-3 sentence plain English explanation
    key_finding: str                # single most likely root cause
    confidence_in_ranking: float    # how certain is the synthesis (0.0–1.0)
```

### 2. Build `sre/agents/synthesis_agent.py`

- Model: `anthropic/claude-sonnet-4-6`
- Input: all signals + the already-ranked hypotheses list
- Output: `SynthesisResult`
- Does NOT generate new hypotheses — only explains the existing ranking
- Write the prompt in `sre/prompts/synthesis_agent.txt`

### 3. Wire into `core/runtime.py`

Run synthesis **after** aggregation (step 6), not in the parallel group:

```python
# After aggregation
synthesis = await SynthesisAgent(llm=...).synthesize(signals, ranked_hypotheses)
```

Attach `SynthesisResult` to `ExecutionResult` so the CLI and API can display it.

### 4. Display in CLI

Add a synthesis panel below the ranked hypothesis table:

```
─── Synthesis ───────────────────────────────────────
Key finding: DB pool reduced to 5 + cache removal caused immediate saturation.

Summary: A deploy that reduced the DB connection pool and removed query
caching combined to saturate the database under normal load. The resulting
slow queries cascaded into request timeouts across the API layer.

Confidence in ranking: 91%
```

---

## Order to build

1. `SynthesisResult` schema — 5 min
2. `synthesis_agent.py` + prompt — 20 min
3. Runtime integration — 10 min
4. CLI display — 10 min
