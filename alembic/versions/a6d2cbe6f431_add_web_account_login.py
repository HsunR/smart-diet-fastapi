"""add web account login

Revision ID: a6d2cbe6f431
Revises: 96898b889cb6
Create Date: 2026-09-21 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6d2cbe6f431"
down_revision: Union[str, None] = "96898b889cb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("account", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=128), nullable=True))
    op.create_index("ix_users_account", "users", ["account"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_account", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "account")
