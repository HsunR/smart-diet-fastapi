"""add database comments

Revision ID: e3c7d1f9a852
Revises: d7e1a6b4f523
Create Date: 2026-10-12
"""

from alembic import op


revision = "e3c7d1f9a852"
down_revision = "d7e1a6b4f523"
branch_labels = None
depends_on = None


COMMENTS = {
    "users": {
        None: "用户表：登录身份、个人资料与饮食偏好",
        "id": "用户主键", "openid": "微信身份标识；网页用户使用系统生成的兼容值",
        "account": "网页端登录账号", "password_hash": "密码哈希，绝不保存明文密码",
        "nickname": "用户展示昵称", "avatar": "头像图片 URL", "gender": "性别编码",
        "age": "年龄，单位：岁", "height": "身高，单位：厘米", "weight": "体重，单位：千克",
        "activity_level": "日常活动等级", "goal": "饮食目标：减脂、保持或增肌",
        "preferences": "饮食偏好标签列表", "allergies": "过敏原或忌口列表",
        "created_at": "创建时间，UTC", "updated_at": "最后更新时间，UTC",
    },
    "food_records": {
        None: "饮食记录表：餐食图片、用户评价与食物明细",
        "id": "饮食记录主键", "user_id": "所属用户，关联 users.id", "date": "实际就餐日期",
        "meal_type": "餐次类型：早餐、午餐、晚餐或其他", "name": "用户填写的饮食名称",
        "description": "用户填写的饮食描述，可为空", "positive_tags": "用户认为这餐好的标签列表",
        "negative_tags": "用户不喜欢这餐的标签列表", "price": "餐费金额，可为空",
        "foods": "食物明细，兼容 AI 识别及报表统计", "meal_overview": "餐食概览、健康分和建议等扩展信息",
        "image_url": "上传餐食图片的 MinIO 访问地址", "rating": "用户星级评分，0 表示尚未评分",
        "created_at": "创建时间，UTC", "updated_at": "最后更新时间，UTC",
    },
    "conversations": {
        None: "会话表：归档用户与 AI 的对话上下文",
        "id": "会话主键", "user_id": "会话所属用户，关联 users.id", "title": "会话展示标题",
        "created_at": "创建时间，UTC", "updated_at": "最后更新时间，UTC",
    },
    "messages": {
        None: "消息表：保存用户或 AI 在会话中的单条消息",
        "id": "消息主键", "conversation_id": "所属会话，关联 conversations.id",
        "role": "消息角色，例如 user 或 assistant", "content": "消息正文",
        "metadata": "消息附加元数据", "created_at": "创建时间，UTC",
    },
}


def _quote(value: str) -> str:
    return value.replace("'", "''")


def upgrade() -> None:
    for table, column_comments in COMMENTS.items():
        for column, comment in column_comments.items():
            if column is None:
                op.execute(f"COMMENT ON TABLE {table} IS '{_quote(comment)}'")
            else:
                op.execute(f"COMMENT ON COLUMN {table}.{column} IS '{_quote(comment)}'")


def downgrade() -> None:
    for table, column_comments in COMMENTS.items():
        for column in column_comments:
            if column is None:
                op.execute(f"COMMENT ON TABLE {table} IS NULL")
            else:
                op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
