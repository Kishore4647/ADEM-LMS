"""Enforce one quarterly exam per student, subject, and period at database level."""

from alembic import op
from sqlalchemy import text

revision = "0002_exam_unique"
down_revision = "0001_initial"


def upgrade():
    op.create_index(
        "uq_subject_quarter_exam",
        "mark_records",
        ["student_id", "subject_node_id", "academic_period"],
        unique=True,
        postgresql_where=text("component = 'QUARTERLY_EXAM'"),
        sqlite_where=text("component = 'QUARTERLY_EXAM'"),
    )


def downgrade():
    op.drop_index("uq_subject_quarter_exam", table_name="mark_records")
