# 倒计时功能调试指南

## 问题症状
倒计时通知功能无法正常工作

## 排查步骤

### 1. 检查倒计时是否成功设置
```
/倒计时
```
查看是否有倒计时记录

### 2. 检查cron任务是否注册
在AstrBot日志中搜索：
- `[coursebell] countdown cron registered` - 成功注册
- `[coursebell] register countdown cron failed` - 注册失败

### 3. 检查cron任务执行
在AstrBot日志中搜索：
- `[coursebell] countdown push` - 推送执行情况

### 4. 检查绑定数据
查看 `data/plugin_data/astrbot_plugin_coursebell/bindings.json`
确认：
- `countdowns` 数组包含倒计时记录
- `countdown_job_ids` 包含任务ID

## 可能的原因

### A. 倒计时设置格式问题
**症状**: `/设置倒计时` 命令返回格式错误

**原因**: 
- 日期格式不正确
- 缺少必要参数

**解决**:
```
正确格式：/设置倒计时 <名称> <日期> [每日|每周|关闭] [HH:MM]
示例：/设置倒计时 考研 2026-12-26 每日 08:00
```

### B. Cron管理器异常
**症状**: 日志显示 `register countdown cron failed`

**原因**:
- AstrBot的cron_manager未正确初始化
- cron表达式语法错误
- 权限问题

**调试代码位置**: 
- `main.py:1200-1249` (_register_countdown_cron)

### C. 倒计时数据未持久化
**症状**: 重启后倒计时消失

**原因**:
- `storage.py` 的 `update_binding` 没有正确保存
- bindings.json 写入失败

**检查**: 
```python
# storage.py:241-252 update_binding方法
# storage.py:254-265 save_bindings方法
```

### D. 推送handler未执行
**症状**: cron任务注册成功但不推送

**原因**:
- payload中的数据不正确
- binding.get_countdown(name) 返回None
- MessageSession创建失败

**调试代码位置**:
- `main.py:1299-1324` (_countdown_push_handler)

## 修复建议

### 修复1: 增强日志输出
在关键位置添加详细日志，便于追踪问题

### 修复2: 添加倒计时验证
设置倒计时后立即验证是否成功注册cron任务

### 修复3: 添加手动测试命令
添加 `/测试倒计时` 命令，手动触发推送测试

## 测试用例

### 测试1: 基础倒计时
```
/设置倒计时 测试 2026-12-26
/倒计时
```
预期：显示倒计时列表，包含"测试"项

### 测试2: 每周通知
```
/设置倒计时 周测试 2026-12-26 每周 09:00
/倒计时
```
预期：显示"每周通知"

### 测试3: 查看设置
```
/查看设置
```
预期：倒计时部分显示已设置的倒计时

### 测试4: 删除倒计时
```
/删除倒计时 测试
/倒计时
```
预期：倒计时列表中不再包含"测试"项
