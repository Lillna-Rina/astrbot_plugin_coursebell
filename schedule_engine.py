"""课程提醒插件 - 课表查询与提醒命中引擎。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Sequence

from .course_types import CourseEvent

SHANGHAI_TZ = timezone(timedelta(hours=8))


def day_events(events: Sequence[CourseEvent], target_date: date) -> List[CourseEvent]:
    """返回指定日期的全部课程（按开始时间排序）。"""
    result = [
        e for e in events if e.start_time.astimezone(SHANGHAI_TZ).date() == target_date
    ]
    result.sort(key=lambda e: e.start_time)
    return result


def week_start(d: date) -> date:
    """返回 d 所在周的周一。"""
    return d - timedelta(days=d.weekday())


def week_events(
    events: Sequence[CourseEvent], target_date: date
) -> List[List[CourseEvent]]:
    """返回 target_date 所在周（周一~周日）七天每天的课程。"""
    start = week_start(target_date)
    return [day_events(events, start + timedelta(days=i)) for i in range(7)]


def upcoming_events(
    *,
    now: datetime,
    events: Sequence[CourseEvent],
    advance_minutes: int = 15,
) -> List[CourseEvent]:
    """返回从现在起 advance_minutes 分钟内即将开始的课程（不含已开始的）。

    仅返回每个课程未来第一次出现（开始时间距今最近的一次）。
    """
    hits: List[CourseEvent] = []
    deadline = now + timedelta(minutes=advance_minutes)
    for e in events:
        if now < e.start_time <= deadline:
            hits.append(e)
    hits.sort(key=lambda e: e.start_time)
    return hits
