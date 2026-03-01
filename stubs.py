"""Stub agents for dashboard demo. Phase 4 replaces these with real SRE agents."""

import asyncio

from agents.base import AgentContext, BaseAgent
from schemas.hypothesis import Hypothesis
from schemas.result import AgentResult


class _Stub(BaseAgent):
    def __init__(self, name, label, desc, conf, delay, source_kw):
        self.llm = None
        self._name, self._label, self._desc = name, label, desc
        self._conf, self._delay, self._source_kw = conf, delay, source_kw

    @property
    def name(self):
        return self._name

    async def run(self, ctx: AgentContext) -> AgentResult:
        await asyncio.sleep(self._delay)
        sigs = [s for s in ctx.signals if self._source_kw in s.source] or ctx.signals[:1]
        if not sigs:
            return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0)
        return AgentResult(
            agent_name=self.name,
            hypotheses=[Hypothesis(
                label=self._label, description=self._desc, confidence=self._conf,
                severity="high", supporting_signals=[s.id for s in sigs[:2]],
                contributing_agent=self.name,
            )],
            execution_time_ms=self._delay * 1000,
        )


def register_stub_agents(runtime):
    """Register demo stub agents on the runtime."""
    runtime.register(_Stub("log_agent", "Error Rate Spike",
                           "Error rate elevated above baseline", 0.82, 0.8, "log"))
    runtime.register(_Stub("metrics_agent", "DB Connection Pool Exhaustion",
                           "Connection pool near capacity", 0.91, 0.6, "metrics"))
    runtime.register(_Stub("commit_agent", "Cache Removal Impact",
                           "Recent commit removed cache layer", 0.78, 1.0, "commit"))
    runtime.register(_Stub("config_agent", "Connection Pool Undersized",
                           "Pool size insufficient for traffic", 0.65, 0.7, "config"))
