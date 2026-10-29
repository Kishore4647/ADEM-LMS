"""Initial LMS schema; safely adopts existing development tables."""

from alembic import op
from sqlalchemy import text

from app import models
from app.core.database import Base

revision = "0001_initial"
down_revision = None


def upgrade():
    connection = op.get_bind()
    Base.metadata.create_all(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        # The API backend uses its private database connection. No table is
        # exposed through Supabase's public/anonymous REST API.
        for table in Base.metadata.sorted_tables:
            quoted = connection.dialect.identifier_preparer.quote(table.name)
            connection.execute(text(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY"))


def downgrade():
    raise RuntimeError(
        "This baseline preserves academic records. Use a reviewed recovery migration."
    )
