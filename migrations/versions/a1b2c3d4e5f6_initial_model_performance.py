"""Initial migration: create model_performance table.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-07-15
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "model_performance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("drift_alert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_performance_shop_id", "model_performance", ["shop_id"])
    op.create_index("ix_model_performance_product_id", "model_performance", ["product_id"])
    op.create_index("ix_model_performance_model_name", "model_performance", ["model_name"])
    op.create_index("ix_model_performance_recorded_at", "model_performance", ["recorded_at"])
    op.create_unique_constraint(
        "uq_model_perf_shop_product_model_time",
        "model_performance",
        ["shop_id", "product_id", "model_name", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_table("model_performance")
