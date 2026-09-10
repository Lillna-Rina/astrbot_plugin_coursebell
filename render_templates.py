"""课铃（CourseBell）插件 - 课表图片渲染模板（Jinja2 + HTML/CSS）。

AstrBot 通过 Star.html_render() 渲染为图片。
模板输出固定 3:4 比例的竖屏图片（默认 420x560 CSS 像素）：
- 内容较少时铺满画布（flex 撑开、底部页脚沉底）；
- 内容较多时通过 JS 等比缩放至画布内，保证课程信息完整、图片比例不变。
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
  }
  #stage {
    width: {{ page_width | default(420) }}px;
    height: {{ page_height | default(560) }}px;
    overflow: hidden;
    position: relative;
    background: #eef2f9;
  }
  #content {
    width: 100%;
    min-height: 100%;
    display: flex;
    flex-direction: column;
    padding: 22px 18px 16px;
  }
  .header { text-align: center; margin-bottom: 16px; }
  .header .date {
    display: inline-block; background: #e4ecff; color: #3b6fe8;
    font-size: 13px; font-weight: 700;
    padding: 5px 16px; border-radius: 999px; margin-bottom: 10px;
  }
  .header h1 { font-size: 27px; font-weight: 900; color: #22304a; letter-spacing: 1px; }
  .header .sub { font-size: 12px; color: #93a1b8; font-weight: 600; margin-top: 4px; }
  .courses { flex: 1; display: flex; flex-direction: column; gap: 11px; }
  .course {
    background: #ffffff; border-radius: 16px; padding: 15px 14px;
    display: flex; gap: 13px; align-items: stretch;
    box-shadow: 0 3px 12px rgba(40, 70, 140, 0.07);
  }
  .time {
    min-width: 72px; text-align: center;
    background: #f1f5ff; border-radius: 12px; padding: 9px 5px;
    display: flex; flex-direction: column; justify-content: center;
  }
  .time .start { font-size: 15px; font-weight: 800; color: #3b6fe8; line-height: 1.1; }
  .time .end { font-size: 11px; color: #93a1b8; font-weight: 700; margin-top: 4px; }
  .info { flex: 1; display: flex; flex-direction: column; justify-content: center; }
  .info .name { font-size: 17px; font-weight: 800; color: #22304a; line-height: 1.35; }
  .info .loc { font-size: 13px; color: #93a1b8; margin-top: 7px; font-weight: 600; }
  .empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #a9b4c8; }
  .empty .big { font-size: 46px; margin-bottom: 12px; }
  .empty p { font-size: 15px; font-weight: 700; }
  .footer {
    text-align: center; color: #a9b4c8; font-size: 12px; font-weight: 600;
    margin-top: 14px;
  }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 7px; }
  .tag {
    font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 999px;
  }
  .tag.swap { background: #fff1e0; color: #d98324; }
  .tag.count { background: #e9f7ef; color: #2f9e5f; }
</style>
</head>
<body>
  <div id="stage">
    <div id="content">
      <div class="header">
        <div class="date">{{ date_str }}</div>
        <h1>📅 {{ title }}</h1>
        <div class="sub">{{ subtitle }}</div>
        {% if swap_note or countdown %}
        <div class="tags">
          {% if swap_note %}<span class="tag swap">🔄 {{ swap_note }}</span>{% endif %}
          {% if countdown %}<span class="tag count">{{ countdown }}</span>{% endif %}
        </div>
        {% endif %}
      </div>
      {% if courses|length == 0 %}
        <div class="empty">
          <div class="big">🎉</div>
          <p>{{ '今天放假，好好休息～' if swap_note else '今天没有课程，享受生活吧～' }}</p>
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
    </div>
  </div>
  <script>
    (function () {
      var stage = document.getElementById('stage');
      var content = document.getElementById('content');
      var doc = document.documentElement;
      var body = document.body;
      var minW = {{ page_width | default(420) }};
      var stepW = 60;
      var maxW = minW + stepW * 3;
      var W = minW;
      var H_target = W * 4 / 3;
      stage.style.width = W + 'px';
      stage.style.height = H_target + 'px';
      body.style.width = W + 'px';
      doc.style.width = W + 'px';

      var h = content.scrollHeight;
      if (h > H_target) {
        var needW = Math.ceil(h * 3 / 4);
        W = Math.min(Math.max(needW, minW + stepW), maxW);
        W = Math.ceil(W / stepW) * stepW;
        H_target = W * 4 / 3;
        stage.style.width = W + 'px';
        stage.style.height = H_target + 'px';
        body.style.width = W + 'px';
        doc.style.width = W + 'px';
        h = content.scrollHeight;
      }

      if (h > H_target) {
        var s = H_target / h;
        content.style.transform = 'scale(' + s + ')';
        content.style.transformOrigin = 'top left';
        content.style.marginLeft = ((W - W * s) / 2) + 'px';
      }
    })();
  </script>
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
  }
  #stage {
    width: {{ page_width | default(420) }}px;
    height: {{ page_height | default(560) }}px;
    overflow: hidden;
    position: relative;
    background: #eef2f9;
  }
  #content {
    width: 100%;
    min-height: 100%;
    display: flex;
    flex-direction: column;
    padding: 16px 14px 12px;
  }
  .header { text-align: center; margin-bottom: 10px; }
  .header .date {
    display: inline-block; background: #e4ecff; color: #3b6fe8;
    font-size: 11px; font-weight: 700;
    padding: 4px 12px; border-radius: 999px; margin-bottom: 7px;
  }
  .header h1 { font-size: 23px; font-weight: 900; color: #22304a; letter-spacing: 1px; }
  .header .sub { font-size: 11px; color: #93a1b8; font-weight: 600; margin-top: 3px; }
  .grid {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
    align-content: start;
  }
  .day {
    background: #ffffff; border-radius: 11px; overflow: hidden;
    border: 1px solid #e4e9f2;
  }
  .day.is-today { border: 2px solid #3b6fe8; background: #f3f7ff; }
  .day-head {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 8px; background: #f6f8fc;
  }
  .is-today .day-head { background: #3b6fe8; }
  .day-name { font-size: 12px; font-weight: 800; color: #22304a; }
  .is-today .day-name { color: #ffffff; }
  .day-date { font-size: 10px; font-weight: 700; color: #93a1b8; }
  .is-today .day-date { color: #dbe7ff; }
  .day-body { padding: 3px 6px; }
  .row { padding: 4px 2px; border-bottom: 1px solid #f0f3f9; }
  .row:last-child { border-bottom: none; }
  .row .t { font-size: 9px; color: #3b6fe8; font-weight: 800; }
  .row .n {
    font-size: 11px; font-weight: 700; color: #22304a; margin-top: 1px; line-height: 1.25;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .none { color: #c3cbda; font-size: 11px; font-weight: 700; text-align: center; padding: 6px 0; }
  .swap-note {
    font-size: 9px; font-weight: 800; color: #d98324; background: #fff5e8;
    border-radius: 5px; padding: 2px 5px; margin-bottom: 3px; text-align: center;
  }
</style>
</head>
<body>
  <div id="stage">
    <div id="content">
      <div class="header">
        <div class="date">{{ subtitle }}</div>
        <h1>🗓 {{ title }}</h1>
      </div>
      <div class="grid">
        {% for day in days %}
        <div class="day {{ 'is-today' if day.is_today else '' }}">
          <div class="day-head">
            <span class="day-name">{{ day.label }}{{ '·今天' if day.is_today else '' }}</span>
            <span class="day-date">{{ day.date_str }}</span>
          </div>
          <div class="day-body">
            {% if day.swap_note %}
              <div class="swap-note">{{ '🚫 放假' if day.swap_note == '放假' else '🔄 调休' }}</div>
            {% endif %}
            {% if day.courses|length == 0 %}
              <div class="none">{{ '放假' if day.swap_note else '无课' }}</div>
            {% else %}
              {% for c in day.courses %}
              <div class="row">
                <div class="t">{{ c.time_range }}</div>
                <div class="n">{{ c.summary }}</div>
              </div>
              {% endfor %}
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
  <script>
    (function () {
      var stage = document.getElementById('stage');
      var content = document.getElementById('content');
      var doc = document.documentElement;
      var body = document.body;
      var minW = {{ page_width | default(420) }};
      var stepW = 60;
      var maxW = minW + stepW * 3;
      var W = minW;
      var H_target = W * 4 / 3;
      stage.style.width = W + 'px';
      stage.style.height = H_target + 'px';
      body.style.width = W + 'px';
      doc.style.width = W + 'px';

      var h = content.scrollHeight;
      if (h > H_target) {
        var needW = Math.ceil(h * 3 / 4);
        W = Math.min(Math.max(needW, minW + stepW), maxW);
        W = Math.ceil(W / stepW) * stepW;
        H_target = W * 4 / 3;
        stage.style.width = W + 'px';
        stage.style.height = H_target + 'px';
        body.style.width = W + 'px';
        doc.style.width = W + 'px';
        h = content.scrollHeight;
      }

      if (h > H_target) {
        var s = H_target / h;
        content.style.transform = 'scale(' + s + ')';
        content.style.transformOrigin = 'top left';
        content.style.marginLeft = ((W - W * s) / 2) + 'px';
      }
    })();
  </script>
</body>
</html>
"""
