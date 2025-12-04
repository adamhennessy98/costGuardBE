"""Utility script to validate the configured database connection."""

from sqlalchemy import text

from app.db.session import SessionLocal


def main() -> None:
    """Ensure a database connection can be established and queried."""

    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    print("Database connection succeeded.")


if __name__ == "__main__":
    main()
