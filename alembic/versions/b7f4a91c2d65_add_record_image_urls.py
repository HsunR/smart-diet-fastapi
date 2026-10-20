"""add multiple photos to food records

Revision ID: b7f4a91c2d65
Revises: f4a6c8e2b917
"""

from alembic import op
import sqlalchemy as sa


revision = "b7f4a91c2d65"
down_revision = "f4a6c8e2b917"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "food_records",
        sa.Column("image_urls", sa.JSON(), nullable=False, server_default=sa.text("'[]'"), comment="餐食图片地址列表，第一张为封面"),
    )
    op.execute("UPDATE food_records SET image_urls = json_build_array(image_url) WHERE image_url IS NOT NULL AND image_url <> ''")


def downgrade() -> None:
    op.drop_column("food_records", "image_urls")
