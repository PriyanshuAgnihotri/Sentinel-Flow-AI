import pytest

from app.services.workflow_lifecycle import WorkflowLifecycle


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "running"),
        ("pending", "blocked"),
        ("pending", "failed"),
        ("running", "completed"),
        ("running", "approval_required"),
        ("running", "blocked"),
        ("running", "failed"),
        ("approval_required", "completed"),
        ("approval_required", "failed"),
    ],
)
def test_valid_transition(current, target):
    assert WorkflowLifecycle.can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "completed"),
        ("completed", "running"),
        ("completed", "failed"),
        ("blocked", "running"),
        ("failed", "completed"),
        ("unknown", "running"),
        ("running", "unknown"),
    ],
)
def test_invalid_transition(current, target):
    assert not WorkflowLifecycle.can_transition(current, target)

    with pytest.raises(ValueError, match="Invalid workflow lifecycle transition"):
        WorkflowLifecycle.validate_transition(current, target)
