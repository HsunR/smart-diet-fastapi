"""initial_schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-27 10:34:09.499226

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False, comment='用户主键'),
    sa.Column('openid', sa.String(length=128), nullable=True, comment='微信身份标识；网页账号为空'),
    sa.Column('account', sa.String(length=32), nullable=True, comment='网页端登录账号'),
    sa.Column('password_hash', sa.String(length=128), nullable=True, comment='密码哈希，绝不保存明文密码'),
    sa.Column('nickname', sa.String(length=64), nullable=True, comment='用户展示昵称'),
    sa.Column('avatar', sa.String(length=512), nullable=True, comment='头像图片 URL'),
    sa.Column('gender', sa.SmallInteger(), nullable=True, comment='性别：0 未设置，其他值由前端约定'),
    sa.Column('age', sa.SmallInteger(), nullable=True, comment='年龄，单位：岁'),
    sa.Column('height', sa.Numeric(precision=5, scale=1), nullable=True, comment='身高，单位：厘米'),
    sa.Column('weight', sa.Numeric(precision=5, scale=1), nullable=True, comment='体重，单位：千克'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, comment='创建时间，UTC'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='最后更新时间，UTC'),
    sa.PrimaryKeyConstraint('id'),
    comment='用户表：登录身份、个人资料与饮食偏好'
    )
    op.create_index(op.f('ix_users_account'), 'users', ['account'], unique=True)
    op.create_index(op.f('ix_users_openid'), 'users', ['openid'], unique=True)
    op.create_table('food_records',
    sa.Column('id', sa.Uuid(), nullable=False, comment='饮食记录主键'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='所属用户，关联 users.id'),
    sa.Column('date', sa.Date(), nullable=False, comment='实际就餐日期'),
    sa.Column('meal_type', sa.String(length=16), nullable=False, comment='餐次类型：早餐、午餐、晚餐或其他'),
    sa.Column('name', sa.String(length=120), nullable=False, comment='用户填写的饮食名称'),
    sa.Column('description', sa.Text(), nullable=False, comment='用户填写的饮食描述，可为空'),
    sa.Column('positive_tags', sa.JSON(), nullable=True, comment='用户认为这餐好的标签列表'),
    sa.Column('negative_tags', sa.JSON(), nullable=True, comment='用户不喜欢这餐的标签列表'),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=True, comment='餐费金额，可为空'),
    sa.Column('image_urls', sa.JSON(), nullable=False, comment='餐食图片地址列表，第一张为封面'),
    sa.Column('rating', sa.Integer(), nullable=True, comment='用户星级评分，0 表示尚未评分'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, comment='创建时间，UTC'),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='最后更新时间，UTC'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    comment='饮食记录表：餐食图片、用户评价与食物明细'
    )
    op.create_index(op.f('ix_food_records_user_id'), 'food_records', ['user_id'], unique=False)
    op.create_table('uploaded_images',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('object_name', sa.String(length=512), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('object_name')
    )
    op.create_index(op.f('ix_uploaded_images_user_id'), 'uploaded_images', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_uploaded_images_user_id'), table_name='uploaded_images')
    op.drop_table('uploaded_images')
    op.drop_index(op.f('ix_food_records_user_id'), table_name='food_records')
    op.drop_table('food_records')
    op.drop_index(op.f('ix_users_openid'), table_name='users')
    op.drop_index(op.f('ix_users_account'), table_name='users')
    op.drop_table('users')
