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

## Invoice File Uploads

- API endpoint `POST /api/invoices/` accepts either JSON payloads or multipart form-data with a `metadata` field (JSON string) and optional `file`. Uploaded files are stored under `storage/invoices/` by default; update `INVOICE_STORAGE_DIR` in `.env` to change the location.
- When a file is uploaded, the backend runs a stub extraction pass (see `app/services/invoice_extractor.py`) that can pull `vendor_name`, `invoice_date`, and `total_amount` from simple JSON or text files. Missing fields in the metadata are filled from the extracted values when possible.
