"""课程提醒插件 - 数据持久化与本地课表文件管理。

- 绑定信息存放在 AstrBot 插件数据目录的 bindings.json；
- 课表 .ics 文件直接读取本地文件夹（ics_dir，可在插件配置中指定），
  插件只读文件、不依赖用户上传；
- 支持按文件名自动匹配用户（文件名以用户 ID 开头，如 `123456.ics`）。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from .course_types import UserBinding


class CourseStorage:
    def __init__(self, base_dir: Path, ics_dir: Path):
        self._base_dir = Path(base_dir)
        self.ics_dir = Path(ics_dir)
        self._bindings_file = self._base_dir / "bindings.json"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self.ics_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 本地课表文件
    # ------------------------------------------------------------------
    def list_ics_files(self) -> List[str]:
        """列出课表文件夹中的所有 .ics 文件名（按名称排序）。"""
        if not self.ics_dir.exists():
            return []
        return sorted(
            f.name
            for f in self.ics_dir.iterdir()
            if f.is_file() and f.name.lower().endswith(".ics")
        )

    def ics_abs_path(self, binding: UserBinding) -> Path:
        """根据绑定记录解析课表文件的绝对路径。"""
        return (self.ics_dir / binding.ics_file).resolve()

    def get_sample_ics_path(self, user_id: str) -> Path:
        """示例课表文件的路径（以用户 ID 命名，便于自动匹配）。"""
        return self.ics_dir / f"sample_{user_id}.ics"

    def find_auto_file(self, user_id: str) -> Optional[str]:
        """查找可以自动匹配到该用户的课表文件。

        规则：文件名（不含扩展名）等于用户 ID，或以「用户ID_/-」开头。
        例如 123456.ics、123456_我的课表.ics。
        """
        prefix = str(user_id)
        for f in self.list_ics_files():
            stem = f[:-4] if f.lower().endswith(".ics") else f
            if stem == prefix or stem.startswith(prefix + "_") or stem.startswith(
                prefix + "-"
            ):
                return f
        return None

    # ------------------------------------------------------------------
    # 绑定记录
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_ics_file(raw: str) -> str:
        """兼容旧版本数据：旧的 ics_file 是相对路径（如 ics/123.ics），只取文件名。"""
        name = str(raw or "").replace("\\", "/").split("/")[-1]
        return name

    def load_bindings(self) -> Dict[str, UserBinding]:
        if not self._bindings_file.exists():
            return {}
        try:
            raw = json.loads(self._bindings_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

        bindings: Dict[str, UserBinding] = {}
        for user_id, item in raw.get("bindings", {}).items():
            if not isinstance(item, dict):
                continue
            bindings[user_id] = UserBinding(
                user_id=user_id,
                unified_msg_origin=str(item.get("unified_msg_origin", "")),
                nickname=str(item.get("nickname", "")),
                ics_file=self._normalize_ics_file(item.get("ics_file", "")),
                updated_at_ts=float(item.get("updated_at_ts", 0.0)),
                enable_daily_push=bool(item.get("enable_daily_push", False)),
                daily_push_time=str(item.get("daily_push_time", "07:00")),
                reminder_advance_minutes=int(
                    item.get("reminder_advance_minutes", 15)
                ),
                daily_push_job_id=str(item.get("daily_push_job_id", "")),
            )
        return bindings

    def save_bindings(self, bindings: Dict[str, UserBinding]) -> None:
        payload = {
            "version": 2,
            "updated_at_ts": time.time(),
            "bindings": {uid: asdict(b) for uid, b in bindings.items()},
        }
        try:
            self._bindings_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def get_binding(self, user_id: str) -> Optional[UserBinding]:
        return self.load_bindings().get(user_id)

    def upsert_binding(
        self,
        *,
        user_id: str,
        unified_msg_origin: str,
        nickname: str,
        ics_file: str,
    ) -> UserBinding:
        """创建或更新绑定（保留原有个性化设置）。"""
        bindings = self.load_bindings()
        prev = bindings.get(user_id)
        binding = UserBinding(
            user_id=user_id,
            unified_msg_origin=unified_msg_origin,
            nickname=nickname,
            ics_file=self._normalize_ics_file(ics_file),
            updated_at_ts=time.time(),
            enable_daily_push=prev.enable_daily_push if prev else False,
            daily_push_time=prev.daily_push_time if prev else "07:00",
            reminder_advance_minutes=(
                prev.reminder_advance_minutes if prev else 15
            ),
            daily_push_job_id=prev.daily_push_job_id if prev else "",
        )
        bindings[user_id] = binding
        self.save_bindings(bindings)
        return binding

    def delete_binding(self, user_id: str) -> bool:
        """解除绑定（仅删除绑定记录，不删除本地课表文件）。"""
        bindings = self.load_bindings()
        if user_id not in bindings:
            return False
        bindings.pop(user_id)
        self.save_bindings(bindings)
        return True


def pick_ics_file(files: List[str], name: str) -> Optional[str]:
    """在文件列表中按用户输入选择文件。

    优先精确匹配（忽略大小写与扩展名），否则做包含匹配；
    匹配结果唯一时返回，否则返回 None（存在歧义）。
    """
    target = str(name).strip().lower()
    if not target:
        return None
    if not target.endswith(".ics"):
        target += ".ics"

    exact = [f for f in files if f.lower() == target]
    if exact:
        return exact[0]

    contains = [f for f in files if target in f.lower()]
    if len(contains) == 1:
        return contains[0]
    return None
