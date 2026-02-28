# Parallel Executor

How Alpha runs multiple agents at the same time, and why the executor is
designed to be fault-tolerant by default.

---

## What It Is

`ParallelExecutor` is the component that runs all registered agents
concurrently and collects their results. It sits between the runtime (which
decides *which* agents to run) and the judge (which decides *what to do* with
the results).

It owns three responsibilities:
1. **Concurrency** — all agents run at the same time, not one after another
2. **Timeouts** — agents that hang get cut off
3. **Fault isolation** — one agent crashing does not affect the others

---

## How `asyncio` Concurrency Works

Python's `asyncio` runs coroutines concurrently on a single thread. It does
not use multiple CPU cores — it uses cooperative multitasking. A coroutine
runs until it hits an `await`, at which point Python switches to another
coroutine that is ready to run.

```
Time →

GoodAgent:   ──── await llm.complete() ──────────────────── result
CrashAgent:  ──── raises ✗
SlowAgent:   ──── await asyncio.sleep(999) ── timeout ✗

All three start at the same moment. Python switches between them at each
await point. Total wall time ≈ slowest successful agent, not sum of all.
```

**Why this matters for Alpha:** LLM API calls are network-bound. Each agent
spends most of its time waiting for an HTTP response. `asyncio` lets all four
agents wait simultaneously instead of sequentially, which cuts total execution
time from ~(4 × latency) to ~(1 × latency).

---

## `asyncio.TaskGroup`

`TaskGroup` (Python 3.11+) schedules multiple coroutines concurrently and
waits for all of them to finish:

```python
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(agent.run(context)) for agent in agents]
# All tasks are done here
```

**Critical behavior:** If any task raises an **unhandled** exception,
`TaskGroup` immediately cancels all remaining tasks. This is the right default
for most applications — but wrong for Alpha, where we want the other agents
to continue even if one fails.

**The fix:** Wrap each agent's execution in a try/except *inside* the task.
The task itself never raises — it catches all exceptions and returns `None`.
`TaskGroup` only sees clean task completions.

```python
# Wrong — one crash cancels everything
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(agent.run(context)) for agent in agents]

# Right — each agent is isolated
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(self._run_agent_safely(agent, context)) for agent in agents]
#                                  ^^^^^^^^^^^^^^^^^^
#                                  catches all exceptions, returns None on failure
```

---

## `asyncio.wait_for()` — Per-Agent Timeouts

`asyncio.wait_for(coro, timeout=N)` runs a coroutine and cancels it if it
does not complete within N seconds:

```python
result = await asyncio.wait_for(
    agent.run(context),
    timeout=self.timeout_seconds,  # default: 30
)
```

If the timeout fires, it raises `asyncio.TimeoutError`. Since this happens
inside `_run_agent_safely`, it is caught, logged, and returned as `None`.
The other agents are unaffected.

**Without this:** A single agent making a slow or hanging API call would
block the entire `TaskGroup` indefinitely. With it, every agent has a
guaranteed exit — either a result, a crash, or a timeout.

---

## Fault Isolation in Practice

The test from development showed all three failure modes in one run:

```
Agent 'crash_agent' raised after 0ms — skipping. Error: Something went wrong
Agent 'slow_agent' timed out after 1.0s (limit: 1s) — skipping.
Results returned: 1 (expected 1 — only GoodAgent)
Returned agent: good_agent
Execution time recorded: 50.7ms
```

Three agents ran concurrently. Two failed (one crash, one timeout). One
succeeded. The runtime received exactly one result and continued normally.

---

## Who Owns Execution Timing

The executor measures wall-clock time per agent, not the agent itself:

```python
start = time.perf_counter()
result = await asyncio.wait_for(agent.run(context), timeout=...)
elapsed_ms = (time.perf_counter() - start) * 1000
return result.model_copy(update={"execution_time_ms": elapsed_ms})
```

Agents set `execution_time_ms=0.0` in their `run()` return. The executor
overwrites it with the real value.

**Why the executor owns this:**
- Timing is infrastructure, not business logic — agents shouldn't care about it
- The executor has the most accurate view: it measures from just before the
  call to just after, including asyncio scheduling overhead
- Keeping timing in one place means one place to change if the measurement
  strategy ever needs to update

`model_copy(update={...})` is Pydantic v2's way of creating a new model
instance with one field changed. It does not mutate the original — Pydantic
models are immutable.

---

## `time.perf_counter()` vs `time.time()`

```python
start = time.perf_counter()  # used in executor
```

| | `time.time()` | `time.perf_counter()` |
|---|---|---|
| What it measures | Wall clock (system time) | High-resolution elapsed time |
| Affected by system clock changes | Yes | No |
| Precision | ~milliseconds | ~nanoseconds |
| Good for timestamps | Yes | No |
| Good for measuring elapsed time | No | Yes |

`perf_counter()` is the right tool for measuring how long something took.
`time()` is for knowing what time it is.

---

## Key Design Decisions Summary

| Decision | Why |
|---|---|
| `asyncio.TaskGroup` | Schedules all agents at once, waits for all to finish |
| try/except inside each task | Prevents one failure from cancelling other agents |
| `asyncio.wait_for()` per agent | Guarantees every agent exits within the timeout |
| Executor owns timing | Infrastructure concern separated from agent logic |
| `model_copy(update=...)` | Pydantic v2 way to update one field without mutation |
| Returns `None` on failure, filtered out | Clean separation — executor handles faults, runtime handles results |

---

## The Rule to Remember

> Agents are untrusted workers. The executor assumes any of them can fail
> at any time, for any reason. Its job is to run all of them and return
> whatever succeeded — never to let one bad agent ruin the run.
