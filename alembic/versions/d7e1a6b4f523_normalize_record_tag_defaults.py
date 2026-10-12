"""normalize record tag defaults

Revision ID: d7e1a6b4f523
Revises: c4b8f92e3d10
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "d7e1a6b4f523"
down_revision = "c4b8f92e3d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE food_records SET positive_tags = '[]'::json WHERE positive_tags IS NULL")
    op.execute("UPDATE food_records SET negative_tags = '[]'::json WHERE negative_tags IS NULL")
    op.alter_column("food_records", "positive_tags", nullable=False, server_default=sa.text("'[]'::json"))
    op.alter_column("food_records", "negative_tags", nullable=False, server_default=sa.text("'[]'::json"))


def downgrade() -> None:
    op.alter_column("food_records", "negative_tags", nullable=True, server_default=None)
    op.alter_column("food_records", "positive_tags", nullable=True, server_default=None)
