"""课程提醒插件 - 课表图片渲染模板（Jinja2 + HTML/CSS）。

AstrBot 通过 Star.html_render() 渲染为图片。
"""

DAY_TMPL = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: {{ page_width | default(520) }}px;
    background: #f5f7fb;
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    padding: 24px;
  }
  .card {
    background: #ffffff;
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 6px 24px rgba(30, 60, 120, 0.08);
  }
  .head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  .head h1 { font-size: 26px; font-weight: 800; color: #1f2d3d; }
  .date-badge {
    background: #eaf2ff; color: #2f6fed;
    font-size: 14px; font-weight: 700;
    padding: 6px 14px; border-radius: 999px;
  }
  .sub { color: #8a94a6; font-size: 13px; margin-top: 4px; }
  .course { display: flex; gap: 16px; padding: 16px 0; border-top: 1px solid #eef1f6; }
  .time {
    min-width: 96px; text-align: center;
    background: #f2f6ff; border-radius: 14px; padding: 10px 8px;
    align-self: center;
  }
  .time .start { font-size: 17px; font-weight: 800; color: #2f6fed; }
  .time .end { font-size: 12px; color: #8a94a6; font-weight: 600; margin-top: 2px; }
  .info { flex: 1; display: flex; flex-direction: column; justify-content: center; }
  .info .name { font-size: 18px; font-weight: 800; color: #1f2d3d; }
  .info .loc { font-size: 13px; color: #8a94a6; margin-top: 6px; font-weight: 600; }
  .empty { text-align: center; color: #a8b2c4; padding: 40px 0 24px; }
  .empty .big { font-size: 40px; margin-bottom: 10px; }
  .empty p { font-size: 15px; font-weight: 600; }
  .footer { text-align: center; color: #b6bfcf; font-size: 12px; margin-top: 16px; }
</style>
</head>
<body>
  <div class="card">
    <div class="head">
      <div>
        <h1>📅 {{ title }}</h1>
        <div class="sub">{{ subtitle }}</div>
      </div>
      <div class="date-badge">{{ date_str }}</div>
    </div>
    {% if courses|length == 0 %}
      <div class="empty">
        <div class="big">🎉</div>
        <p>今天没有课程，享受生活吧～</p>
      </div>
    {% else %}
      {% for c in courses %}
      <div class="course">
        <div class="time">
          <div class="start">{{ c.time_range.split(' - ')[0] }}</div>
          <div class="end">至 {{ c.time_range.split(' - ')[1] }}</div>
        </div>
        <div class="info">
          <div class="name">{{ c.summary }}</div>
          <div class="loc">📍 {{ c.location if c.location else '地点待定' }}</div>
        </div>
      </div>
      {% endfor %}
    {% endif %}
  </div>
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
  body {
    width: {{ page_width | default(820) }}px;
    background: #f5f7fb;
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    padding: 24px;
  }
  .card { background: #ffffff; border-radius: 20px; padding: 24px; box-shadow: 0 6px 24px rgba(30,60,120,0.08); }
  .head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
  .head h1 { font-size: 26px; font-weight: 800; color: #1f2d3d; }
  .head .date-badge { background: #eaf2ff; color: #2f6fed; font-size: 13px; font-weight: 700; padding: 6px 14px; border-radius: 999px; }
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
  .day { border: 1px solid #eef1f6; border-radius: 14px; overflow: hidden; background: #fbfcfe; }
  .day.is-today { border: 2px solid #2f6fed; background: #f2f6ff; }
  .day-head { padding: 10px 12px; background: #eef1f6; display: flex; justify-content: space-between; align-items: center; }
  .is-today .day-head { background: #2f6fed; color: #fff; }
  .day-name { font-size: 14px; font-weight: 800; }
  .day-date { font-size: 11px; font-weight: 600; opacity: .75; }
  .courses { padding: 8px; }
  .row { padding: 7px 4px; border-bottom: 1px solid #f1f4f9; }
  .row:last-child { border-bottom: none; }
  .row .t { font-size: 11px; color: #2f6fed; font-weight: 800; }
  .row .n { font-size: 13px; font-weight: 700; color: #1f2d3d; margin: 2px 0; line-height: 1.25; }
  .row .l { font-size: 11px; color: #a0a9ba; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .none { color: #c3cbda; font-size: 12px; font-weight: 700; text-align: center; padding: 14px 0; }
</style>
</head>
<body>
  <div class="card">
    <div class="head">
      <h1>🗓 {{ title }}</h1>
      <div class="date-badge">{{ subtitle }}</div>
    </div>
    <div class="grid">
      {% for day in days %}
      <div class="day {{ 'is-today' if day.is_today else '' }}">
        <div class="day-head">
          <span class="day-name">{{ day.label }}{{ ' · 今天' if day.is_today else '' }}</span>
          <span class="day-date">{{ day.date_str }}</span>
        </div>
        <div class="courses">
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
  </div>
</body>
</html>
"""
