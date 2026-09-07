"""课铃（CourseBell）插件 - ICS 课表解析。

将 .ics 文件解析为 CourseEvent 列表：
- 支持单次事件（DTSTART/DTEND）；
- 支持重复事件（RRULE），展开为未来一年的所有发生实例；
- 支持 EXDATE 排除日期；
- 支持课程文本中的周次范围（如「4-5周」「2-16周」「单周」「双周」），
  按校历周次过滤实例（需设置 term_start_date 或自动推断学期第一周）；
- 所有时间统一转换为上海时区（UTC+8）。
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import List, Optional, Set, Tuple

from icalendar import Calendar
from dateutil.rrule import rrulestr

from .course_types import CourseEvent

SHANGHAI_TZ = timezone(timedelta(hours=8))

# 展开重复事件的时间范围（从现在起的天数）
_EXPAND_DAYS = 365

# 课程文本中的周次范围，如「13-16周」「4-5周，7-12周」「第3周」
_WEEK_RANGE_RE = re.compile(r"(\d{1,2})(?:\s*[-–—~～]\s*(\d{1,2}))?\s*周")
# 单双周标记，如「单周」「双周」
_ODD_EVEN_RE = re.compile(r"(单|双)\s*周")


def extract_weeks(text: str) -> Optional[Set[int]]:
    """从课程文本中提取上课周次集合。

    匹配「N周」「N-M周」格式（「3-4节」这类节次不会被误匹配，因为以「节」结尾）。
    返回 None 表示文本中没有周次信息（不过滤）；否则返回允许的周次集合。
    """
    if not text:
        return None
    weeks: Set[int] = set()
    found = False
    for m in _WEEK_RANGE_RE.finditer(text):
        found = True
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a > b:
            a, b = b, a
        weeks.update(range(a, b + 1))
    if not found:
        return None
    # 单双周限制：与范围取交集
    odd_even = _ODD_EVEN_RE.findall(text)
    if odd_even:
        if "单" in odd_even:
            weeks = {w for w in weeks if w % 2 == 1}
        if "双" in odd_even:
            weeks = {w for w in weeks if w % 2 == 0}
    return weeks


class IcsParser:
    def __init__(self):
        # path -> (mtime, size, events)
        self._cache: dict[str, Tuple[float, int, List[CourseEvent]]] = {}
        # 手动设置的学期开始日期（校历第一周周一）
        self._term_start: Optional[date] = None
        # 最近一次解析实际使用的学期开始日期（手动或自动推断）
        self._last_term_start: Optional[date] = None

    def clear_cache(self, ics_path: str) -> None:
        self._cache.pop(ics_path, None)

    def set_term_start(self, term_start: Optional[date]) -> None:
        """设置学期开始日期；变更后清空解析缓存使其生效。"""
        if term_start != self._term_start:
            self._term_start = term_start
            self._cache.clear()

    @property
    def term_start(self) -> Optional[date]:
        """最近一次解析使用的学期开始日期（手动设置或自动推断）。"""
        return self._last_term_start

    def parse_ics_file(self, file_path: str) -> List[CourseEvent]:
        """解析 ICS 文件，返回按开始时间排序的课程列表（带缓存）。

        通过对比文件修改时间与大小自动检测文件变更：
        用户把新的 .ics 文件放入文件夹后无需任何操作即可读到最新课表。
        """
        try:
            stat = os.stat(file_path)
            mtime, size = stat.st_mtime, stat.st_size
        except OSError:
            return []

        cached = self._cache.get(file_path)
        if cached is not None and cached[0] == mtime and cached[1] == size:
            return cached[2]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        events = self.parse_ics_text(content)
        events.sort(key=lambda e: e.start_time)
        self._cache[file_path] = (mtime, size, events)
        return events

    def parse_ics_text(self, content: str) -> List[CourseEvent]:
        """解析 ICS 文本内容（无缓存，供测试使用）。"""
        try:
            cal = Calendar.from_ical(content)
        except Exception:
            return []

        today = datetime.now(SHANGHAI_TZ).date()
        # 学期开始日期：优先使用手动设置，否则自动推断为
        # 文件中最早课程所在周的周一（高校课表通常从学期第一周开始排课）
        term_start = self._term_start
        if term_start is None:
            earliest = self._find_earliest_start(cal)
            if earliest is not None:
                term_start = earliest - timedelta(days=earliest.weekday())
        self._last_term_start = term_start

        events: List[CourseEvent] = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            try:
                event = self._parse_vevent(component, today, term_start)
                if event:
                    events.extend(event)
            except Exception:
                # 单个事件解析失败不影响其他事件
                continue

        events.sort(key=lambda e: e.start_time)
        return events

    @staticmethod
    def _find_earliest_start(cal) -> Optional[date]:
        """找出日历中所有事件最早的 DTSTART 日期（本地时区）。"""
        earliest: Optional[date] = None
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            dtstart_raw = component.get("dtstart")
            if dtstart_raw is None:
                continue
            try:
                d = IcsParser._to_aware_local(dtstart_raw.dt).date()
            except Exception:
                continue
            if earliest is None or d < earliest:
                earliest = d
        return earliest

    def _week_no(self, day: date, term_start: Optional[date]) -> int:
        """计算日期对应的校历周次；学期开始前为 0，未知为 0。"""
        if term_start is None:
            return 0
        return (day - term_start).days // 7 + 1

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _parse_vevent(
        self, component, today: date, term_start: Optional[date]
    ) -> Optional[List[CourseEvent]]:
        summary = str(component.get("summary") or "")
        description = str(component.get("description") or "")
        location = str(component.get("location") or "")
        dtstart_raw = component.get("dtstart")
        dtend_raw = component.get("dtend")
        if not dtstart_raw or not dtend_raw:
            return None

        dtstart = self._to_aware_local(dtstart_raw.dt)
        dtend = self._to_aware_local(dtend_raw.dt)
        if dtend <= dtstart:
            return None
        duration = dtend - dtstart

        # 排除日期（EXDATE）
        excluded = self._collect_exdates(component)

        # 课程文本中的周次限制（如「4-5周」「2-16周」「单周」）
        allowed_weeks = extract_weeks(f"{summary} {description}")

        rrule = component.get("rrule")
        if rrule is not None:
            try:
                expanded = self._expand_recurring(
                    summary, description, location, dtstart, duration, rrule,
                    excluded, allowed_weeks, term_start,
                )
                return expanded
            except Exception:
                # RRULE 无法解析（如时区数据缺失导致 vBroken）时，
                # 降级为单次事件，避免整节课丢失
                pass

        # 单次事件：只保留今天及以后
        if dtstart.date() >= today and dtstart not in excluded:
            week_no = self._week_no(dtstart.date(), term_start)
            if not self._week_allowed(week_no, allowed_weeks):
                return None
            return [
                CourseEvent(
                    summary=summary,
                    description=description,
                    location=location,
                    start_time=dtstart,
                    end_time=dtend,
                    week_no=week_no,
                )
            ]
        return None

    @staticmethod
    def _week_allowed(week_no: int, allowed_weeks: Optional[Set[int]]) -> bool:
        """按校历周次过滤；无周次信息的课程不过滤。"""
        if allowed_weeks is None:
            return True
        if week_no <= 0:
            # 学期开始前的实例无法确定周次，保守丢弃
            return False
        return week_no in allowed_weeks

    @staticmethod
    def _to_aware_local(dt) -> datetime:
        """将 ICS 中的日期时间统一为带上海时区的 datetime。"""
        if isinstance(dt, date) and not isinstance(dt, datetime):
            dt = datetime.combine(dt, dt_time.min)
        if getattr(dt, "tzinfo", None):
            return dt.astimezone(SHANGHAI_TZ)
        return dt.replace(tzinfo=SHANGHAI_TZ)

    @staticmethod
    def _collect_exdates(component) -> set:
        excluded = set()
        raw = component.get("exdate")
        if raw is None:
            return excluded
        entries = raw.dts if hasattr(raw, "dts") else [raw]
        for entry in entries:
            try:
                excluded.add(IcsParser._to_aware_local(entry.dt))
            except Exception:
                continue
        return excluded

    def _expand_recurring(
        self,
        summary: str,
        description: str,
        location: str,
        dtstart: datetime,
        duration: timedelta,
        rrule,
        excluded: set,
        allowed_weeks: Optional[Set[int]] = None,
        term_start: Optional[date] = None,
    ) -> List[CourseEvent]:
        """展开 RRULE 重复事件。

        解析失败时抛出异常，由调用方降级处理。
        """
        rule_dict = rrule
        # 处理 UNTIL：转换为 UTC 的 datetime，供 rrulestr 使用
        if "UNTIL" in rule_dict:
            until_raw = rule_dict["UNTIL"]
            until_dt = until_raw[0] if isinstance(until_raw, list) else until_raw
            if isinstance(until_dt, date) and not isinstance(until_dt, datetime):
                until_dt = datetime.combine(until_dt, dt_time.max)
            until_dt = self._to_aware_local(until_dt).astimezone(timezone.utc)
            rule_dict = rule_dict.copy()
            rule_dict["UNTIL"] = [until_dt]

        rule_text = rule_dict.to_ical().decode()
        rule = rrulestr(rule_text, dtstart=dtstart.astimezone(timezone.utc))

        # 展开窗口：从今天零点（UTC）到未来 _EXPAND_DAYS 天
        now_utc = datetime.now(timezone.utc)
        window_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(days=_EXPAND_DAYS)

        events: List[CourseEvent] = []
        occurrences = rule.between(window_start, window_end, inc=True)

        for occ_utc in occurrences:
            occ_local = occ_utc.astimezone(SHANGHAI_TZ)
            if occ_local in excluded:
                continue
            week_no = self._week_no(occ_local.date(), term_start)
            if not self._week_allowed(week_no, allowed_weeks):
                continue
            events.append(
                CourseEvent(
                    summary=summary,
                    description=description,
                    location=location,
                    start_time=occ_local,
                    end_time=occ_local + duration,
                    week_no=week_no,
                )
            )
        return events
