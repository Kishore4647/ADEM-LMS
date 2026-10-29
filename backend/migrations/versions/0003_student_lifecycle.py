"""Add school-managed student lifecycle and academic-year history."""

import sqlalchemy as sa
from alembic import op

revision = "0003_student_lifecycle"
down_revision = "0002_exam_unique"


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("student_profiles")}
    if "section" not in columns:
        op.add_column("student_profiles", sa.Column("section", sa.String(40), nullable=True))
    if "academic_year" not in columns:
        op.add_column(
            "student_profiles", sa.Column("academic_year", sa.String(20), nullable=True)
        )
    if "status" not in columns:
        op.add_column(
            "student_profiles",
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        )
    if "retain_next_year" not in columns:
        op.add_column(
            "student_profiles",
            sa.Column(
                "retain_next_year",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("student_profiles")
    }
    if "uq_school_admission" not in constraints:
        op.create_unique_constraint(
            "uq_school_admission",
            "student_profiles",
            ["school_id", "admission_number"],
        )
    if "student_enrollments" not in inspector.get_table_names():
        op.create_table(
            "student_enrollments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "student_id",
                sa.Integer(),
                sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("academic_year", sa.String(20), nullable=False),
            sa.Column(
                "class_node_id",
                sa.Integer(),
                sa.ForeignKey("curriculum_nodes.id"),
                nullable=False,
            ),
            sa.Column("section", sa.String(40), nullable=False),
            sa.Column("outcome", sa.String(20), nullable=False, server_default="active"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "student_id", "academic_year", name="uq_student_academic_year"
            ),
        )
        op.create_index(
            "ix_student_enrollments_student_id",
            "student_enrollments",
            ["student_id"],
        )
        op.create_index(
            "ix_student_enrollments_academic_year",
            "student_enrollments",
            ["academic_year"],
        )
        op.create_index(
            "ix_student_enrollments_class_node_id",
            "student_enrollments",
            ["class_node_id"],
        )
    if connection.dialect.name == "postgresql":
        op.execute("ALTER TABLE student_enrollments ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("student_enrollments")
    op.drop_constraint("uq_school_admission", "student_profiles", type_="unique")
    op.drop_column("student_profiles", "retain_next_year")
    op.drop_column("student_profiles", "status")
    op.drop_column("student_profiles", "academic_year")
    op.drop_column("student_profiles", "section")
