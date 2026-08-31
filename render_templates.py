"""课铃（CourseBell）插件 - 课表图片渲染模板（Jinja2 + HTML/CSS）。

AstrBot 通过 Star.html_render() 渲染为图片。
模板均为竖屏设计（窄宽度、纵向排版），输出适合手机查看的竖版图片。
"""

DAY_TMPL = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { width: fit-content; background: #eef2f9; }
  body {
    width: {{ page_width | default(420) }}px;
    background: #eef2f9;
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    padding: 20px 16px 16px;
  }
  .header { text-align: center; margin-bottom: 18px; }
  .header .date {
    display: inline-block; background: #e4ecff; color: #3b6fe8;
    font-size: 13px; font-weight: 700;
    padding: 5px 16px; border-radius: 999px; margin-bottom: 10px;
  }
  .header h1 { font-size: 28px; font-weight: 900; color: #22304a; letter-spacing: 1px; }
  .header .sub { font-size: 12px; color: #93a1b8; font-weight: 600; margin-top: 4px; }
  .courses { display: flex; flex-direction: column; gap: 12px; }
  .course {
    background: #ffffff; border-radius: 18px; padding: 18px 16px;
    display: flex; gap: 14px; align-items: stretch;
    box-shadow: 0 3px 14px rgba(40, 70, 140, 0.07);
  }
  .time {
    min-width: 74px; text-align: center;
    background: #f1f5ff; border-radius: 14px; padding: 10px 6px;
    display: flex; flex-direction: column; justify-content: center;
  }
  .time .start { font-size: 16px; font-weight: 800; color: #3b6fe8; line-height: 1.1; }
  .time .end { font-size: 11px; color: #93a1b8; font-weight: 700; margin-top: 4px; }
  .info { flex: 1; display: flex; flex-direction: column; justify-content: center; }
  .info .name { font-size: 18px; font-weight: 800; color: #22304a; line-height: 1.35; }
  .info .loc { font-size: 13px; color: #93a1b8; margin-top: 8px; font-weight: 600; }
  .empty { text-align: center; color: #a9b4c8; padding: 56px 0 40px; }
  .empty .big { font-size: 44px; margin-bottom: 12px; }
  .empty p { font-size: 15px; font-weight: 700; }
  .footer {
    text-align: center; color: #a9b4c8; font-size: 12px; font-weight: 600;
    margin-top: 16px;
  }
</style>
</head>
<body>
  <div class="header">
    <div class="date">{{ date_str }}</div>
    <h1>📅 {{ title }}</h1>
    <div class="sub">{{ subtitle }}</div>
  </div>
  {% if courses|length == 0 %}
    <div class="empty">
      <div class="big">🎉</div>
      <p>今天没有课程，享受生活吧～</p>
    </div>
  {% else %}
    <div class="courses">
      {% for c in courses %}
      <div class="course">
        <div class="time">
          <div class="start">{{ c.time_range.split(' - ')[0] }}</div>
          <div class="end">至<br/>{{ c.time_range.split(' - ')[1] }}</div>
        </div>
        <div class="info">
          <div class="name">{{ c.summary }}</div>
          <div class="loc">📍 {{ c.location if c.location else '地点待定' }}</div>
        </div>
      </div>
      {% endfor %}
    </div>
  {% endif %}
  <div class="footer">共 {{ courses|length }} 节课</div>
</body>
</html>
"""

WEEK_TMPL = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { width: fit-content; background: #eef2f9; }
  body {
    width: {{ page_width | default(420) }}px;
    background: #eef2f9;
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    padding: 20px 16px 16px;
  }
  .header { text-align: center; margin-bottom: 16px; }
  .header .date {
    display: inline-block; background: #e4ecff; color: #3b6fe8;
    font-size: 12px; font-weight: 700;
    padding: 5px 14px; border-radius: 999px; margin-bottom: 10px;
  }
  .header h1 { font-size: 26px; font-weight: 900; color: #22304a; letter-spacing: 1px; }
  .header .sub { font-size: 12px; color: #93a1b8; font-weight: 600; margin-top: 4px; }
  .days { display: flex; flex-direction: column; gap: 10px; }
  .day {
    background: #ffffff; border-radius: 16px; overflow: hidden;
    border: 1px solid #e4e9f2;
  }
  .day.is-today { border: 2px solid #3b6fe8; background: #f3f7ff; }
  .day-head {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 14px; background: #f6f8fc;
  }
  .is-today .day-head { background: #3b6fe8; }
  .day-name { font-size: 15px; font-weight: 800; color: #22304a; }
  .is-today .day-name { color: #ffffff; }
  .day-date { font-size: 12px; font-weight: 700; color: #93a1b8; }
  .is-today .day-date { color: #dbe7ff; }
  .day-body { padding: 8px 12px; }
  .row { padding: 8px 2px; border-bottom: 1px solid #f0f3f9; }
  .row:last-child { border-bottom: none; }
  .row .t { font-size: 11px; color: #3b6fe8; font-weight: 800; }
  .row .n { font-size: 14px; font-weight: 700; color: #22304a; margin: 3px 0; line-height: 1.3; }
  .row .l { font-size: 11px; color: #9aa6ba; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .none { color: #c3cbda; font-size: 12px; font-weight: 700; text-align: center; padding: 10px 0; }
</style>
</head>
<body>
  <div class="header">
    <div class="date">{{ subtitle }}</div>
    <h1>🗓 {{ title }}</h1>
  </div>
  <div class="days">
    {% for day in days %}
    <div class="day {{ 'is-today' if day.is_today else '' }}">
      <div class="day-head">
        <span class="day-name">{{ day.label }}{{ ' · 今天' if day.is_today else '' }}</span>
        <span class="day-date">{{ day.date_str }}</span>
      </div>
      <div class="day-body">
        {% if day.courses|length == 0 %}
          <div class="none">无课</div>
        {% else %}
          {% for c in day.courses %}
          <div class="row">
            <div class="t">{{ c.time_range }}</div>
            <div class="n">{{ c.summary }}</div>
            <div class="l">📍 {{ c.location if c.location else '待定' }}</div>
          </div>
          {% endfor %}
        {% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
</body>
</html>
"""
