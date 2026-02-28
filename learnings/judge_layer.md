# Judge Layer

How Alpha validates agent output before it reaches the aggregator, and why
the judge is designed to be deterministic-only.

---

## What It Is

The `JudgeLayer` sits between the executor and the aggregator. Every
`AgentResult` passes through it before any hypothesis is ranked. Its job is
to answer one question:

> "Is this result trustworthy enough to aggregate?"

If the answer is no, the result is excluded. The pipeline continues with
whatever valid results remain.

```
ParallelExecutor
    │
    ├─ AgentResult (log_agent)    ──► JudgeLayer ──► valid   ──► Aggregator
    ├─ AgentResult (metrics_agent)──► JudgeLayer ──► valid   ──► Aggregator
    ├─ AgentResult (commit_agent) ──► JudgeLayer ──► invalid ──► logged, skipped
    └─ AgentResult (config_agent) ──► JudgeLayer ──► valid   ──► Aggregator
```

---

## Why Deterministic-Only — No LLM

The judge never calls an LLM. Every check produces the same result given the
same inputs, every time.

**Why this matters:**

If the judge used an LLM to evaluate agent output, you would have
non-determinism validating non-determinism. When a hypothesis gets rejected,
you would need to reason about:
- Did the agent produce bad output?
- Or did the judge LLM have a bad day?

Deterministic checks eliminate that ambiguity entirely. A rejection always
has a specific, reproducible reason that a developer can read and act on.

| Approach | Reproducible? | Debuggable? | Fast? |
|---|---|---|---|
| Deterministic checks | Always | Yes — exact reason | Yes |
| LLM judge | No | Hard — probabilistic | No |

---

## The Four Checks

Checks run in order. The **first failure short-circuits** — no point checking
signal IDs if the agent name is already empty.

### Check 1 — `agent_name` is non-empty

```python
if not result.agent_name or not result.agent_name.strip():
    return JudgedResult(valid=False, ...)
```

An empty name means the result cannot be attributed to any agent. The
aggregator's `contributing_agent` field would be blank, the display layer
would have an unlabelled panel, and debugging would become impossible.

`result.agent_name.strip()` catches whitespace-only strings like `"  "` that
pass the truthiness check but are still meaningless.

---

### Check 2 — Every hypothesis cites at least one signal

```python
for hypothesis in result.hypotheses:
    if not hypothesis.supporting_signals:
        return JudgedResult(valid=False, ...)
```

A hypothesis with no `supporting_signals` is pure invention — it is not
grounded in any verified fact from the incident. This is the core
facts-vs-interpretations rule enforced at the gate:

> Hypotheses must be interpretations of signals. Not hallucinations.

Note: a result with **zero hypotheses** is valid. An agent that found no
relevant signals in its domain is a legitimate outcome.

---

### Check 3 — Every cited signal ID exists in memory

```python
valid_signal_ids = memory.signal_ids()
for hypothesis in result.hypotheses:
    for signal_id in hypothesis.supporting_signals:
        if signal_id not in valid_signal_ids:
            return JudgedResult(valid=False, ...)
```

An agent might cite a signal ID that was never extracted — either through
hallucination or a bug. This check cross-references every cited ID against
`StructuredMemory.signal_ids()`.

`memory.signal_ids()` returns a `set`, making each lookup O(1). This check
is called once per cited signal ID across all hypotheses, so efficiency matters.

**The rejection message includes valid IDs:**
```
Hypothesis 'DB Exhaustion' cites unknown signal ID 'sig_999'.
Valid IDs: ['sig_001', 'sig_002']
```

This makes debugging a misbehaving agent fast — you can see exactly what
was available and what the agent cited instead.

---

### Check 4 — Confidence is between 0.0 and 1.0

```python
for hypothesis in result.hypotheses:
    if not 0.0 <= hypothesis.confidence <= 1.0:
        return JudgedResult(valid=False, ...)
```

This check should **never fire in practice**. Pydantic's `@field_validator`
on `Hypothesis.confidence` already rejects invalid values at instantiation
time — a `Hypothesis` with `confidence=1.5` cannot exist.

It is included as **defense-in-depth**: if a result is ever constructed in
an unusual way that bypasses normal Pydantic instantiation (e.g. direct
`model_construct()` calls), the judge catches it before the aggregator's
math is corrupted.

**Defense-in-depth** means: validate at multiple layers. Each layer assumes
the previous one might have failed.

---

## `JudgedResult` — A Dataclass, Not a Pydantic Model

```python
@dataclass
class JudgedResult:
    valid: bool
    result: AgentResult
    rejection_reason: str | None = None
```

`JudgedResult` is a dataclass because it is an internal pipeline object:
- It is never serialized to JSON
- It never crosses a system boundary
- It is created by the judge and consumed by the aggregator in the same
  `execute()` call, then discarded

Using Pydantic here would add validation overhead for an object that never
receives untrusted input. A dataclass is simpler and faster.

Compare to `AgentResult` (Pydantic) — that crosses the agent boundary and
needs validation. `JudgedResult` wraps `AgentResult` and stays internal.

---

## Fail Fast Pattern

The judge uses early returns throughout:

```python
# Check 1
if fails:
    return JudgedResult(valid=False, ...)   # exit immediately

# Check 2
for hypothesis in result.hypotheses:
    if fails:
        return JudgedResult(valid=False, ...)   # exit immediately

# Check 3
...

# All checks passed
return JudgedResult(valid=True, result=result)
```

**Why fail fast?**
- The first failure is the most actionable — report it and stop
- Running all checks on a result that already failed wastes time
- A list of multiple failures is harder to act on than one specific root cause
- The agent developer fixes check 1 first anyway before checking 2, 3, 4

---

## What the Judge Does NOT Do

- It does not decide what to do with failed results — that is the runtime's job
- It does not call an LLM — ever
- It does not modify the `AgentResult` — it only reads it
- It does not rank or score hypotheses — that is the aggregator's job
- It does not run across multiple results simultaneously — one result at a time

---

## The Rule to Remember

> The judge is the last line of defense before aggregation. It enforces
> the facts-vs-interpretations contract: hypotheses must be grounded in
> real signals. If they are not, they do not get ranked.
