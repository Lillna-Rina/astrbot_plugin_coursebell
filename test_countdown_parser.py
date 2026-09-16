#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倒计时参数解析测试脚本（独立运行，不依赖AstrBot）"""

import sys
from pathlib import Path

# 添加插件目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from command_parsers import parse_countdown_args, normalize_date_arg

# 测试用例
test_cases = [
    "考研 2026-12-26",
    "考研 2026-12-26 每日",
    "考研 2026-12-26 每日 08:00",
    "期末 2027-01-10 每周",
    "考研 12-26",
    "考研 2026/12/26",
    "测试 2026-12-26 关闭",
]

print("=" * 60)
print("倒计时参数解析测试")
print("=" * 60)

for i, test in enumerate(test_cases, 1):
    print(f"\n[测试 {i}] 输入: 「{test}」")
    result = parse_countdown_args(test)
    if result:
        name, date_str, mode, push_time = result
        print(f"  ✅ 解析成功")
        print(f"     名称: {name}")
        print(f"     日期: {date_str}")
        print(f"     模式: {mode}")
        print(f"     时间: {push_time}")
    else:
        print(f"  ❌ 解析失败")

print("\n" + "=" * 60)
print("日期格式解析测试")
print("=" * 60)

date_tests = [
    "2026-12-26",
    "2026/12/26",
    "2026.12.26",
    "12-26",
    "12/26",
    "invalid",
    "",
]

for date_input in date_tests:
    result = normalize_date_arg(date_input)
    status = "✅" if result else "❌"
    print(f"{status} 「{date_input}」 → {result}")

print("\n" + "=" * 60)
