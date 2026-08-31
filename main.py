"""课铃（CourseBell）—— AstrBot 课程提醒插件（Star）。

课表来源：直接读取本地文件夹中的 .ics 文件（不依赖用户上传）。
- 文件夹路径可在插件配置（_conf_schema.json 的 ics_dir）中指定，
  留空时使用插件数据目录下的 ics 文件夹；
- /绑定课表 [文件名]：选择文件夹中的课表文件完成绑定；
- 文件名以用户 ID 开头的文件（如 123456.ics）可自动匹配，无需手动绑定；
- 文件变更自动检测：把新课表文件放入文件夹即可，无需任何操作。

功能：
- /今日课表 /明日课表 /本周课表 /下周课表：查询课表（渲染为竖屏图片，失败时降级为文本）
- 课前提醒：每 60 秒扫描，课程开始前自动发送提醒
- /设置每日推送：每日定时推送当日课表
- /设置提醒时间 /查看设置 /删除课表 /课表文件 /课表帮助
- /示例课表：生成一份示例课表文件并绑定，便于快速体验
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.io import download_file
from astrbot.core.utils.session_waiter import SessionController, session_waiter

from .course_types import CourseEvent, UserBinding
from .ics_parser import IcsParser, SHANGHAI_TZ
from .render_templates import DAY_TMPL, WEEK_TMPL
from .sample_ics import build_sample_ics
from .schedule_engine import day_events, week_events, week_start, upcoming_events
from .storage import CourseStorage, pick_ics_file

PLUGIN_NAME = "astrbot_plugin_coursebell"
PLUGIN_DISPLAY_NAME = "课铃"
WEEK_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 会话等待超时（秒）
_BIND_TIMEOUT = 120


@register(
    PLUGIN_NAME,
    "Lillna-Rina",
    "课铃：直接读取本地文件夹中的课表文件，可查看今日、明日、本周及下周的课表（竖屏图片），支持课前提醒与每日定时推送课表。",
    "1.3.0",
)
class CourseBellPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self._context = context
        plugin_name = getattr(self, "name", None) or PLUGIN_NAME
        self._config = config or {}
        self._base_dir = StarTools.get_data_dir(plugin_name)
        self._storage = CourseStorage(self._base_dir, self._resolve_ics_dir())
        self._parser = IcsParser()

        self._reminded: Dict[str, Set[str]] = {}
        self._stop_event = asyncio.Event()
        self._reminder_task: Optional[asyncio.Task] = None
        self._init_lock = asyncio.Lock()

    def _resolve_ics_dir(self) -> Path:
        """根据插件配置解析课表文件夹路径。

        配置 ics_dir 为空时，使用插件数据目录下的 ics 文件夹。
        支持绝对路径、~ 开头的用户目录路径，以及相对 AstrBot 运行目录的路径。
        """
        configured = str(self._config.get("ics_dir") or "").strip()
        if configured:
            return Path(configured).expanduser()
        return self._base_dir / "ics"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def initialize(self):
        async with self._init_lock:
            logger.info(f"[coursebell] initializing... ics_dir={self._storage.ics_dir}")
            if self._storage.migrated_from_legacy:
                logger.info("[coursebell] migrated legacy data from astrbot_plugin_course_reminder")
            if self._storage.ics_dir_fallback_reason:
                logger.warning(
                    f"[coursebell] configured ics_dir unavailable, using fallback dir: "
                    f"{self._storage.ics_dir_fallback_reason}"
                )
            if self._reminder_task is not None and not self._reminder_task.done():
                self._stop_event.set()
                self._reminder_task.cancel()
                try:
                    await asyncio.wait_for(self._reminder_task, timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception as e:
                    logger.warning(f"[coursebell] error cancelling old task: {e}")
            self._reminded.clear()
            self._stop_event.clear()
            self._reminder_task = asyncio.create_task(self._reminder_loop())
            logger.info("[coursebell] reminder loop started")

        # 恢复所有用户的每日推送定时任务
        for user_id, binding in self._storage.load_bindings().items():
            if binding.enable_daily_push and binding.daily_push_time:
                try:
                    await self._register_user_cron(user_id, binding.daily_push_time)
                except Exception as e:
                    logger.error(f"[coursebell] restore cron failed for {user_id}: {e}")

    async def terminate(self):
        logger.info("[coursebell] terminating...")
        self._stop_event.set()
        if self._reminder_task is not None:
            if not self._reminder_task.done():
                self._reminder_task.cancel()
                try:
                    await asyncio.wait_for(self._reminder_task, timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception as e:
                    logger.warning(f"[coursebell] error cancelling task: {e}")
            self._reminder_task = None
        self._reminded.clear()
        logger.info("[coursebell] terminated")

    # ------------------------------------------------------------------
    # 绑定解析
    # ------------------------------------------------------------------
    def _resolve_binding(
        self, user_id: str, event: AstrMessageEvent | None = None
    ) -> Optional[UserBinding]:
        """获取用户绑定；未绑定时尝试按文件名自动匹配并固化绑定。

        自动匹配：文件夹中存在以「用户ID」开头的 .ics 文件
        （如 123456.ics、123456_我的课表.ics）。
        """
        binding = self._storage.get_binding(user_id)
        if binding:
            return binding
        auto_file = self._storage.find_auto_file(user_id)
        if auto_file and event is not None:
            try:
                self._storage.upsert_binding(
                    user_id=user_id,
                    unified_msg_origin=event.unified_msg_origin,
                    nickname=str(event.get_sender_name()),
                    ics_file=auto_file,
                )
                logger.info(f"[coursebell] auto bound {user_id} -> {auto_file}")
                return self._storage.get_binding(user_id)
            except Exception as e:
                logger.warning(f"[coursebell] auto bind failed for {user_id}: {e}")
        return None

    # ------------------------------------------------------------------
    # 课表绑定 / 删除
    # ------------------------------------------------------------------
    @filter.command("绑定课表", alias={"绑定", "bind"})
    async def bind_course(self, event: AstrMessageEvent, filename: str = ""):
        """绑定课表文件（支持本地选择与上传）。

        - /绑定课表：列出文件夹中的 .ics 文件，回复文件名或发送新文件完成绑定
        - /绑定课表 文件名.ics：直接绑定指定文件
        - 任何时候发送 .ics 文件都会自动下载到文件夹并绑定
        """
        user_id = str(event.get_sender_id())
        nickname = str(event.get_sender_name())
        ics_dir = self._storage.ics_dir

        # 1) 命令触发时如果直接带了 .ics 文件，直接下载绑定
        direct_url, direct_name = await _try_get_file_info(event)
        if direct_url:
            saved = await self._handle_upload(user_id, nickname, event, direct_url, direct_name)
            if saved:
                return
            # 下载失败时继续走下方列表/上传流程

        files = self._storage.list_ics_files()

        if filename:
            target = pick_ics_file(files, filename)
            if not target:
                yield event.plain_result(
                    f"文件夹中找不到「{filename}」。\n可用文件：\n"
                    + "\n".join(f"📄 {f}" for f in files)
                )
                return
            self._storage.upsert_binding(
                user_id=user_id,
                unified_msg_origin=event.unified_msg_origin,
                nickname=nickname,
                ics_file=target,
            )
            yield event.plain_result(f"绑定成功：{target}")
            return

        if not files:
            yield event.plain_result(
                "课表文件夹中没有 .ics 文件。\n"
                f"课表文件夹：{ics_dir}\n"
                "📥 你可以直接发送 .ics 文件作为消息（我会自动下载到该文件夹并绑定），\n"
                "或者发送「示例课表」生成示例课表体验。"
            )
            async for r in self._bind_wait_upload(event, user_id, nickname, files):
                yield r
            return

        yield event.plain_result(
            "请回复要绑定的课表文件名（120 秒内有效，回复「退出」可取消）。\n"
            "📥 也可直接发送 .ics 文件作为消息，下载到文件夹后自动绑定。\n"
            "📄 " + "\n📄 ".join(files)
        )
        async for r in self._bind_wait_upload(event, user_id, nickname, files):
            yield r

    async def _bind_wait_upload(
        self,
        event: AstrMessageEvent,
        user_id: str,
        nickname: str,
        files: list,
    ):
        """绑定流程的会话等待：支持回复文件名或发送 .ics 文件。"""
        @session_waiter(timeout=_BIND_TIMEOUT, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消绑定。"))
                controller.stop()
                return

            # 检测到 .ics 文件：自动下载并绑定
            file_url, file_name = await _try_get_file_info(evt)
            if file_url:
                saved = await self._handle_upload(
                    user_id, nickname, evt, file_url, file_name
                )
                if saved:
                    controller.stop()
                else:
                    controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)
                return

            # 也允许直接粘贴 .ics 链接
            if re.match(r"^https?://\S+\.ics(\?.*)?$", text, re.I):
                saved = await self._handle_upload(user_id, nickname, evt, text, None)
                if saved:
                    controller.stop()
                else:
                    controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)
                return

            target = pick_ics_file(files, text)
            if not target:
                await evt.send(
                    evt.plain_result(
                        f"未找到「{text}」，请重新回复文件名（回复「退出」取消），或直接发送 .ics 文件。"
                    )
                )
                controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)
                return

            self._storage.upsert_binding(
                user_id=user_id,
                unified_msg_origin=evt.unified_msg_origin,
                nickname=nickname,
                ics_file=target,
            )
            await evt.send(
                evt.plain_result(
                    f"绑定成功：{target}\n"
                    "可发送 /今日课表、/本周课表 查看，\n"
                    "或 /设置每日推送、/设置提醒时间 进行配置。"
                )
            )
            controller.stop()

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("绑定超时，请重新发送 /绑定课表。")
        finally:
            event.stop_event()

    async def _handle_upload(
        self,
        user_id: str,
        nickname: str,
        evt: AstrMessageEvent,
        file_url: str,
        file_name: Optional[str],
    ) -> bool:
        """下载 .ics 文件到 ics_dir 并绑定用户。成功返回 True。"""
        ics_path = self._storage.get_upload_ics_path(user_id, file_name)
        await evt.send(evt.plain_result("正在下载课表..."))
        try:
            await download_file(file_url, str(ics_path))
        except Exception as e:
            logger.error(f"[coursebell] upload download failed: {e}")
            await evt.send(evt.plain_result("文件下载失败，请重试。"))
            return False

        self._parser.clear_cache(str(ics_path))
        self._storage.upsert_binding(
            user_id=user_id,
            unified_msg_origin=evt.unified_msg_origin,
            nickname=nickname,
            ics_file=ics_path.name,
        )
        await evt.send(
            evt.plain_result(
                f"✅ 已下载到课表文件夹并绑定：\n📄 {ics_path.name}\n"
                f"📁 {ics_path.parent}\n"
                "可发送 /今日课表 查看，或 /课表文件 查看文件夹。"
            )
        )
        return True

    @filter.command("课表文件", alias={"文件列表", "files"})
    async def list_files(self, event: AstrMessageEvent):
        """列出课表文件夹中的所有 .ics 文件。"""
        files = self._storage.list_ics_files()
        dir_note = ""
        if self._storage.ics_dir_fallback_reason:
            dir_note = (
                f"\n⚠️ 配置的课表文件夹不可用（{self._storage.ics_dir_fallback_reason}），"
                f"当前使用默认文件夹。"
            )
        if not files:
            yield event.plain_result(
                f"课表文件夹（{self._storage.ics_dir}）中没有任何 .ics 文件。{dir_note}"
            )
            return
        lines = [f"📄 {f}" for f in files]
        # 标注自动匹配
        user_id = str(event.get_sender_id())
        auto = self._storage.find_auto_file(user_id)
        if auto:
            lines = [
                f"📄 {f} {'（已自动匹配你）' if f == auto else ''}" for f in files
            ]
        yield event.plain_result(
            "课表文件夹中的 .ics 文件：\n"
            + "\n".join(lines)
            + f"\n\n📁 {self._storage.ics_dir}{dir_note}"
        )

    @filter.command("删除课表", alias={"解除绑定", "unbind"})
    async def delete_course(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        await self._unregister_user_cron(user_id)
        self._reminded.pop(user_id, None)
        ok = self._storage.delete_binding(user_id)
        if ok:
            yield event.plain_result(
                "已解除课表绑定（本地课表文件未被删除）。"
            )
        else:
            yield event.plain_result("你还没有绑定课表。")

    # ------------------------------------------------------------------
    # 课表查询
    # ------------------------------------------------------------------
    @filter.command("今日课表", alias={"今日", "today"})
    async def today(self, event: AstrMessageEvent):
        async for r in self._send_day_schedule(event, day_offset=0):
            yield r

    @filter.command("明日课表", alias={"明日", "tomorrow"})
    async def tomorrow(self, event: AstrMessageEvent):
        async for r in self._send_day_schedule(event, day_offset=1):
            yield r

    @filter.command("本周课表", alias={"本周", "week"})
    async def this_week(self, event: AstrMessageEvent):
        async for r in self._send_week_schedule(event, offset_weeks=0):
            yield r

    @filter.command("下周课表", alias={"下周", "nextweek"})
    async def next_week(self, event: AstrMessageEvent):
        async for r in self._send_week_schedule(event, offset_weeks=1):
            yield r

    @filter.command("示例课表", alias={"示例", "sample"})
    async def sample(self, event: AstrMessageEvent):
        """在课表文件夹中生成示例课表文件并绑定（测试辅助）。"""
        user_id = str(event.get_sender_id())
        nickname = str(event.get_sender_name())

        # 1) 生成示例课表内容
        try:
            ics_text = build_sample_ics()
        except Exception as e:
            logger.error(f"[coursebell] build sample ics failed: {e}", exc_info=True)
            yield event.plain_result(f"示例课表生成失败：{e}\n请查看 AstrBot 日志获取详细信息。")
            return

        # 2) 写入课表文件夹；失败时回退到插件数据目录
        ics_path = self._storage.get_sample_ics_path(user_id)
        bound_file = ics_path.name
        try:
            ics_path.write_text(ics_text, encoding="utf-8")
        except OSError as e:
            logger.warning(f"[coursebell] write to ics_dir failed ({e}), fallback to data dir")
            fallback_path = self._storage.fallback_dir / ics_path.name
            try:
                fallback_path.write_text(ics_text, encoding="utf-8")
                ics_path = fallback_path
                bound_file = str(fallback_path)
            except OSError as e2:
                logger.error(f"[coursebell] write sample ics failed: {e2}")
                yield event.plain_result(
                    f"示例课表生成失败（无法写入文件夹）：\n"
                    f"课表文件夹：{self._storage.ics_dir}\n原因：{e2}"
                )
                return

        self._parser.clear_cache(str(ics_path))
        self._storage.upsert_binding(
            user_id=user_id,
            unified_msg_origin=event.unified_msg_origin,
            nickname=nickname,
            ics_file=bound_file,
        )
        yield event.plain_result(
            f"已生成示例课表文件并绑定成功：{ics_path.name}\n"
            "示例课表包含每周固定课程，以及一节 20 分钟后开始的测试课。\n"
            "可发送 /今日课表 查看，或等待测试课的课前提醒；\n"
            "也可使用 /设置每日推送 体验每日定时推送。"
        )

    @filter.command("课表帮助", alias={"课程帮助", "help"})
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "🔔 课铃 · 课程提醒使用说明\n"
            "──────────────\n"
            "📁 课表文件放在本地文件夹（插件配置 ics_dir），插件直接读取\n"
            "📥 /绑定课表 [文件名]   选择文件夹中的课表文件绑定\n"
            "🗂 /课表文件   查看文件夹中的课表文件\n"
            "🗑 /删除课表   解除绑定（不删除文件）\n"
            "📅 /今日课表 /明日课表\n"
            "🗓 /本周课表 /下周课表\n"
            "⏰ /设置提醒时间   课前提醒提前分钟数（1-120）\n"
            "📤 /设置每日推送   每日定时推送课表（开启 HH:MM / 关闭）\n"
            "⚙️ /查看设置   查看当前配置\n"
            "🧪 /示例课表   生成示例课表文件用于测试"
        )

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    @filter.command("设置每日推送", alias={"每日推送"})
    async def set_daily_push(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._resolve_binding(user_id, event)
        if not binding:
            yield event.plain_result(
                "你还没有绑定课表。请先使用 /绑定课表（或 /课表文件 查看可用文件）"
            )
            return

        yield event.plain_result(
            "请回复以下格式设置每日推送：\n"
            "「开启 HH:MM」（例如：开启 07:00）\n"
            "或回复「关闭」禁用每日推送\n"
            "120 秒内有效，回复「退出」可取消。"
        )

        @session_waiter(timeout=_BIND_TIMEOUT, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消设置。"))
                controller.stop()
                return

            if text == "关闭":
                bindings = self._storage.load_bindings()
                if user_id in bindings:
                    bindings[user_id].enable_daily_push = False
                    self._storage.save_bindings(bindings)
                await self._unregister_user_cron(user_id)
                await evt.send(evt.plain_result("已关闭每日推送。"))
                controller.stop()
                return

            parts = text.split()
            if len(parts) == 2 and parts[0] == "开启" and _is_valid_time(parts[1]):
                time_str = parts[1]
                bindings = self._storage.load_bindings()
                if user_id in bindings:
                    bindings[user_id].enable_daily_push = True
                    bindings[user_id].daily_push_time = time_str
                    self._storage.save_bindings(bindings)
                await self._unregister_user_cron(user_id)
                await self._register_user_cron(user_id, time_str)
                await evt.send(
                    evt.plain_result(f"已开启每日推送，推送时间：{time_str}")
                )
                controller.stop()
                return

            controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("设置超时，请重新发送 /设置每日推送。")
        finally:
            event.stop_event()

    @filter.command("设置提醒时间", alias={"提醒时间"})
    async def set_reminder_minutes(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._resolve_binding(user_id, event)
        if not binding:
            yield event.plain_result(
                "你还没有绑定课表。请先使用 /绑定课表（或 /课表文件 查看可用文件）"
            )
            return

        yield event.plain_result(
            "请回复提前提醒的分钟数（例如：15 表示提前 15 分钟提醒）\n"
            "范围 1-120，120 秒内有效，回复「退出」可取消。"
        )

        @session_waiter(timeout=_BIND_TIMEOUT, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消设置。"))
                controller.stop()
                return

            try:
                minutes = int(text)
            except ValueError:
                controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)
                return

            if not 1 <= minutes <= 120:
                controller.keep(timeout=_BIND_TIMEOUT, reset_timeout=True)
                return

            bindings = self._storage.load_bindings()
            if user_id in bindings:
                bindings[user_id].reminder_advance_minutes = minutes
                self._storage.save_bindings(bindings)
            await evt.send(evt.plain_result(f"已设置提前 {minutes} 分钟提醒。"))
            controller.stop()

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("设置超时，请重新发送 /设置提醒时间。")
        finally:
            event.stop_event()

    @filter.command("查看设置", alias={"设置", "settings"})
    async def view_settings(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._resolve_binding(user_id, event)
        if not binding:
            yield event.plain_result(self._not_bound_text())
            return
        yield event.plain_result(
            "当前设置：\n"
            f"课表文件：{binding.ics_file}\n"
            f"课表文件夹：{self._storage.ics_dir}\n"
            f"每日推送：{'已开启' if binding.enable_daily_push else '已关闭'}\n"
            f"推送时间：{binding.daily_push_time}\n"
            f"提前提醒：{binding.reminder_advance_minutes} 分钟"
        )

    # ------------------------------------------------------------------
    # 课表渲染（图片优先，失败降级为文本）
    # ------------------------------------------------------------------
    async def _send_day_schedule(self, event: AstrMessageEvent, *, day_offset: int):
        user_id = str(event.get_sender_id())
        binding = self._resolve_binding(user_id, event)
        if not binding:
            yield event.plain_result(self._not_bound_text())
            return

        events = self._parser.parse_ics_file(
            str(self._storage.ics_abs_path(binding))
        )
        target = datetime.now(SHANGHAI_TZ).date() + timedelta(days=day_offset)
        courses = [_event_view(e) for e in day_events(events, target)]

        title = "今日课表" if day_offset == 0 else "明日课表"
        subtitle = f"{binding.nickname} | {_format_date_cn(target)}"
        try:
            url = await self.html_render(
                DAY_TMPL,
                {
                    "title": title,
                    "subtitle": subtitle,
                    "date_str": target.strftime("%m-%d"),
                    "courses": courses,
                    "page_width": 420,
                    "page_height": 560,
                },
                options={"quality": 100, "full_page": True},
            )
            yield event.image_result(url)
        except Exception as e:
            logger.warning(f"[coursebell] day render failed, fallback to text: {e}")
            yield event.plain_result(
                _format_day_text(title, target, courses, subtitle)
            )

    async def _send_week_schedule(self, event: AstrMessageEvent, *, offset_weeks: int):
        user_id = str(event.get_sender_id())
        binding = self._resolve_binding(user_id, event)
        if not binding:
            yield event.plain_result(self._not_bound_text())
            return

        events = self._parser.parse_ics_file(
            str(self._storage.ics_abs_path(binding))
        )
        today = datetime.now(SHANGHAI_TZ).date()
        start = week_start(today) + timedelta(weeks=offset_weeks)

        days = []
        for i in range(7):
            d = start + timedelta(days=i)
            days.append(
                {
                    "label": WEEK_LABELS[i],
                    "date_str": d.strftime("%m-%d"),
                    "is_today": d == today,
                    "courses": [_event_view(e) for e in day_events(events, d)],
                }
            )

        title = "本周课表" if offset_weeks == 0 else "下周课表"
        subtitle = f"{binding.nickname} | {start.strftime('%m-%d')} ~ {(start + timedelta(days=6)).strftime('%m-%d')}"
        try:
            url = await self.html_render(
                WEEK_TMPL,
                {
                    "title": title,
                    "subtitle": subtitle,
                    "days": days,
                    "page_width": 420,
                    "page_height": 560,
                },
                options={"quality": 100, "full_page": True},
            )
            yield event.image_result(url)
        except Exception as e:
            logger.warning(f"[coursebell] week render failed, fallback to text: {e}")
            yield event.plain_result(
                _format_week_text(title, start, days, subtitle)
            )

    def _not_bound_text(self) -> str:
        files = self._storage.list_ics_files()
        dir_note = (
            f"\n⚠️ 配置的课表文件夹不可用，当前使用默认文件夹。"
            if self._storage.ics_dir_fallback_reason
            else ""
        )
        if files:
            hint = (
                "你还没有绑定课表。\n"
                f"课表文件夹：{self._storage.ics_dir}{dir_note}\n"
                f"可用文件：\n"
                + "\n".join(f"📄 {f}" for f in files)
                + "\n请使用 /绑定课表 选择文件完成绑定（或 /示例课表 快速体验）。"
            )
        else:
            hint = (
                "你还没有绑定课表，且课表文件夹中没有任何 .ics 文件。\n"
                f"请将课表 .ics 文件放入文件夹：\n{self._storage.ics_dir}{dir_note}\n"
                "然后发送 /绑定课表 完成绑定（或 /示例课表 快速体验）。"
            )
        return hint

    # ------------------------------------------------------------------
    # 每日推送（cron）
    # ------------------------------------------------------------------
    async def _register_user_cron(self, user_id: str, time_str: str) -> None:
        try:
            hour, minute = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            logger.warning(f"[coursebell] invalid push time: {time_str}")
            return

        binding = self._storage.get_binding(user_id)
        if not binding:
            return

        cron_expr = f"{minute} {hour} * * *"

        # 清理该用户旧的推送任务，避免重复
        for old_job_id in await self._collect_user_daily_job_ids(user_id, binding):
            try:
                await self._context.cron_manager.delete_job(old_job_id)
            except Exception as e:
                logger.debug(f"[coursebell] cleanup old cron job {old_job_id}: {e}")

        payload = {
            "user_id": user_id,
            "unified_msg_origin": binding.unified_msg_origin,
            "nickname": binding.nickname,
            "ics_file": binding.ics_file,
        }

        try:
            job = await self._context.cron_manager.add_basic_job(
                name=f"每日课表推送_{user_id}",
                cron_expression=cron_expr,
                handler=self._daily_push_handler,
                description="每日课表推送",
                timezone="Asia/Shanghai",
                payload=payload,
                enabled=True,
                persistent=True,
            )
            bindings = self._storage.load_bindings()
            if user_id in bindings:
                bindings[user_id].daily_push_job_id = str(job.job_id)
                self._storage.save_bindings(bindings)
            logger.info(f"[coursebell] daily push cron registered for {user_id} @ {time_str}")
        except Exception as e:
            logger.error(f"[coursebell] register cron failed for {user_id}: {e}")

    async def _unregister_user_cron(self, user_id: str) -> None:
        binding = self._storage.get_binding(user_id)
        job_ids = await self._collect_user_daily_job_ids(user_id, binding)
        for job_id in job_ids:
            try:
                await self._context.cron_manager.delete_job(job_id)
            except Exception as e:
                logger.debug(f"[coursebell] unregister cron job {job_id}: {e}")
        bindings = self._storage.load_bindings()
        if user_id in bindings:
            bindings[user_id].daily_push_job_id = ""
            self._storage.save_bindings(bindings)

    async def _collect_user_daily_job_ids(
        self, user_id: str, binding: Optional[UserBinding]
    ) -> Set[str]:
        job_ids: Set[str] = set()
        if binding and binding.daily_push_job_id:
            job_ids.add(binding.daily_push_job_id)

        try:
            jobs = await self._context.cron_manager.list_jobs("basic")
        except Exception as e:
            logger.debug(f"[coursebell] list cron jobs failed: {e}")
            return job_ids

        for job in jobs:
            payload = getattr(job, "payload", None) or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("user_id", "")) != user_id:
                continue
            name = str(getattr(job, "name", ""))
            description = str(getattr(job, "description", ""))
            if "每日课表推送" not in name and "每日课表推送" not in description:
                continue
            job_id = getattr(job, "job_id", "")
            if job_id:
                job_ids.add(str(job_id))
        return job_ids

    async def _daily_push_handler(self, **payload) -> None:
        """cron 触发的每日课表推送。"""
        user_id = payload.get("user_id")
        if not user_id:
            return
        binding = self._storage.get_binding(user_id)
        if not binding or not binding.enable_daily_push:
            return

        try:
            events = self._parser.parse_ics_file(
                str(self._storage.ics_abs_path(binding))
            )
            today = datetime.now(SHANGHAI_TZ).date()
            courses = [_event_view(e) for e in day_events(events, today)]
            title = "今日课表"
            subtitle = f"{binding.nickname} | {_format_date_cn(today)}"

            try:
                url = await self.html_render(
                    DAY_TMPL,
                    {
                        "title": title,
                        "subtitle": subtitle,
                        "date_str": today.strftime("%m-%d"),
                        "courses": courses,
                        "page_width": 420,
                        "page_height": 560,
                    },
                    options={"quality": 100, "full_page": True},
                )
                chain = MessageChain([Image.fromURL(url)])
            except Exception as e:
                logger.warning(
                    f"[coursebell] daily push render failed, fallback to text: {e}"
                )
                chain = MessageChain().message(
                    _format_day_text(title, today, courses, subtitle)
                )

            session = MessageSession.from_str(binding.unified_msg_origin)
            await self._context.send_message(session, chain)
        except Exception as e:
            logger.error(f"[coursebell] daily push failed for {user_id}: {e}")

    # ------------------------------------------------------------------
    # 课前提醒循环
    # ------------------------------------------------------------------
    async def _reminder_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick_reminder()
            except Exception as e:
                logger.error(f"[coursebell] reminder tick failed: {e}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def _tick_reminder(self) -> None:
        bindings = self._storage.load_bindings()
        if not bindings:
            return

        now = datetime.now(SHANGHAI_TZ)
        self._cleanup_reminded(now)

        for user_id, binding in bindings.items():
            try:
                events = self._parser.parse_ics_file(
                    str(self._storage.ics_abs_path(binding))
                )
                hits = upcoming_events(
                    now=now,
                    events=events,
                    advance_minutes=binding.reminder_advance_minutes,
                )
                if not hits:
                    continue
                reminded = self._reminded.setdefault(user_id, set())
                for e in hits:
                    key = e.reminder_key()
                    if key in reminded:
                        continue
                    reminded.add(key)
                    session = MessageSession.from_str(binding.unified_msg_origin)
                    await self._context.send_message(
                        session,
                        MessageChain().message(
                            _format_reminder(e, binding.reminder_advance_minutes)
                        ),
                    )
            except Exception as e:
                logger.error(f"[coursebell] reminder failed for {user_id}: {e}")

    def _cleanup_reminded(self, now: datetime) -> None:
        """清理 30 天前的提醒记录，防止内存无限增长。"""
        cutoff = now - timedelta(days=30)
        for user_id in list(self._reminded.keys()):
            kept = {
                key
                for key in self._reminded[user_id]
                if _reminder_time_from_key(key) and _reminder_time_from_key(key) >= cutoff
            }
            if kept:
                self._reminded[user_id] = kept
            else:
                self._reminded.pop(user_id, None)


# ======================================================================
# 模块级辅助函数
# ======================================================================

def _event_view(e: CourseEvent) -> Dict[str, str]:
    return {
        "summary": e.summary,
        "location": e.location or "",
        "time_range": (
            f"{e.start_time.strftime('%H:%M')} - {e.end_time.strftime('%H:%M')}"
        ),
    }


def _format_date_cn(d: date) -> str:
    return f"{d.month}月{d.day}日 {WEEK_LABELS[d.weekday()]}"


def _format_day_text(
    title: str, target: date, courses: list, subtitle: str = ""
) -> str:
    lines = [f"📅 {title}（{target.strftime('%m-%d')}）"]
    if subtitle:
        lines.insert(1, subtitle)
    if not courses:
        lines.append("今日暂无课程，享受生活吧～")
    else:
        for c in courses:
            lines.append(
                f"{c['time_range']}  {c['summary']}"
                f"{'  📍' + c['location'] if c['location'] else ''}"
            )
    lines.append(f"共 {len(courses)} 节课")
    return "\n".join(lines)


def _format_week_text(title: str, start: date, days: list, subtitle: str = "") -> str:
    lines = [f"🗓 {title}（{start.strftime('%m-%d')} ~ {(start + timedelta(days=6)).strftime('%m-%d')}）"]
    if subtitle:
        lines.insert(1, subtitle)
    for day in days:
        mark = "（今天）" if day["is_today"] else ""
        lines.append(f"—— {day['label']}{mark} {day['date_str']}")
        if not day["courses"]:
            lines.append("    无课")
        else:
            for c in day["courses"]:
                lines.append(
                    f"    {c['time_range']}  {c['summary']}"
                    f"{'  📍' + c['location'] if c['location'] else ''}"
                )
    return "\n".join(lines)


def _format_reminder(e: CourseEvent, advance_minutes: int) -> str:
    loc = e.location.strip() if e.location else ""
    msg = (
        f"⏰ 开课提醒\n"
        f"《{e.summary}》将在 {advance_minutes} 分钟后开始\n"
        f"🕐 {e.start_time.strftime('%H:%M')} - {e.end_time.strftime('%H:%M')}"
    )
    if loc:
        msg += f"\n📍 {loc}"
    return msg


def _reminder_time_from_key(key: str):
    """从提醒记录 key 中解析开始时间，用于清理过期记录。"""
    start_str = key.split("|", 1)[0].strip()
    if not start_str:
        return None
    try:
        dt = datetime.fromisoformat(start_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


async def _try_get_file_info(event: AstrMessageEvent):
    """从消息中提取 .ics 文件的下载 URL 与原始文件名。

    Returns:
        (url, name) 元组；未检测到文件时返回 (None, None)。
        兼容不同平台 File 组件实现（aiocqhttp 的 url / get_file 等）。
    """
    try:
        for m in event.get_messages():
            if getattr(m, "type", None) != "File":
                continue
            # 仅接受 .ics 文件
            name = (getattr(m, "name", None) or "").strip()
            if name and not name.lower().endswith(".ics"):
                continue

            # 部分平台直接暴露 url 字段
            url = getattr(m, "url", None)
            if isinstance(url, str) and url.startswith("http"):
                return url, name or None

            # 部分平台通过 get_file 协程获取下载 URL
            get_file = getattr(m, "get_file", None)
            if callable(get_file):
                try:
                    res = get_file(allow_return_url=True)
                    if asyncio.iscoroutine(res):
                        res = await res
                    if isinstance(res, str) and res.startswith("http"):
                        return res, name or None
                except Exception:
                    continue
    except Exception:
        pass
    return None, None


def _is_valid_time(time_str: str) -> bool:
    return bool(re.match(r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$", time_str))
