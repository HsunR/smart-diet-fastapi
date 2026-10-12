from datetime import date
from pydantic import BaseModel

from app.schemas.base import CamelModel


class WeeklyReportResponse(CamelModel):
    """周饮食报告响应 VO。"""
    week_start: date  # 报告统计周期的开始日期。
    week_end: date  # 报告统计周期的结束日期。
    total_meals: int  # 本周已记录的餐数。
    avg_score: float  # 本周平均健康评分。
    score_trend: list  # 按日期汇总的评分趋势数据。
    report: str = ""  # 面向用户的文字总结。
