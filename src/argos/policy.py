"""Future effectful adapters must pass through this same policy."""
from dataclasses import dataclass

from .models import ArgosError
from .security import fingerprint


@dataclass(frozen=True)
class Operation:
    name: str
    arguments: dict
    project: str | None
    effect: str = "read"

    @property
    def fingerprint(self):
        return fingerprint(self.name, {**self.arguments, "_effect": self.effect}, self.project)


class Policy:
    def __init__(self):
        # Process-scoped and single-use: restarts invalidate outstanding authority.
        self._approved = set()

    def approve(self, operation: Operation, displayed_fingerprint: str):
        if operation.fingerprint != displayed_fingerprint:
            raise ArgosError("La operación ha cambiado. La aprobación ya no es válida.")
        self._approved.add(operation.fingerprint)

    def authorize(self, operation: Operation):
        if operation.effect in ("read", "routine"):
            return
        if operation.fingerprint not in self._approved:
            raise ArgosError("Esta operación requiere una aprobación concreta.")
        self._approved.remove(operation.fingerprint)

    def is_approved(self, operation):
        return operation.effect in ("read", "routine") or operation.fingerprint in self._approved


class ApprovalNeeded(ArgosError):
    def __init__(self, pending):
        self.pending = pending
        super().__init__("La operación está preparada y necesita aprobación.")
