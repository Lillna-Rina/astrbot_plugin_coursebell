"""课铃（CourseBell）插件 - 课表查询、调休映射与提醒命中引擎。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .course_types import CourseEvent

SHANGHAI_TZ = timezone(timedelta(hours=8))

# 调休映射中表示「放假无课」的特殊值
OFF_VALUES = {"off", "放假", "休息", "无课", "none", "-", "假"}


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


# ----------------------------------------------------------------------
# 调休映射
# ----------------------------------------------------------------------
def date_key(d: date) -> str:
    """日期的映射键（MM-DD）。"""
    return d.strftime("%m-%d")


def normalize_map_date(raw: str) -> Optional[str]:
    """把用户输入的日期规范化为 MM-DD；非法返回 None。

    接受 09-27、9-27、2026-09-27、2026/9/27 等写法；
    放假类输入（off/放假/无课）返回 "off"。
    """
    s = str(raw or "").strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    if s.lower() in OFF_VALUES:
        return "off"
    parts = s.split("-")
    if len(parts) == 3:  # YYYY-MM-DD
        parts = parts[1:]
    if len(parts) != 2:
        return None
    try:
        month, day = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{month:02d}-{day:02d}"


def resolve_effective_date(
    target: date, date_map: Optional[Dict[str, str]]
) -> Optional[date]:
    """把查询日期按调休映射转换为「实际上哪一天的课」。

    - 无映射：返回原日期；
    - 映射到某天：返回该天（如 09-27 -> 10-07 表示 9月27日 上 10月7日 的课）；
    - 映射到 off/放假：返回 None（当天无课）。
    """
    if not date_map:
        return target
    raw = date_map.get(date_key(target))
    if raw is None:
        return target
    val = normalize_map_date(raw)
    if val is None:
        return target
    if val == "off":
        return None
    month, day = (int(x) for x in val.split("-"))
    # 沿用查询日期的年份，避免跨年越界
    try:
        return date(target.year, month, day)
    except ValueError:
        return target


def date_map_note(target: date, date_map: Optional[Dict[str, str]]) -> str:
    """返回该日期的调休说明文本（无调休时为空字符串）。"""
    if not date_map:
        return ""
    raw = date_map.get(date_key(target))
    if raw is None:
        return ""
    val = normalize_map_date(raw)
    if val is None:
        return ""
    if val == "off":
        return "放假"
    return f"调休：按 {int(val[:2])}月{int(val[3:])}日 课表"


def day_events_mapped(
    events: Sequence[CourseEvent],
    target_date: date,
    date_map: Optional[Dict[str, str]] = None,
) -> List[CourseEvent]:
    """返回 target_date 当天实际要上的课（已应用调休映射）。

    映射到其他日期时，课程内容取自被映射日期，日期平移到 target_date，
    开始/结束时刻保持不变（如 9月27日 上 10月7日 09:00 的课）。
    """
    effective = resolve_effective_date(target_date, date_map)
    if effective is None:
        return []
    if effective == target_date:
        return day_events(events, target_date)

    moved: List[CourseEvent] = []
    for e in day_events(events, effective):
        start = e.start_time.astimezone(SHANGHAI_TZ)
        end = e.end_time.astimezone(SHANGHAI_TZ)
        moved.append(
            replace(
                e,
                start_time=datetime.combine(target_date, start.timetz()),
                end_time=datetime.combine(target_date, end.timetz()),
            )
        )
    moved.sort(key=lambda e: e.start_time)
    return moved


def week_events_mapped(
    events: Sequence[CourseEvent],
    target_date: date,
    date_map: Optional[Dict[str, str]] = None,
) -> Tuple[List[List[CourseEvent]], List[str]]:
    """返回一周七天每天的课程，以及每天的调休说明。"""
    start = week_start(target_date)
    days: List[List[CourseEvent]] = []
    notes: List[str] = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append(day_events_mapped(events, d, date_map))
        notes.append(date_map_note(d, date_map))
    return days, notes


def upcoming_events(
    *,
    now: datetime,
    events: Sequence[CourseEvent],
    advance_minutes: int = 15,
    date_map: Optional[Dict[str, str]] = None,
) -> List[CourseEvent]:
    """返回从现在起 advance_minutes 分钟内即将开始的课程（不含已开始的）。

    调休日的课程会被平移到当天，因此这里先按映射替换掉当天原有的课程，
    再统一比较时间，保证调休后的课也能正常提醒。
    """
    candidates: List[CourseEvent] = list(events)
    today = now.astimezone(SHANGHAI_TZ).date()
    effective = resolve_effective_date(today, date_map)
    if effective != today:
        # 今天被调休：移除今天原本的课程，加入映射后（平移）的课程
        candidates = [
            e
            for e in candidates
            if e.start_time.astimezone(SHANGHAI_TZ).date() != today
        ]
        candidates.extend(day_events_mapped(events, today, date_map))

    hits: List[CourseEvent] = []
    deadline = now + timedelta(minutes=advance_minutes)
    for e in candidates:
        if now < e.start_time <= deadline:
            hits.append(e)
    hits.sort(key=lambda e: e.start_time)
    return hits
