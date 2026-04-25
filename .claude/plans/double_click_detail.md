# 实现计划：双击展开详情 + 删除按钮固定位置

## 问题根因

主窗口宽度仅 260px，`TaskItemWidget` 内的 `QLabel` 文本过长时，布局系统无法正确收缩 label，导致右侧 24px 的删除按钮被推出可视区域。

---

## 修改范围

仅修改 `main.py`，涉及 3 处变更：

### 1. 新增 `TaskDetailPopup` 类（约 110 行）

在 `TaskItemWidget` 类定义之前，新增一个圆角悬浮窗类。

**外观：**
- 无边框圆角窗口，`Qt.Popup` 标志（点击外部自动关闭）
- 白色背景 + `QGraphicsDropShadowEffect` 阴影
- 右上角圆形 "×" 关闭按钮
- 内容区用只读 `QTextEdit`，开启自动换行，无边框

**交互：**
- 显示时自动聚焦，`Esc` 关闭
- 底部左侧放一个删除按钮（平时隐藏，悬浮时显示），点击后弹 `QMessageBox` 确认，确认后删除任务并关闭弹窗
- 通过信号 `delete_requested(int)` 通知父组件删除

**定位：**
- 在 `TaskItemWidget` 右侧弹出（`widget.mapToGlobal()` 计算坐标）
- 固定宽度 300px，高度随内容自适应，最大不超过屏幕高度 80%

### 2. 修改 `TaskItemWidget` 类（约 25 行变更）

- **构造参数**：新增 `show_detail` 回调参数
- **双击事件**：重写 `mouseDoubleClickEvent`，忽略 checkbox 区域（y 轴 0-40 且 x 轴 checkbox 范围内不触发），其他区域调用 `show_detail(task_id)`
- **文本溢出兜底**：在 `_setup_ui` 中给 label 设置：
  ```python
  self.label.setMinimumWidth(40)           # 防止被压缩到 0
  self.label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
  ```
  同时保存原始文本到 `self._full_text`，后续 resize 时手动 elide

### 3. 在 `StickyNotes` 中连线（约 10 行变更）

- `render_tasks` 方法中，创建 `TaskItemWidget` 时传入 `show_detail` 回调 → 指向新方法 `_show_task_detail(task_id)`
- 新增方法 `_show_task_detail(task_id)`：查找任务文本 → 创建/复用 `TaskDetailPopup` → 定位到对应 `TaskItemWidget` → `popup.show()`
- 连接弹窗的 `delete_requested` 信号到现有的 `delete_task` 方法

---

## 文件变更摘要

| 文件 | 操作 | 行数变化 |
|------|------|----------|
| `main.py` | 导入新增 `QGraphicsDropShadowEffect`, `QTextEdit` | +1 import |
| `main.py` | 新增 `TaskDetailPopup` 类 | ~110 行新增 |
| `main.py` | 修改 `TaskItemWidget.__init__` 签名 | +1 参数 |
| `main.py` | `TaskItemWidget` 新增 `mouseDoubleClickEvent` | ~15 行新增 |
| `main.py` | `TaskItemWidget._setup_ui` 补充兜底设置 | ~5 行新增 |
| `main.py` | `StickyNotes.render_tasks` 传入回调 | ~3 行变更 |
| `main.py` | `StickyNotes` 新增 `_show_task_detail` 方法 | ~20 行新增 |

**总计**：约 +150 行，-5 行（已有代码微调）

---

## 用户体验流程

```
1. 用户看到一条长文本任务，文本被截断显示 "..."
2. 鼠标悬停 → 右侧固定位置出现红色 "×" 删除按钮（可快速删除）
3. 双击任务文本区域 → 弹出圆角悬浮窗，完整显示文本（自动换行）
4. 悬浮窗内可：
   - 阅读完整内容
   - 点击悬浮窗内删除按钮删除任务
   - 点击外部 / 按 Esc / 点 "×" 关闭
```
