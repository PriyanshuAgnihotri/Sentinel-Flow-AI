from typing import ClassVar


class WorkflowLifecycle:
    """Validate workflow lifecycle state transitions."""

    PENDING: ClassVar[str] = "pending"
    RUNNING: ClassVar[str] = "running"
    COMPLETED: ClassVar[str] = "completed"
    APPROVAL_REQUIRED: ClassVar[str] = "approval_required"
    BLOCKED: ClassVar[str] = "blocked"
    FAILED: ClassVar[str] = "failed"

    TRANSITIONS: ClassVar[dict[str, frozenset[str]]] = {
        PENDING: frozenset({RUNNING, BLOCKED, FAILED}),
        RUNNING: frozenset({COMPLETED, APPROVAL_REQUIRED, BLOCKED, FAILED}),
        APPROVAL_REQUIRED: frozenset({COMPLETED, FAILED}),
        COMPLETED: frozenset(),
        BLOCKED: frozenset(),
        FAILED: frozenset(),
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        """Return whether a lifecycle transition is permitted."""
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def validate_transition(cls, current: str, target: str) -> None:
        """Raise ValueError when a transition is not permitted."""
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid workflow lifecycle transition: {current} -> {target}")
