"""Structured memory for a single runtime execution.

StructuredMemory is the shared, typed, append-only store that lives for the
duration of one AlphaRuntime.execute() call. It is created at the start of
execution, written to during signal extraction and agent execution, and read
by the judge and aggregator.

It is not a database. It does not persist between runs. No disk, no network.
When execute() returns, the memory object is discarded.

Lifecycle within one execute() call:
    1. AlphaRuntime creates an empty StructuredMemory
    2. SignalExtractor writes signals into it
    3. AlphaRuntime builds AgentContext from memory.get_signals()
    4. Agents run and produce AgentResults (hypotheses are NOT written here)
    5. JudgeLayer reads memory.get_signals() to cross-reference signal IDs
    6. Aggregator reads ranked hypotheses (held externally after aggregation)
"""

from schemas.hypothesis import Hypothesis
from schemas.signal import Signal


class StructuredMemory:
    """Typed, append-only in-RAM store for one execution.

    All writes are append-only — signals and hypotheses can be added but
    never removed or modified. This guarantees that:
    - Agents cannot tamper with signals that were extracted before they ran
    - The judge can trust that signal IDs in memory are stable
    - Concurrent agent reads are safe (no mutations during execution)

    Attributes:
        _signals: Internal list of signals extracted from the incident.
        _hypotheses: Internal list of hypotheses produced by agents.
    """

    def __init__(self) -> None:
        """Initialise empty memory. Always starts with no signals or hypotheses."""
        self._signals: list[Signal] = []
        self._hypotheses: list[Hypothesis] = []

    def add_signal(self, signal: Signal) -> None:
        """Append a single signal to memory.

        Args:
            signal: A verified fact produced by the signal extraction layer.
        """
        self._signals.append(signal)

    def add_signals(self, signals: list[Signal]) -> None:
        """Append multiple signals to memory in one call.

        Convenience method for the signal extractor, which typically produces
        all signals at once before any agent runs.

        Args:
            signals: List of verified facts to add. May be empty — no error
                is raised if the list is empty.
        """
        self._signals.extend(signals)

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Append a single hypothesis to memory.

        Args:
            hypothesis: A candidate root cause produced by an agent.
        """
        self._hypotheses.append(hypothesis)

    def get_signals(self) -> list[Signal]:
        """Return all signals currently in memory.

        Returns a copy so callers cannot mutate the internal list.

        Returns:
            List of all signals added so far. Empty list if none have
            been added yet.
        """
        return list(self._signals)

    def get_hypotheses(self) -> list[Hypothesis]:
        """Return all hypotheses currently in memory.

        Returns a copy so callers cannot mutate the internal list.

        Returns:
            List of all hypotheses added so far. Empty list if none have
            been added yet.
        """
        return list(self._hypotheses)

    def signal_ids(self) -> set[str]:
        """Return the set of all signal IDs currently in memory.

        Used by the JudgeLayer to efficiently cross-reference whether a
        hypothesis's cited signal IDs actually exist.

        Returns:
            Set of signal ID strings (e.g. {"sig_001", "sig_002"}).
        """
        return {s.id for s in self._signals}
