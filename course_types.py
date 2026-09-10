"""课铃（CourseBell）插件 - 数据模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


@dataclass(frozen=True)
class CourseEvent:
    """一节具体的课程（已展开为单次实例）。"""

    summary: str
    start_time: datetime
    end_time: datetime
    location: str = ""
    description: str = ""
    week_no: int = 0  # 校历周次（以学期第一周周一为第 1 周）；0 表示未知

    def reminder_key(self) -> str:
        """生成用于提醒去重的唯一键。"""
        return "|".join(
            [
                self.start_time.isoformat(),
                self.end_time.isoformat(),
                self.summary,
                self.location,
            ]
        )


@dataclass
class Countdown:
    """一个日期倒计时（如考研倒计时）。"""

    name: str
    date: str  # 目标日期 YYYY-MM-DD
    mode: str = "daily"  # daily=每日通知 / weekly=每周通知 / off=不通知
    push_time: str = "08:00"  # 通知时间 HH:MM

    def days_left(self, today) -> int:
        """距离目标日期的天数（0=今天，负数=已过）。"""
        try:
            target = datetime.strptime(self.date, "%Y-%m-%d").date()
        except ValueError:
            return 0
        return (target - today).days


@dataclass
class UserBinding:
    """一个用户与课表的绑定关系及个性化设置。"""

    user_id: str
    unified_msg_origin: str
    nickname: str
    ics_file: str
    updated_at_ts: float
    # 以下为可配置项
    enable_daily_push: bool = False
    daily_push_time: str = "07:00"  # 格式 HH:MM（24 小时制）
    reminder_advance_minutes: int = 15  # 课前提前提醒分钟数
    daily_push_job_id: str = ""  # 已注册的 cron 任务 id
    # 调休映射：{"09-27": "10-07"} 表示 9月27日按 10月7日 的课表上课；
    # 值 "off"/"放假" 表示当天放假无课
    date_map: Dict[str, str] = field(default_factory=dict)
    # 日期倒计时列表（如考研倒计时）
    countdowns: List[Countdown] = field(default_factory=list)
    # 倒计时推送任务 id：{倒计时名称: job_id}
    countdown_job_ids: Dict[str, str] = field(default_factory=dict)

    def get_countdown(self, name: str):
        """按名称查找倒计时（忽略大小写与空格）。"""
        key = str(name or "").strip().lower()
        for c in self.countdowns:
            if c.name.strip().lower() == key:
                return c
        return None
