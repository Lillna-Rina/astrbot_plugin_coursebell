"""课铃（CourseBell）插件 - 数据模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
