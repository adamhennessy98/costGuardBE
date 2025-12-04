"""core tables for costguard domain

Revision ID: 20231203_0002
Revises: 20231203_0001
Create Date: 2025-12-03 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20231203_0002"
down_revision = "20231203_0001"
branch_labels = None
depends_on = None


anomaly_type_enum = sa.Enum("PRICE_CREEP", "DUPLICATE", "ABNORMAL_TOTAL", name="anomaly_type")
anomaly_severity_enum = sa.Enum("LOW", "MEDIUM", "HIGH", name="anomaly_severity")
anomaly_status_enum = sa.Enum("UNREVIEWED", "VALID", "ISSUE", name="anomaly_status")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    anomaly_type_enum.create(op.get_bind(), checkfirst=True)
    anomaly_severity_enum.create(op.get_bind(), checkfirst=True)
    anomaly_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("business_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name_normalized", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "vendors_user_normalized_name_idx",
        "vendors",
        ["user_id", "name_normalized"],
        unique=True,
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source_file_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("invoices_vendor_date_idx", "invoices", ["vendor_id", "invoice_date"], unique=False)
    op.create_index(
        "invoices_duplicate_check_idx",
        "invoices",
        ["vendor_id", "invoice_date", "total_amount"],
        unique=False,
    )

    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", anomaly_type_enum, nullable=False),
        sa.Column("severity", anomaly_severity_enum, nullable=False),
        sa.Column("status", anomaly_status_enum, server_default="UNREVIEWED", nullable=False),
        sa.Column("reason_text", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("anomalies_invoice_id_idx", "anomalies", ["invoice_id"], unique=False)
    op.create_index("anomalies_status_idx", "anomalies", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("anomalies_status_idx", table_name="anomalies")
    op.drop_index("anomalies_invoice_id_idx", table_name="anomalies")
    op.drop_table("anomalies")

    op.drop_index("invoices_duplicate_check_idx", table_name="invoices")
    op.drop_index("invoices_vendor_date_idx", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("vendors_user_normalized_name_idx", table_name="vendors")
    op.drop_table("vendors")

    op.drop_table("users")

    anomaly_status_enum.drop(op.get_bind(), checkfirst=True)
    anomaly_severity_enum.drop(op.get_bind(), checkfirst=True)
    anomaly_type_enum.drop(op.get_bind(), checkfirst=True)