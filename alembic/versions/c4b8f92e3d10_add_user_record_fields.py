"""add user record fields

Revision ID: c4b8f92e3d10
Revises: a6d2cbe6f431
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "c4b8f92e3d10"
down_revision = "a6d2cbe6f431"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("food_records", sa.Column("name", sa.String(length=120), nullable=False, server_default=""))
    op.add_column("food_records", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("food_records", sa.Column("positive_tags", sa.JSON(), nullable=True))
    op.add_column("food_records", sa.Column("negative_tags", sa.JSON(), nullable=True))
    op.add_column("food_records", sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column("food_records", "price")
    op.drop_column("food_records", "negative_tags")
    op.drop_column("food_records", "positive_tags")
    op.drop_column("food_records", "description")
    op.drop_column("food_records", "name")
