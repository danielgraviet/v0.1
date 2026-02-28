/**
 * Alpha SRE — dashboard frontend.
 *
 * Displays the same data as cli.py: agent panels with real-time status,
 * ranked hypotheses table, review flag, and execution ID.
 */

const AlphaSRE = (() => {
  const AGENT_IDS = ["agent-log", "agent-metrics", "agent-commit", "agent-config"];

  let _running = false;
  let _startTime = null;
  let _timerInterval = null;

  function el(id) { return document.getElementById(id); }

  function setSystemStatus(state) {
    const pill = el("system-status");
    pill.className = `status-pill status--${state}`;
    pill.textContent = state.toUpperCase();
  }

  function setAgentStatus(agentId, status, detail = "") {
    const card = el(agentId);
    if (!card) return;
    const badge = card.querySelector(".badge");
    badge.className = `badge badge--${status}`;
    badge.textContent = status.toUpperCase();
    if (detail) card.querySelector(".agent-detail").textContent = detail;
  }

  function resetAgents() {
    AGENT_IDS.forEach((id) => {
      setAgentStatus(id, "pending");
      el(id).querySelector(".agent-detail").textContent = "—";
    });
  }

  function agentNameToId(name) {
    const map = {
      log_agent: "agent-log",
      metrics_agent: "agent-metrics",
      commit_agent: "agent-commit",
      config_agent: "agent-config",
    };
    return map[name] || null;
  }

  function startTimer() {
    _startTime = Date.now();
    const t = el("agents-timer");
    t.classList.remove("hidden");
    _timerInterval = setInterval(() => { t.textContent = `${Date.now() - _startTime}ms`; }, 100);
  }

  function stopTimer() { clearInterval(_timerInterval); _timerInterval = null; }

  function escapeHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // ─── Hypothesis table (matches CLI: #, Label, Confidence, Severity, Agents) ──

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
        const pct = Math.round(h.confidence * 100);
        const cls = pct >= 80 ? "high" : pct >= 60 ? "medium" : "low";
        return `
          <div class="hypothesis-item">
            <div class="hypothesis-header">
              <span class="hypothesis-rank">#${i + 1}</span>
              <span class="hypothesis-label">${escapeHtml(h.label)}</span>
              <span class="hypothesis-confidence confidence--${cls}">${pct}%</span>
              <span class="hypothesis-severity">${escapeHtml(h.severity)}</span>
              <span class="hypothesis-agents">${escapeHtml(h.contributing_agent || "—")}</span>
            </div>
          </div>`;
      })
      .join("");
  }

  // ─── Error display ──

  function showError(msg) {
    const e = el("input-error");
    e.textContent = msg;
    e.classList.remove("hidden");
  }

  function clearError() { el("input-error").classList.add("hidden"); }

  // ─── Real-time event handling ──

  function handleAgentEvent(event) {
    const agentId = agentNameToId(event.agent_name);
    if (!agentId) return;

    const secs = (event.timestamp_ms / 1000).toFixed(2) + "s";

    if (event.event_type === "started") {
      setAgentStatus(agentId, "running", "analyzing...");
    } else if (event.event_type === "complete") {
      setAgentStatus(agentId, "complete", `${secs} · ${event.message}`);
    } else if (event.event_type === "signal_detected") {
      setAgentStatus(agentId, "running", event.message);
    } else if (event.event_type === "error") {
      setAgentStatus(agentId, "failed", `${secs} · ${event.message}`);
    }
  }

  function handleResult(data) {
    stopTimer();
    setSystemStatus("complete");
    renderHypotheses(data.hypotheses || []);

    // Review flag (matches CLI footer)
    const flag = el("review-flag");
    if (data.requires_human_review) {
      flag.textContent = "⚠  Requires human review";
      flag.className = "review-flag review-flag--warn";
    } else {
      flag.textContent = "✓  Confidence sufficient for automated action";
      flag.className = "review-flag review-flag--ok";
    }

    if (data.execution_id) {
      const eid = el("execution-id");
      eid.textContent = `execution: ${data.execution_id}`;
      eid.classList.remove("hidden");
    }
  }

  // ─── Main ──

  async function analyze() {
    if (_running) return;
    clearError();

    let payload;
    try { payload = JSON.parse(el("incident-json").value); }
    catch { showError("Invalid JSON — check your incident payload."); return; }

    _running = true;
    setSystemStatus("running");
    resetAgents();
    el("review-flag").className = "hidden";
    renderHypotheses([]);
    el("analyze-btn").disabled = true;
    startTimer();

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        while (buffer.includes("\n")) {
          const idx = buffer.indexOf("\n");
          const line = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          if (!line) continue;
          const msg = JSON.parse(line);
          if (msg.type === "agent_event") handleAgentEvent(msg);
          else if (msg.type === "result") handleResult(msg);
        }
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

  // Load default fixture data on page load (same data cli.py uses)
  async function loadFixture() {
    try {
      const res = await fetch("/fixtures/incident_b.json");
      if (!res.ok) return;
      const data = await res.json();
      el("incident-json").value = JSON.stringify(data, null, 2);
    } catch { /* fixture not available — user can paste manually */ }
  }

  document.addEventListener("DOMContentLoaded", loadFixture);

  return { analyze };
})();
