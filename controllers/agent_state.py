from __future__ import annotations

from enum import Enum, auto


class AgentState(Enum):
    IDLE = auto()
    CONFIGURING = auto()
    CALIBRATING = auto()
    READY = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()
    ERROR = auto()


class AgentStateMachine:
    VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
        AgentState.IDLE: {AgentState.CONFIGURING, AgentState.CALIBRATING, AgentState.READY},
        AgentState.CONFIGURING: {AgentState.READY, AgentState.IDLE},
        AgentState.CALIBRATING: {AgentState.READY, AgentState.IDLE},
        AgentState.READY: {AgentState.RUNNING, AgentState.CONFIGURING, AgentState.CALIBRATING},
        AgentState.RUNNING: {AgentState.PAUSED, AgentState.STOPPED, AgentState.ERROR, AgentState.READY},
        AgentState.PAUSED: {AgentState.RUNNING, AgentState.STOPPED, AgentState.ERROR},
        AgentState.STOPPED: {AgentState.READY, AgentState.IDLE},
        AgentState.ERROR: {AgentState.IDLE, AgentState.READY},
    }

    def __init__(self, initial: AgentState = AgentState.IDLE) -> None:
        self._state = initial

    @property
    def state(self) -> AgentState:
        return self._state

    def can_transition(self, target: AgentState) -> bool:
        return target in self.VALID_TRANSITIONS.get(self._state, set())

    def transition(self, target: AgentState) -> None:
        if not self.can_transition(target):
            raise ValueError(f"Invalid transition: {self._state.name} -> {target.name}")
        self._state = target
