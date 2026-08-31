"""课铃（CourseBell）插件 - 示例课表生成器。

用于测试：生成一份包含固定每周课程 + 一节"即将开始"课程的 .ics 文件。
绑定后即可体验课前提醒与每日推送功能。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from icalendar import Calendar, Event

SHANGHAI_TZ = timezone(timedelta(hours=8))

# 固定课程：(周一偏移 0-6, 开始时间 HH:MM, 时长分钟, 课程名, 地点)
_FIXED_COURSES: List[Tuple[int, str, int, str, str]] = [
    (0, "09:00", 100, "高等数学", "教1-101"),
    (0, "14:00", 100, "大学英语", "教2-203"),
    (1, "08:00", 100, "线性代数", "教1-205"),
    (1, "10:10", 100, "数据结构", "实验楼A-301"),
    (2, "09:00", 100, "大学物理", "教3-102"),
    (2, "13:30", 90, "体育", "田径场"),
    (3, "10:10", 100, "操作系统", "教1-303"),
    (3, "15:10", 100, "毛概", "教2-105"),
    (4, "09:00", 100, "计算机网络", "实验楼B-202"),
    (4, "14:00", 100, "概率论", "教1-401"),
]


def _build_fixed_event(
    start: datetime, minutes: int, summary: str, location: str
) -> Event:
    event = Event()
    event.add("summary", summary)
    event.add("location", location)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(minutes=minutes))
    event.add("description", "示例课程（由课铃（CourseBell）插件生成）")
    return event


def build_sample_ics(now: datetime | None = None) -> str:
    """生成示例课表 ICS 文本。

    包含：
    1. 每周固定课程（周一至周五），重复 26 周；
    2. 一节 20 分钟后开始的临时课程（仅当天），用于体验课前提醒。
    """
    if now is None:
        now = datetime.now(SHANGHAI_TZ)

    cal = Calendar()
    cal.add("prodid", "-//CourseBell//Sample//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "示例课表")
    cal.add("x-wr-timezone", "Asia/Shanghai")

    # --- 固定每周课程（RRULE 重复） ---
    this_week_monday = now.date() - timedelta(days=now.weekday())
    for weekday, time_str, minutes, name, location in _FIXED_COURSES:
        hour, minute = map(int, time_str.split(":"))
        first_start = datetime(
            this_week_monday.year,
            this_week_monday.month,
            this_week_monday.day,
            hour,
            minute,
            tzinfo=SHANGHAI_TZ,
        ) + timedelta(days=weekday)

        event = Event()
        event.add("summary", name)
        event.add("location", location)
        event.add("dtstart", first_start)
        event.add("dtend", first_start + timedelta(minutes=minutes))
        event.add("rrule", {"freq": "weekly", "count": 26})
        event.add("description", "示例固定课程")
        cal.add_component(event)

    # --- 临时测试课：20 分钟后开始 ---
    test_start = now + timedelta(minutes=20)
    cal.add_component(
        _build_fixed_event(
            test_start,
            45,
            "课铃测试课",
            "测试楼-T101",
        )
    )

    return cal.to_ical().decode("utf-8")
