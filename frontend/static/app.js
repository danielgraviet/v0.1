/**
 * Alpha SRE — dashboard frontend.
 *
 * All API calls go through AlphaSRE.analyze().
 * Agent state and results are rendered into the four main panels.
 *
 * This is a skeleton. Wiring to the live AlphaRuntime API happens in Phase 3+.
 */

const AlphaSRE = (() => {
  // ─── State ────────────────────────────────────────────────────────────────

  const AGENT_IDS = ["agent-log", "agent-metrics", "agent-commit", "agent-config", "agent-synthesis"];

  const AGENT_LABELS = {
    "agent-log":       "LogAgent",
    "agent-metrics":   "MetricsAgent",
    "agent-commit":    "CommitAgent",
    "agent-config":    "ConfigAgent",
    "agent-synthesis": "SynthesisAgent",
  };

  let _running = false;
  let _startTime = null;
  let _timerInterval = null;

  // ─── DOM helpers ─────────────────────────────────────────────────────────

  function el(id) {
    return document.getElementById(id);
  }

  function setSystemStatus(state) {
    const pill = el("system-status");
    pill.className = `status-pill status--${state}`;
    pill.textContent = state.toUpperCase();
  }

  // ─── Agent card helpers ───────────────────────────────────────────────────

  function setAgentStatus(agentId, status, detail = "") {
    const card = el(agentId);
    if (!card) return;

    const badgeEl = card.querySelector(".badge");
    badgeEl.className = `badge badge--${status}`;
    badgeEl.textContent = status.toUpperCase();

    const detailEl = card.querySelector(".agent-detail");
    if (detail) {
      detailEl.textContent = detail;
    }
  }

  function resetAgents() {
    AGENT_IDS.forEach((id) => {
      setAgentStatus(id, "pending");
      el(id).querySelector(".agent-detail").textContent =
        id === "agent-synthesis" ? "Waits for all agents to complete" : "—";
    });
  }

  // ─── Timer ───────────────────────────────────────────────────────────────

  function startTimer() {
    _startTime = Date.now();
    const timerEl = el("agents-timer");
    timerEl.classList.remove("hidden");

    _timerInterval = setInterval(() => {
      const elapsed = Date.now() - _startTime;
      timerEl.textContent = `${elapsed}ms`;
    }, 100);
  }

  function stopTimer() {
    clearInterval(_timerInterval);
    _timerInterval = null;
  }

  // ─── Signal rendering ─────────────────────────────────────────────────────

  function renderSignals(signals) {
    const list = el("signals-list");
    const counter = el("signals-count");

    if (!signals || signals.length === 0) {
      list.innerHTML = `<div class="empty-state">No signals extracted.</div>`;
      counter.textContent = "0";
      return;
    }

    counter.textContent = String(signals.length);
    list.innerHTML = signals
      .map(
        (s) => `
        <div class="signal-item">
          <span class="signal-type">${escapeHtml(s.type)}</span>
          <span class="signal-desc">${escapeHtml(s.description)}</span>
          <span class="signal-severity severity--${s.severity}">${s.severity.toUpperCase()}</span>
        </div>`
      )
      .join("");
  }

  // ─── Hypothesis rendering ─────────────────────────────────────────────────

  function confidenceClass(score) {
    if (score >= 0.7) return "high";
    if (score >= 0.4) return "medium";
    return "low";
  }

  function renderHypotheses(hypotheses) {
    const list = el("hypotheses-list");
    const counter = el("hypotheses-count");

    if (!hypotheses || hypotheses.length === 0) {
      list.innerHTML = `<div class="empty-state">No hypotheses generated.</div>`;
      counter.textContent = "0";
      return;
    }

    counter.textContent = String(hypotheses.length);
    list.innerHTML = hypotheses
      .map((h, i) => {
        const cls = confidenceClass(h.confidence);
        const pct = Math.round(h.confidence * 100);
        return `
          <div class="hypothesis-item">
            <div class="hypothesis-header">
              <span class="hypothesis-rank">#${i + 1}</span>
              <span class="hypothesis-label">${escapeHtml(h.label)}</span>
              <span class="hypothesis-confidence confidence--${cls}">${pct}%</span>
            </div>
            <div class="confidence-bar-track">
              <div class="confidence-bar-fill confidence-bar-fill--${cls === "high" ? "" : cls}" style="width:${pct}%"></div>
            </div>
            <div class="hypothesis-desc">${escapeHtml(h.description)}</div>
            <div class="hypothesis-meta">
              <span class="hypothesis-agents">agents: ${h.contributing_agents ? h.contributing_agents.join(", ") : h.contributing_agent || "—"}</span>
              <span class="hypothesis-signals">signals: ${h.supporting_signals ? h.supporting_signals.join(", ") : "—"}</span>
            </div>
          </div>`;
      })
      .join("");

    el("approval-gate").classList.remove("hidden");
  }

  // ─── Error display ────────────────────────────────────────────────────────

  function showError(msg) {
    const errEl = el("input-error");
    errEl.textContent = msg;
    errEl.classList.remove("hidden");
  }

  function clearError() {
    el("input-error").classList.add("hidden");
  }

  // ─── Utility ─────────────────────────────────────────────────────────────

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ─── Main: analyze ────────────────────────────────────────────────────────

  async function analyze() {
    if (_running) return;

    clearError();

    // Parse and validate JSON input
    let payload;
    try {
      payload = JSON.parse(el("incident-json").value);
    } catch {
      showError("Invalid JSON — check your incident payload.");
      return;
    }

    _running = true;
    setSystemStatus("running");
    resetAgents();
    el("approval-gate").classList.add("hidden");
    renderSignals([]);
    renderHypotheses([]);
    el("analyze-btn").disabled = true;
    startTimer();

    // Mark all specialist agents as running
    ["agent-log", "agent-metrics", "agent-commit", "agent-config"].forEach((id) => {
      setAgentStatus(id, "running");
    });

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();

      // Stub response handling — replace with real response shape in Phase 3+
      if (data.status === "not_implemented") {
        // Show demo/mock state so the UI is useful before the backend is wired
        handleMockResult();
      } else {
        handleResult(data);
      }
    } catch (err) {
      stopTimer();
      setSystemStatus("error");
      AGENT_IDS.forEach((id) => setAgentStatus(id, "failed"));
      showError(`Request failed: ${err.message}`);
    } finally {
      _running = false;
      el("analyze-btn").disabled = false;
    }
  }

  // ─── Real result handler (Phase 3+) ──────────────────────────────────────

  function handleResult(data) {
    stopTimer();
    setSystemStatus("complete");

    if (data.agent_results) {
      data.agent_results.forEach((r) => {
        const agentId = agentNameToId(r.agent_name);
        setAgentStatus(agentId, "complete", `${r.execution_time_ms}ms · ${r.hypotheses.length} hypotheses`);
      });
    }

    setAgentStatus("agent-synthesis", "complete");
    renderSignals(data.signals_used || []);
    renderHypotheses(data.ranked_hypotheses || []);
  }

  function agentNameToId(name) {
    const map = {
      LogAgent:       "agent-log",
      MetricsAgent:   "agent-metrics",
      CommitAgent:    "agent-commit",
      ConfigAgent:    "agent-config",
      SynthesisAgent: "agent-synthesis",
    };
    return map[name] || null;
  }

  // ─── Mock result handler (used until backend is wired) ───────────────────

  function handleMockResult() {
    stopTimer();
    setSystemStatus("complete");

    // Simulate staggered agent completion
    const delays = [600, 900, 750, 1100];
    ["agent-log", "agent-metrics", "agent-commit", "agent-config"].forEach((id, i) => {
      setTimeout(() => {
        setAgentStatus(id, "complete", `${delays[i]}ms`);
      }, delays[i]);
    });

    setTimeout(() => {
      setAgentStatus("agent-synthesis", "complete", "1250ms");

      renderSignals(MOCK_SIGNALS);
      renderHypotheses(MOCK_HYPOTHESES);
    }, 1300);
  }

  // ─── Approval gate ────────────────────────────────────────────────────────

  function approve() {
    el("approval-gate").classList.add("hidden");
    // Stub: wire to patch application endpoint in Phase 6+
    console.log("[Alpha SRE] Approval recorded — no action taken (not yet implemented).");
  }

  function reject() {
    el("approval-gate").classList.add("hidden");
    console.log("[Alpha SRE] Analysis rejected.");
  }

  // ─── Mock data ────────────────────────────────────────────────────────────

  const MOCK_SIGNALS = [
    {
      type: "metric_spike",
      description: "p99 latency spiked to 4800ms (baseline ~200ms)",
      severity: "critical",
    },
    {
      type: "metric_degradation",
      description: "Cache hit rate dropped from 88% to 6%",
      severity: "high",
    },
    {
      type: "resource_saturation",
      description: "DB connection pool at 98/100 (98% utilization)",
      severity: "high",
    },
    {
      type: "log_anomaly",
      description: "DB query timeout errors: 0 → 847/min",
      severity: "critical",
    },
    {
      type: "commit_change",
      description: "cache.py: cache decorator removed in commit b19e044",
      severity: "high",
    },
    {
      type: "commit_change",
      description: "db/queries.py: query restructured in commit a3f8c12 (possible N+1)",
      severity: "medium",
    },
  ];

  const MOCK_HYPOTHESES = [
    {
      label: "Cache removal caused DB saturation cascade",
      description:
        "Removal of cache decorator in commit b19e044 forced all requests to hit the DB directly. Combined with an unindexed query introduced in a3f8c12, this saturated the connection pool and caused cascading timeouts.",
      confidence: 0.91,
      contributing_agents: ["LogAgent", "MetricsAgent", "CommitAgent"],
      supporting_signals: ["sig-cache-drop", "sig-pool-sat", "sig-commit-cache"],
    },
    {
      label: "Unindexed query in db/queries.py",
      description:
        "The refactored user query in commit a3f8c12 may have introduced a full-table scan. Without the cache absorbing traffic, this query runs on every request and degrades under load.",
      confidence: 0.74,
      contributing_agents: ["CommitAgent", "MetricsAgent"],
      supporting_signals: ["sig-db-latency", "sig-commit-query"],
    },
    {
      label: "Connection pool undersized for current traffic",
      description:
        "DB connection pool capped at 10 (config_snapshot.db_pool_size). Under cache-miss load this is exhausted immediately, queuing all requests and amplifying latency.",
      confidence: 0.58,
      contributing_agents: ["ConfigAgent", "MetricsAgent"],
      supporting_signals: ["sig-pool-sat"],
    },
  ];

  // ─── Public API ───────────────────────────────────────────────────────────

  return { analyze, approve, reject };
})();
