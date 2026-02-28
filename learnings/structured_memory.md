# Structured Memory

How Alpha manages state during a single execution, and why it was designed this way.

---

## What It Is

`StructuredMemory` is a typed, append-only, in-RAM container that lives for
the duration of one `AlphaRuntime.execute()` call.

It is not a database. It is not a cache. It is the shared whiteboard for a
single execution — created when the run starts, discarded when it ends.

```python
mem = StructuredMemory()   # born at the start of execute()
mem.add_signals([...])     # signal extractor writes verified facts
mem.get_signals()          # executor reads signals to build AgentContext
mem.signal_ids()           # judge uses this to validate hypothesis citations
                           # execute() returns → memory is garbage collected
```

---

## Lifecycle Within One Execution

```
AlphaRuntime.execute()
    │
    ├─ 1. Create StructuredMemory (empty)
    │
    ├─ 2. SignalExtractor → memory.add_signals([...])
    │        Verified facts are now in memory
    │
    ├─ 3. Build AgentContext from memory.get_signals()
    │        Agents receive a snapshot of signals
    │
    ├─ 4. ParallelExecutor runs all agents concurrently
    │        Each agent returns an AgentResult
    │        (agents do NOT write back to memory)
    │
    ├─ 5. JudgeLayer reads memory.signal_ids()
    │        Cross-references each hypothesis's supporting_signals
    │        against real signal IDs in memory
    │
    └─ 6. Aggregator ranks valid hypotheses → ExecutionResult returned
```

---

## Key Design Decisions

### 1. In-RAM only — no database

For a single execution, a database would add latency, complexity, and
infrastructure overhead with no benefit. The data only needs to exist for
the duration of one function call.

If Alpha ever needed to replay executions, store historical runs, or share
state across distributed workers, a database would become necessary. For the
hackathon and single-process execution, RAM is the right choice.

### 2. Append-only writes

Signals and hypotheses can be added but never removed or modified:

```python
mem.add_signal(signal)     # allowed
mem.add_signals(signals)   # allowed
mem._signals.pop()         # violates the convention — don't do this
```

**Why append-only?**

Agents run concurrently. If one agent could modify or remove a signal while
another was reasoning over it, you'd have a race condition — agent B's
hypothesis might cite `sig_003`, which agent A just deleted. The judge would
then reject a valid hypothesis for a bad reason.

Append-only means reads are always safe during concurrent execution. No locks,
no synchronisation needed.

### 3. `get_signals()` returns a copy, not the internal list

```python
def get_signals(self) -> list[Signal]:
    return list(self._signals)   # copy
```

If `get_signals()` returned `self._signals` directly, any caller could do:

```python
signals = mem.get_signals()
signals.clear()   # accidentally wipes memory
```

Returning a copy means callers can do whatever they want with the list —
sort it, filter it, clear it — without affecting the stored state.

### 4. `signal_ids()` returns a `set`, not a list

```python
def signal_ids(self) -> set[str]:
    return {s.id for s in self._signals}
```

The judge checks: "does this signal ID exist in memory?" for every cited ID
in every hypothesis. That is an existence check — exactly what sets are
optimised for.

| Operation | List | Set |
|---|---|---|
| `"sig_001" in signals` | O(n) — scans every element | O(1) — hash lookup |
| Useful for ordering | Yes | No |
| Useful for existence checks | Technically, but slow | Yes |

With 10 signals and 4 agents each producing 2 hypotheses with 3 citations
each, that is 24 existence checks. A set makes each one instant.

### 5. Typed storage — Pydantic models, not raw dicts

```python
self._signals: list[Signal] = []         # not list[dict]
self._hypotheses: list[Hypothesis] = []  # not list[dict]
```

Storing raw dicts would mean the judge and aggregator have to do their own
field access with string keys (`signal["id"]`), which has no type safety and
no autocomplete. Storing typed Pydantic models means:

- `signal.id` — type-checked, autocompleted, validated at insertion time
- If a signal is malformed, Pydantic catches it when it enters memory,
  not when the judge tries to read from it later

---

## Why Not Just Use a Global Variable?

A global `MEMORY = StructuredMemory()` would work for a single-threaded
script, but would break immediately if you ran two incidents concurrently —
both executions would share the same memory and corrupt each other's signals.

Creating a new `StructuredMemory()` per `execute()` call means each run is
fully isolated. Two concurrent executions have separate memory instances with
no shared state.

---

## What Gets Stored vs What Doesn't

| Data | Stored in memory? | Why |
|---|---|---|
| Signals from signal extractor | Yes | Agents need them; judge cross-references them |
| Hypotheses from agents | Yes (via `add_hypothesis`) | SynthesisAgent needs to read all hypotheses |
| Raw `AgentResult` objects | No | Held by executor, passed directly to judge |
| `ExecutionResult` | No | Returned to caller, not stored anywhere |
| Events (display layer) | No | Emitted in real time, not persisted |

---

## The Rule to Remember

> Memory is infrastructure for one execution. Agents read from it.
> Only the runtime and signal extractor write to it.
> Nothing outside `AlphaRuntime.execute()` should hold a reference to it.
