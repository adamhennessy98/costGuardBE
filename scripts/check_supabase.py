"""Quick check of what exists in the Supabase database."""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Check enums
    r = conn.execute(text(
        "SELECT typname FROM pg_type WHERE typname IN "
        "('anomaly_type', 'anomaly_severity', 'anomaly_status')"
    ))
    print("Existing enums:", [row[0] for row in r])

    # Check tables
    r = conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ))
    print("Existing tables:", [row[0] for row in r])

    # Check alembic version
    try:
        r = conn.execute(text("SELECT version_num FROM alembic_version"))
        print("Alembic version:", [row[0] for row in r])
    except Exception:
        print("Alembic version table: does not exist")
