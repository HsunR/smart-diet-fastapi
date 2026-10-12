"""remove unused profile and record fields

Revision ID: f4a6c8e2b917
Revises: e3c7d1f9a852
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a6c8e2b917"
down_revision = "e3c7d1f9a852"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "allergies")
    op.drop_column("users", "preferences")
    op.drop_column("users", "goal")
    op.drop_column("users", "activity_level")
    op.drop_column("food_records", "meal_overview")
    op.drop_column("food_records", "foods")


def downgrade() -> None:
    op.add_column("food_records", sa.Column("foods", sa.JSON(), nullable=True, comment="食物明细，兼容 AI 识别及报表统计"))
    op.add_column("food_records", sa.Column("meal_overview", sa.JSON(), nullable=True, comment="餐食概览、健康分和建议等扩展信息"))
    op.add_column("users", sa.Column("activity_level", sa.SmallInteger(), nullable=True, comment="日常活动等级"))
    op.add_column("users", sa.Column("goal", sa.String(length=16), nullable=True, comment="饮食目标：减脂、保持或增肌"))
    op.add_column("users", sa.Column("preferences", sa.JSON(), nullable=True, comment="饮食偏好标签列表"))
    op.add_column("users", sa.Column("allergies", sa.JSON(), nullable=True, comment="过敏原或忌口列表"))
