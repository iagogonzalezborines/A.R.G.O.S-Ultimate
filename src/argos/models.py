from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL = {Status.COMPLETED, Status.FAILED, Status.CANCELLED}


@dataclass(frozen=True)
class Decision:
    kind: str
    speech: str = ""
    agent: str = ""
    capability: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class Response:
    speech: str
    kind: str = "answer"
    task_id: str | None = None
    data: Any = None
    route: str = "local"
    language: str = "es"

    def json(self):
        return asdict(self)


class ArgosError(Exception):
    """Safe, user-facing failure. Raw provider exceptions are never persisted."""


class EscalationNeeded(ArgosError):
    """A local task requests deeper reasoning; Core alone chooses the provider."""
