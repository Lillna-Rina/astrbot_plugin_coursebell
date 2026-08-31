# AstrBot 课程提醒插件

<div align="center">

![Version](https://img.shields.io/badge/Version-v1.2.0-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Python](https://img.shields.io/badge/Python-3.9+-yellow)

**直接读取本地文件夹中的课表文件，竖屏展示今日/明日/本周/下周课表，支持课前提醒与每日定时推送。**

</div>

> **使用提示**：本插件**不依赖用户上传**课表文件。只需把 `.ics` 课表文件放入指定文件夹，发送 `/绑定课表` 选择文件即可；文件名以用户 ID 开头时无需绑定、自动匹配。

## 功能概览

- **本地文件夹课表**：直接读取本地文件夹中的 `.ics` 文件（可在插件配置中指定路径），放入新文件即刻生效，无需重载插件。
- **竖屏课表图片**：今日/明日/本周/下周课表渲染为适合手机查看的竖屏图片；未安装 Playwright 时自动降级为文本。
- **课前提醒**：每 60 秒扫描课表，开课前 `N` 分钟（默认 15，可配置 1-120）自动推送提醒，同一节课只提醒一次。
- **每日定时推送**：每天指定时间（如 07:00）自动推送当日课表；定时任务持久化，插件重启后自动恢复。
- **自动匹配绑定**：文件名以用户 ID 开头的课表文件（如 `123456.ics`）自动匹配用户，无需手动绑定。
- **示例课表**：一键生成示例课表（含一节 20 分钟后开始的测试课），快速体验提醒与推送功能。
- **ICS 兼容**：支持重复课程（RRULE）展开、EXDATE 排除、东八区时间换算；重复事件解析失败时自动降级为单次事件，不丢课。

## 快速安装

### 前置要求

- AstrBot >= 4.19.4
- Python 3.9+
- 可选：Playwright 渲染环境（用于输出竖屏课表图片；未安装时自动降级为文本消息，功能不受影响）

### 安装方式

**从文件安装**：在插件界面右下角点击加号，选择「从文件安装」，上传本仓库 [Releases](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/releases) 中的 `astrbot_plugin_course_reminder.zip`。

**链接安装**：在插件界面右下角点击加号，选择「从链接安装」，输入：

```text
https://github.com/Lillna-Rina/astrbot_plugin_course_reminder
```

依赖会按 [requirements.txt](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/blob/main/requirements.txt) 自动安装（`icalendar`、`python-dateutil`、`tzdata`）。

## 最小配置

插件配置中可设置：

- `ics_dir`：本地课表文件夹路径（支持绝对路径如 `D:/课表`、`~/` 开头路径，或相对 AstrBot 运行目录的路径）；
- **留空**时使用插件数据目录下的 `ics` 文件夹（`data/plugin_data/astrbot_plugin_course_reminder/ics/`），直接把 `.ics` 文件放进去即可；
- 文件夹无法创建或写入时会自动回退到默认目录，并在 `/课表文件` 中显示警告。

常用入口：

- [使用说明](#常用命令)
- [数据存储说明](#数据存储)
- [故障排除](#常见问题)

## 常用命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/绑定课表` | 列出文件夹中的课表文件并绑定 | `/绑定课表` 后回复文件名 |
| `/绑定课表 [文件名]` | 直接绑定指定文件 | `/绑定课表 我的课表.ics` |
| `/课表文件` | 查看文件夹中的所有 .ics 文件 | `/课表文件` |
| `/删除课表` | 解除绑定（不删除本地文件） | `/删除课表` |
| `/今日课表` | 输出今日课表 | `/今日课表` |
| `/明日课表` | 输出明日课表 | `/明日课表` |
| `/本周课表` | 输出本周课表 | `/本周课表` |
| `/下周课表` | 输出下周课表 | `/下周课表` |
| `/设置提醒时间` | 设置课前提醒提前分钟数 | `/设置提醒时间` 后回复 `15` |
| `/设置每日推送` | 设置每日定时推送课表 | `/设置每日推送` 后回复 `开启 07:00` 或 `关闭` |
| `/查看设置` | 查看当前绑定与配置 | `/查看设置` |
| `/示例课表` | 生成示例课表并绑定 | `/示例课表` |
| `/课表帮助` | 查看指令列表 | `/课表帮助` |

> 所有指令均支持简短别名：`/today`、`/tomorrow`、`/week`、`/nextweek`、`/bind`、`/unbind`、`/files`、`/sample`、`/settings`、`/help`。

## 数据存储

- 课表文件：你指定的本地文件夹（插件只读）；
- 绑定信息与设置：`data/plugin_data/astrbot_plugin_course_reminder/bindings.json`（插件重装/更新不会丢失）；
- 文件变更自动检测：每次读取前对比文件修改时间与大小，替换文件后无需任何操作即生效。

## 项目结构

```text
astrbot_plugin_course_reminder/
├── main.py                 # 插件主入口（命令、提醒循环、每日推送）
├── ics_parser.py           # ICS 解析（RRULE 展开、EXDATE、时区换算）
├── schedule_engine.py      # 课表查询与提醒命中引擎
├── storage.py              # 绑定信息与本地文件管理
├── render_templates.py     # 竖屏课表图片 HTML 模板
├── sample_ics.py           # 示例课表生成器
├── course_types.py         # 数据模型
├── _conf_schema.json       # 配置 Schema（ics_dir）
├── metadata.yaml           # 插件元数据
├── requirements.txt        # 依赖清单
└── logo.png                # 插件图标
```

## 贡献

欢迎提交 [Issue](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/issues) 和 [Pull Request](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/pulls)。

## 许可证

MIT License - 详见 [LICENSE](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/blob/main/LICENSE)。

## 相关链接

- [项目地址](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder)
- [更新日志](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/blob/main/CHANGELOG.md)
- [问题反馈](https://github.com/Lillna-Rina/astrbot_plugin_course_reminder/issues)
- [AstrBot](https://docs.astrbot.app/)
- [WakeUp 课程表](https://www.wakeupcourse.com/)（导出 .ics 课表）
- [参考项目：astrbot_plugin_course](https://github.com/PolysaCHride/astrbot_plugin_course)

## 常见问题

- **课表输出为文本而不是图片**：AstrBot 未安装 Playwright 渲染环境，功能不受影响；安装 Playwright 后即可获得竖屏图片。
- **文件夹中没有文件**：确认 `.ics` 文件已放入配置的文件夹（可在 WebUI 插件配置中查看路径），并发送 `/绑定课表`。
- **示例课表失败**：查看 `/课表文件` 是否提示目录回退；插件会自动回退到数据目录并继续生成。
- **时区**：插件固定按东八区（Asia/Shanghai）计算日期与提醒时间。

## Star History

<a href="https://www.star-history.com/?repos=Lillna-Rina%2Fastrbot_plugin_course_reminder&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Lillna-Rina/astrbot_plugin_course_reminder&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Lillna-Rina/astrbot_plugin_course_reminder&type=date&theme=light&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Lillna-Rina/astrbot_plugin_course_reminder&type=date&legend=top-left" />
 </picture>
</a>
