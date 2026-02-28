# Design Decisions

Key architectural and code-level decisions made during development, and the reasoning behind them.

---

## Python Concepts

### Pydantic `Field(default_factory=...)` vs a plain default

```python
# Wrong — generates ONE uuid at class definition time, reused forever
execution_id: str = str(uuid.uuid4())

# Right — calls the function fresh on every new instance
execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
```

`default_factory` accepts a callable and calls it each time an instance is created.
Use it any time your default value needs to be unique or mutable per instance.

---

### Pydantic `@field_validator` + `@classmethod`

```python
@field_validator("confidence")
@classmethod
def confidence_must_be_valid(cls, v: float) -> float:
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
    return v
```

`@field_validator("x")` intercepts a field's value before it's stored on the model.
If it raises, the entire instantiation fails immediately with a readable error.

`@classmethod` is required because validation runs before the object exists —
`cls` is the class itself, not an instance. You rarely use `cls` in the body,
but Pydantic requires the signature.

**Why validate at the model level instead of in the judge?**
The confidence validator fires on every `Hypothesis(...)` call, not just during
judge validation. This means malformed data is caught at the earliest possible
point — inside the agent — rather than propagating through memory and into the
aggregator before being rejected.

---

### Abstract classes (`ABC` + `@abstractmethod`)

```python
from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...
```

`ABC` marks a class as abstract. Python refuses to instantiate it directly.
Any subclass that doesn't implement every `@abstractmethod` also can't be
instantiated. This turns a runtime mistake into an immediate, readable error.

**When to use it:** When you have an interface that multiple implementations
will satisfy (e.g. `LLMClient` → `OpenRouterClient`, future `CerebrasClient`),
and you want Python to enforce that every implementation is complete.

---

### `@property @abstractmethod` for `name`

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
```

vs passing name as a constructor argument:

```python
# Alternative — don't do this
def __init__(self, llm, name: str): ...
```

Declaring `name` as an abstract property means subclasses define it at the
class level, not at instantiation time. There is no way to create an agent
without a name — Python enforces it before you ever call `__init__`.

```python
class LogAgent(BaseAgent):
    name = "log_agent"   # one line, always present, impossible to forget
```

---

### `@dataclass` vs Pydantic model

| | `@dataclass` | Pydantic `BaseModel` |
|---|---|---|
| Validates field types | No | Yes |
| Serializes to JSON | No (without extra work) | Yes |
| Raises on bad input | No | Yes |
| Overhead | Minimal | Small but present |
| Best for | Internal runtime objects | External data boundaries |

`AgentContext` is a dataclass because it is an internal runtime object — it
never crosses an API boundary, never gets serialized, and never receives
untrusted input. Adding Pydantic validation here would be unnecessary overhead.

`Signal`, `Hypothesis`, `IncidentInput`, `AgentResult`, `ExecutionResult` are
Pydantic models because they cross boundaries: they come from external sources,
flow through the judge, or are returned to callers.

---

## Architecture Decisions

### Dependency injection for `LLMClient`

```python
# Agent does NOT do this
class LogAgent(BaseAgent):
    def __init__(self):
        self.llm = OpenRouterClient("anthropic/claude-sonnet-4.5")  # hardcoded

# Agent DOES do this
class LogAgent(BaseAgent):
    def __init__(self, llm: LLMClient):
        self.llm = llm  # injected by the caller
```

Injecting the LLM client at construction time means:
- Swapping a model is one string change at the call site
- Tests can inject a stub client — no real API calls required
- The agent class has no knowledge of which provider it's using

---

### `os.environ["KEY"]` vs `os.getenv("KEY")`

```python
# Silent failure — passes None to the API client, confusing auth error later
api_key=os.getenv("OPENROUTER_API_KEY")

# Immediate failure — KeyError at construction with a clear message
api_key=os.environ["OPENROUTER_API_KEY"]
```

Bracket syntax raises `KeyError` immediately if the key is missing.
`os.getenv()` returns `None`, which silently passes through to the API client
and produces a confusing authentication error on the first call — far from
where the real problem is.

**Rule:** Use `os.environ["KEY"]` for required secrets. Use `os.getenv("KEY")`
only when the variable is truly optional and `None` is a valid value.

---

### Monorepo structure: runtime layer vs SRE vertical

```
schemas/  core/  agents/  llm/  judge/  aggregation/  display/
  ↑ runtime layer — generic, no SRE knowledge

sre/
  ↑ SRE vertical — imports from runtime, never the reverse
```

Keeping both layers in one repo avoids managing cross-repo dependencies during
the hackathon. The boundary is enforced by convention: nothing outside `sre/`
imports from it.

This makes the runtime portable — in theory, it could power a different
vertical (e.g. security incident analysis) by adding a new top-level package
alongside `sre/` without touching the runtime layer.

---

### OpenRouter model IDs use dots, not dashes

OpenRouter model IDs do not always match the Anthropic/Google native IDs.

| Provider native ID | OpenRouter ID |
|---|---|
| `claude-sonnet-4-6` | `anthropic/claude-sonnet-4.5` |
| `gemini-2.0-flash` | `google/gemini-2.0-flash-001` |

Always verify model IDs against [openrouter.ai/models](https://openrouter.ai/models)
before using them in code. A wrong model ID produces a `400 Bad Request` at
runtime, not a startup error.

---

### `.env.example` pattern for team secrets

| File | Committed? | Purpose |
|---|---|---|
| `.env.example` | Yes | Shows teammates which variables are required |
| `.env` | No (gitignored) | Holds real values locally |

New dev onboarding:
```bash
cp .env.example .env
# fill in real values
```

`python-dotenv` only loads `.env` by default. `.env.local` is a frontend
convention (Next.js) — it does nothing in Python without an explicit
`load_dotenv(".env.local")` call.
