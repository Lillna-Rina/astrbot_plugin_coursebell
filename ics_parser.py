"""课铃（CourseBell）插件 - ICS 课表解析。

将 .ics 文件解析为 CourseEvent 列表：
- 支持单次事件（DTSTART/DTEND）；
- 支持重复事件（RRULE），展开为未来一年的所有发生实例；
- 支持 EXDATE 排除日期；
- 所有时间统一转换为上海时区（UTC+8）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import List, Optional, Tuple

from icalendar import Calendar
from dateutil.rrule import rrulestr

from .course_types import CourseEvent

SHANGHAI_TZ = timezone(timedelta(hours=8))

# 展开重复事件的时间范围（从现在起的天数）
_EXPAND_DAYS = 365


class IcsParser:
    def __init__(self):
        # path -> (mtime, size, events)
        self._cache: dict[str, Tuple[float, int, List[CourseEvent]]] = {}

    def clear_cache(self, ics_path: str) -> None:
        self._cache.pop(ics_path, None)

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
        events: List[CourseEvent] = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            try:
                event = self._parse_vevent(component, today)
                if event:
                    events.extend(event)
            except Exception:
                # 单个事件解析失败不影响其他事件
                continue

        events.sort(key=lambda e: e.start_time)
        return events

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _parse_vevent(
        self, component, today: date
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

        rrule = component.get("rrule")
        if rrule is not None:
            try:
                expanded = self._expand_recurring(
                    summary, description, location, dtstart, duration, rrule, excluded
                )
                return expanded
            except Exception:
                # RRULE 无法解析（如时区数据缺失导致 vBroken）时，
                # 降级为单次事件，避免整节课丢失
                pass

        # 单次事件：只保留今天及以后
        if dtstart.date() >= today and dtstart not in excluded:
            return [
                CourseEvent(
                    summary=summary,
                    description=description,
                    location=location,
                    start_time=dtstart,
                    end_time=dtend,
                )
            ]
        return None

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
            events.append(
                CourseEvent(
                    summary=summary,
                    description=description,
                    location=location,
                    start_time=occ_local,
                    end_time=occ_local + duration,
                )
            )
        return events
