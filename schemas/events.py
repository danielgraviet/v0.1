"""Agent event schema.

Events are emitted by the runtime during execution so the display layer can
update its live panels in real time. The runtime and display layer are
deliberately decoupled — the runtime works correctly whether or not anything
is listening to these events.
"""

from enum import Enum

from pydantic import BaseModel


class EventType(str, Enum):
    """The lifecycle stages an agent can emit events for.

    Extends str so values serialize to plain strings ("started", "complete")
    rather than "EventType.STARTED" — cleaner for logging and display output.

    Values:
        STARTED: Agent has begun execution.
        SIGNAL_DETECTED: Agent identified a relevant signal in its context.
        COMPLETE: Agent finished and returned a result successfully.
        ERROR: Agent raised an exception and was skipped by the executor.
    """

    STARTED = "started"
    SIGNAL_DETECTED = "signal_detected"
    COMPLETE = "complete"
    ERROR = "error"


class AgentEvent(BaseModel):
    """A single runtime event emitted during agent execution.

    The display layer subscribes to these events and uses them to update
    the live terminal panels. Events are append-only — the display layer
    never modifies or deletes them.

    Attributes:
        agent_name: Name of the agent that emitted this event. Maps to
            the panel heading in the Rich display layout.
        event_type: Lifecycle stage this event represents. See EventType
            for the full list of valid values.
        message: Human-readable description of what happened at this
            moment (e.g. "analyzing error patterns...", "sig_003 detected").
            Displayed inside the agent's panel.
        timestamp_ms: Wall-clock time when the event was emitted, in
            milliseconds since the start of the execution. Used to render
            the elapsed time shown in each panel (e.g. "[1.31s]").
    """

    agent_name: str
    event_type: EventType
    message: str
    timestamp_ms: float
