# Alpha — High-Level Roadmap

## Vision

Alpha is a parallel AI runtime for coordinating specialized agents.

The first vertical is Alpha SRE — an AI-powered incident investigation system for small engineering teams.

The roadmap is structured to:

1. Prove value in a narrow vertical.
2. Build the runtime through real usage.
3. Polish abstraction after validation.
4. Position Alpha as infrastructure.

---

# Phase 0 — Vision & Scope Lock

**Goal:** Prevent overbuilding.

### Outcomes

* Define target user (early-stage engineering teams)
* Define problem (incident investigation chaos)
* Define non-goals (no auto-remediation, no observability ingestion)
* Define demo story
* Lock single incident scenario (polished > broad)

### Deliverable

* Clear product narrative
* Agreed feature boundaries
* Defined demo flow

This phase protects you from scope creep.

---

# Phase 1 — Vertical Contract Definition

**Goal:** Define what flows through the system.

This is the product contract for Alpha SRE.

### Outcomes

* Define Incident Input structure
* Define deterministic Signals layer
* Define Agent role model
* Define Hypothesis model (independent)
* Define Aggregated Output structure

### Deliverable

* Clear schemas (conceptual, not over-engineered)
* Explicit separation of:

  * Facts (signals)
  * Interpretations (hypotheses)

This phase defines what the runtime must support.

---

# Phase 2 — Minimal Alpha Runtime (Core Engine)

**Goal:** Build only what the SRE vertical requires.

This is not a general framework yet.
This is a minimal orchestration engine.

### Capabilities

* Agent registration
* Parallel execution
* Structured memory container
* Judge layer (basic validation)
* Hypothesis aggregation
* Structured final result

### Deliverable

* Working runtime that can:

  * Accept structured input
  * Dispatch parallel agents
  * Aggregate ranked hypotheses

No plugin system.
No extensibility marketing.
Just execution.

---

# Phase 3 — Deterministic Signal Layer (SRE Foundation)

**Goal:** Extract objective signals before AI reasoning.

This gives credibility.

### Capabilities

* Log anomaly detection
* Metric spike detection
* Commit diff scanning
* Config change inspection

### Deliverable

* Structured signal objects
* Repeatable deterministic output

This phase separates Alpha from “LLM wrapper” projects.

---

# Phase 4 — SRE Agent Pack

**Goal:** Model a parallel AI SRE team.

### Agents

* Log Analyst
* Metrics Analyst
* Commit Analyst
* Config Analyst
* Synthesis Agent

### Capabilities

* Independent hypothesis generation
* Confidence scoring
* Structured reasoning summaries
* Signal grounding enforcement

### Deliverable

* Multiple agents running in parallel
* Independent hypotheses
* Ranked, confidence-weighted output

This is the visible intelligence layer.

---

# Phase 5 — Aggregation & Confidence Modeling

**Goal:** Make results feel credible and system-driven.

### Capabilities

* Cross-agent agreement boosting
* Confidence normalization
* Severity weighting
* Deduplication

### Deliverable

* Ranked hypothesis list
* Contributing agent visibility
* Transparent confidence scoring

This is your differentiation layer.

---

# Phase 6 — CLI & Minimal Dashboard

**Goal:** Provide a serious engineering interface.

### CLI

* Run analysis
* Inspect results
* Replay execution

### Dashboard (minimal)

* Agent execution states
* Signal summary
* Ranked hypotheses
* Human approval gate

No chat UI.
No gimmicks.
Engineering-first aesthetic.

---

# Phase 7 — Demo Polish & Narrative

**Goal:** Win the room.

### Polish

* Clean output formatting
* Clear ranking display
* Clean logging
* Remove debugging noise

### Narrative

* Start with incident pain
* Show parallel execution
* Reveal ranked root causes
* Emphasize deterministic + probabilistic separation
* Position runtime as reusable core

### Deliverable

* Smooth 3–5 minute demo
* Crisp explanation of architecture
* Confident answers to “what’s next?”

---

# Phase 8 — Runtime Abstraction Hardening (Post-Demo Optional)

**Goal:** Make Alpha look like infrastructure.

After SRE works:

* Clean module boundaries
* Extract domain-specific assumptions
* Rename internals generically
* Improve type clarity
* Prepare runtime for open-source positioning

This is when Alpha becomes “a platform.”

Not before.

---

# Strategic Arc

The roadmap intentionally flows:

1. Narrow vertical
2. Real usage
3. Runtime proven in context
4. Infrastructure positioning

You are not building:

“A general agent framework that might someday be useful.”

You are building:

“A domain-proven runtime that expands outward.”

---

# Hackathon Priority Order (If Time Gets Tight)

If time compresses:

1. Single incident scenario
2. Deterministic signal extraction
3. Parallel agents
4. Simple aggregation
5. CLI polish

Dashboard is optional.
Abstraction polish is optional.
Second scenario is optional.

Invest in depth, not breadth.

---

# Final Positioning Statement (for the Overview File)

Alpha is a deterministic runtime for coordinating parallel AI agents.
Alpha SRE is the first vertical application, providing structured, confidence-weighted incident investigation for small engineering teams.

The runtime is built through the vertical, not before it.