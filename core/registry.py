"""Agent registry.

AgentRegistry is the runtime's roster of agents. It tracks which agents have
been registered and provides lookup by name. AlphaRuntime delegates all agent
registration and retrieval to this class.

The registry enforces one invariant: agent names must be unique. Two agents
with the same name would produce ambiguous output in the judge, aggregator,
and display layer — so duplicate registration is rejected immediately.
"""

from agents.base import BaseAgent


class AgentRegistry:
    """Tracks registered agents and provides lookup by name.

    Used by AlphaRuntime to store agents at registration time, and by
    ParallelExecutor to retrieve the full agent list at execution time.

    Internally backed by a dict keyed on agent name, which gives O(1)
    lookup for get_by_name() without scanning the full list.

    Attributes:
        _agents: Internal dict mapping agent name to agent instance.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent with the runtime.

        Args:
            agent: The agent instance to register. Its name property is
                used as the unique key.

        Raises:
            ValueError: If an agent with the same name is already registered.
                This is always a programming error, not a recoverable condition.
        """
        if agent.name in self._agents:
            raise ValueError(
                f"Agent '{agent.name}' is already registered. "
                "Each agent must have a unique name."
            )
        self._agents[agent.name] = agent

    def get_all(self) -> list[BaseAgent]:
        """Return all registered agents.

        Returns a copy of the internal list so callers cannot mutate the
        registry's state.

        Returns:
            List of all registered agent instances. Empty list if no agents
            have been registered yet.
        """
        return list(self._agents.values())

    def get_by_name(self, name: str) -> BaseAgent | None:
        """Look up a registered agent by name.

        Returns None rather than raising if the agent is not found, because
        a missing agent is a valid query result — not an exceptional condition.
        The caller decides how to handle it.

        Args:
            name: The agent name to look up (e.g. "log_agent").

        Returns:
            The registered agent instance, or None if no agent with that
            name has been registered.
        """
        return self._agents.get(name)

    def __len__(self) -> int:
        """Return the number of registered agents.

        Allows callers to check registry size with len(registry).
        """
        return len(self._agents)
