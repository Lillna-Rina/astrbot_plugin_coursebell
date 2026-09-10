"""课铃（CourseBell）插件 - 指令参数解析（不依赖 astrbot 运行时，便于测试）。

包含：
- 倒计时参数解析（名称 / 日期 / 通知方式 / 通知时间）；
- 调休映射参数解析（源日期 = 目标日期，或 = 放假）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from .schedule_engine import normalize_map_date

SHANGHAI_TZ = timezone(timedelta(hours=8))

# 通知方式关键字 → 内部模式
COUNTDOWN_MODES = {
    "每日": "daily",
    "每天": "daily",
    "日": "daily",
    "daily": "daily",
    "每周": "weekly",
    "每星期": "weekly",
    "周": "weekly",
    "weekly": "weekly",
    "关闭": "off",
    "不通知": "off",
    "off": "off",
    "none": "off",
}

MODE_TEXT = {"daily": "每日通知", "weekly": "每周通知", "off": "不通知"}


def normalize_date_arg(raw: str) -> Optional[str]:
    """把倒计时日期规范化为 YYYY-MM-DD。

    接受 2026-12-26、2026/12/26、2026.12.26、12-26
    （只写月日时自动补年份：若今年已过则用明年）。
    """
    s = str(raw or "").strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    parts = [p for p in s.split("-") if p]
    try:
        if len(parts) == 3:
            y, m, d = (int(p) for p in parts)
        elif len(parts) == 2:
            m, d = (int(p) for p in parts)
            today = datetime.now(SHANGHAI_TZ).date()
            y = today.year
            if date(y, m, d) < today:
                y += 1
        else:
            return None
        return date(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_time_arg(raw: str) -> Optional[str]:
    """解析 HH:MM 或 HH 形式的时间，返回规范化 HH:MM。"""
    s = str(raw or "").strip().replace("：", ":")
    if not s:
        return None
    if ":" not in s:
        if s.isdigit() and len(s) <= 2 and 0 <= int(s) <= 23:
            return f"{int(s):02d}:00"
        return None
    hh, _, mm = s.partition(":")
    if not (hh.isdigit() and mm.isdigit()):
        return None
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def parse_countdown_args(raw: str) -> Optional[Tuple[str, str, str, str]]:
    """解析 /设置倒计时 的参数。

    格式：<名称> <日期> [每日|每周|关闭] [HH:MM]
    返回 (name, date_str, mode, push_time)；格式错误返回 None。
    """
    tokens = str(raw or "").split()
    if len(tokens) < 2:
        return None
    name = tokens[0].strip()
    date_str = normalize_date_arg(tokens[1])
    if not name or date_str is None:
        return None
    mode = "daily"
    push_time = "08:00"
    for tok in tokens[2:]:
        key = tok.strip().lower()
        if key in COUNTDOWN_MODES:
            mode = COUNTDOWN_MODES[key]
            continue
        parsed_time = normalize_time_arg(tok)
        if parsed_time:
            push_time = parsed_time
    return name, date_str, mode, push_time


def parse_date_map_args(raw: str) -> Dict[str, str]:
    """解析 /设置调休 的参数，返回 {源日期 MM-DD: 目标日期 MM-DD 或 "off"}。

    支持 `09-27=10-07`、`10-07=放假`，可用空格/逗号分隔一次设置多条；
    也支持空格分隔形式 `09-27 10-07`。
    """
    text = str(raw or "").replace("，", " ").replace(",", " ").strip()
    result: Dict[str, str] = {}
    if not text:
        return result

    if "=" in text or "＝" in text:
        text = text.replace("＝", "=")
        for chunk in text.split():
            if "=" not in chunk:
                continue
            src, _, dst = chunk.partition("=")
            src_key = normalize_map_date(src)
            if src_key is None or src_key == "off":
                continue
            dst_val = normalize_map_date(dst)
            if dst_val is None:
                continue
            result[src_key] = dst_val
        return result

    tokens = text.split()
    if len(tokens) >= 2 and len(tokens) % 2 == 0:
        for i in range(0, len(tokens), 2):
            src_key = normalize_map_date(tokens[i])
            dst_val = normalize_map_date(tokens[i + 1])
            if src_key is None or src_key == "off" or dst_val is None:
                continue
            result[src_key] = dst_val
    return result


def pretty_md(value: str) -> str:
    """把 MM-DD 显示为「9月27日」；off 显示为「放假」。"""
    if normalize_map_date(value) == "off":
        return "放假"
    try:
        return f"{int(value[:2])}月{int(value[3:])}日"
    except (ValueError, IndexError):
        return str(value)
