# CostGuard Backend

FastAPI service with SQLAlchemy ORM and Alembic migrations.

## Getting Started

1. Create and activate a virtual environment if needed.
2. Install dependencies:
   ```bash
   pip install -e .[dev]
   ```
3. Copy `.env.example` to `.env` and update settings.
4. Run the database migrations:
   ```bash
   alembic upgrade head
   ```
5. Start the development server:
   ```bash
   uvicorn app.main:app --reload
   ```
