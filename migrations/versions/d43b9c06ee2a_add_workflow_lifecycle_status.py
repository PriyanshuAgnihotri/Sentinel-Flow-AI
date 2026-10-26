"""add workflow lifecycle status

Revision ID: d43b9c06ee2a
Revises: d9ce7fd68851
Create Date: 2026-10-22 16:42:41.325848
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d43b9c06ee2a"
down_revision: Union[str, Sequence[str], None] = "d9ce7fd68851"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lifecycle status and backfill existing workflow runs."""
    op.add_column(
        "workflow_runs",
        sa.Column("lifecycle_status", sa.String(length=32), nullable=True),
    )

    op.execute(
        """
        UPDATE workflow_runs
        SET lifecycle_status = CASE
            WHEN result_json ->> 'lifecycle_status'
                IN ('completed', 'approval_required', 'blocked', 'failed')
            THEN result_json ->> 'lifecycle_status'
            ELSE 'completed'
        END
        """
    )

    op.alter_column(
        "workflow_runs",
        "lifecycle_status",
        existing_type=sa.String(length=32),
        nullable=False,
    )

    op.create_index(
        op.f("ix_workflow_runs_lifecycle_status"),
        "workflow_runs",
        ["lifecycle_status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the lifecycle status column and its index."""
    op.drop_index(
        op.f("ix_workflow_runs_lifecycle_status"),
        table_name="workflow_runs",
    )
    op.drop_column("workflow_runs", "lifecycle_status")
