# Agent Registry

How Alpha tracks registered agents, and why the registry is designed the way it is.

---

## What It Is

`AgentRegistry` is the runtime's roster of agents. It is a simple lookup table
that answers two questions:

1. Which agents are registered? (`get_all()`)
2. Is a specific agent registered? (`get_by_name()`)

`AlphaRuntime` delegates all agent registration to it. `ParallelExecutor`
calls `get_all()` to know which agents to run. Neither the executor nor the
runtime manage their own agent lists — the registry owns that responsibility.

---

## Internal Structure

The registry is backed by a `dict`, not a `list`:

```python
self._agents: dict[str, BaseAgent] = {}
#                   ^^^
#                   keyed by agent.name
```

| Operation | With a list | With a dict |
|---|---|---|
| `get_all()` | O(n) copy | O(n) copy |
| `get_by_name("log_agent")` | O(n) — scan every element | O(1) — hash lookup |
| Check for duplicates on register | O(n) — scan every element | O(1) — key check |

For the number of agents Alpha runs (4–5), this difference is negligible in
practice. But a dict is semantically correct — agents are identified by name,
and dicts are designed for keyed lookup.

---

## Key Design Decisions

### 1. Duplicate names raise `ValueError` immediately

```python
def register(self, agent: BaseAgent) -> None:
    if agent.name in self._agents:
        raise ValueError(f"Agent '{agent.name}' is already registered...")
    self._agents[agent.name] = agent
```

Two agents with the same name would cause silent, hard-to-debug problems:
- The judge labels results by `agent_name` — ambiguous if two share a name
- The aggregator tracks `contributing_agent` — would conflate two agents
- The display layer would render two panels with identical labels

Raising immediately at registration time surfaces the bug before any
execution happens.

**This is `ValueError`, not a silent overwrite.**
An alternative design would silently replace the first agent with the second.
That would be worse — the first agent would vanish with no indication.

---

### 2. `get_by_name()` returns `None`, not an exception

```python
def get_by_name(self, name: str) -> BaseAgent | None:
    return self._agents.get(name)
```

Compare the two approaches:

```python
# Option A — raises on missing (forces caller to use try/except)
def get_by_name(self, name: str) -> BaseAgent:
    if name not in self._agents:
        raise KeyError(f"No agent named '{name}'")
    return self._agents[name]

# Option B — returns None on missing (caller decides how to handle it)
def get_by_name(self, name: str) -> BaseAgent | None:
    return self._agents.get(name)
```

A missing agent is a valid query result — the caller might be doing an
optional check ("is this agent registered?"). Raising an exception would
force every caller into a try/except block for a non-exceptional situation.

The `| None` return type makes the contract explicit: callers must handle
the None case or their type checker will warn them.

---

### 3. `get_all()` returns a copy

```python
def get_all(self) -> list[BaseAgent]:
    return list(self._agents.values())
```

`self._agents.values()` is a live view into the dict — modifying it would
modify the registry's internal state. `list(...)` creates a copy, so callers
can sort, filter, or clear the returned list without affecting the registry.

Same principle as `StructuredMemory.get_signals()`.

---

### 4. `__len__` makes the registry feel like a Python container

```python
def __len__(self) -> int:
    return len(self._agents)
```

Without this, checking the registry size requires:
```python
len(registry.get_all())   # clunky — allocates a copy just to count
```

With `__len__`, you can write:
```python
len(registry)   # natural, no allocation
```

This is a Python protocol — implementing `__len__` means the object works
with the built-in `len()` function, which is what users expect.

---

## What the Registry Does NOT Do

- It does not run agents — that is `ParallelExecutor`'s job
- It does not validate agent output — that is `JudgeLayer`'s job
- It does not know about execution order or parallelism
- It does not persist between executions — a new `AlphaRuntime` instance
  starts with an empty registry

---

## The Rule to Remember

> The registry owns the agent list. Everything else asks the registry.
> No other component maintains its own copy of which agents exist.
