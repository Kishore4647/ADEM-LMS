"""Read-only connectivity/migration/RLS check; never displays credentials."""

from sqlalchemy import text

from app.core.database import engine

with engine.connect() as connection:
    print("Database connected")
    print(
        "Migration:",
        connection.execute(text("select version_num from alembic_version")).scalar(),
    )
    names = [
        "users",
        "student_profiles",
        "mark_records",
        "question_sets",
        "private_files",
    ]
    from sqlalchemy import bindparam

    query = text(
        "select count(*) from pg_tables where schemaname='public' and tablename in :names and not rowsecurity"
    ).bindparams(bindparam("names", expanding=True))
    print(
        "Academic tables without RLS:",
        connection.execute(query, {"names": names}).scalar(),
    )
