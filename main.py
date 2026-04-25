#!/usr/bin/env python3
"""
任务便签悬浮窗 — 桌面常驻悬浮窗级任务管理工具
运行: python main.py
依赖: pip install PyQt6
"""

import json
import os
import sys
import time
import shutil
from pathlib import Path

# Windows 下 PyQt6 需要 Qt6/bin 在 PATH 中（conda 环境常见问题）
if sys.platform == "win32":
    try:
        import importlib.util
        spec = importlib.util.find_spec("PyQt6")
        if spec and spec.submodule_search_locations:
            pkg_dir = spec.submodule_search_locations[0]
            qt_bin = os.path.join(pkg_dir, "Qt6", "bin")
            if os.path.isdir(qt_bin):
                os.environ["PATH"] = qt_bin + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

from PyQt6.QtCore import Qt, QEvent, QStandardPaths
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QIcon, QPixmap, QAction
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea,
    QCheckBox, QSystemTrayIcon, QMenu, QFrame,
    QWIDGETSIZE_MAX
)


# ──────────────────────────────────────────────
# 数据持久化层
# ──────────────────────────────────────────────

class DataManager:
    """负责 JSON 文件的读取、写入、备份与重置"""

    def __init__(self):
        self.data_dir = self._get_data_dir()
        self.data_file = self.data_dir / "tasks.json"

    @staticmethod
    def _get_data_dir() -> Path:
        """获取系统应用数据目录"""
        app_name = "StickyNotes"
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if base:
            p = Path(base)
            if p.name != app_name:
                p = p / app_name
            return p
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", "")) / app_name
        elif sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / app_name
        else:
            return Path.home() / ".local" / "share" / app_name

    def ensure_dir(self):
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_data(self) -> dict:
        """读取 JSON，损坏时自动备份并重置"""
        default = {
            "version": "1.0",
            "window": {
                "x": None, "y": None,
                "width": 320, "height": 400,
                "collapsed": False,
            },
            "tasks": [],
        }
        if not self.data_file.exists():
            return default
        try:
            raw = self.data_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict) or "tasks" not in data:
                raise ValueError("数据结构异常")
            data.setdefault("version", "1.0")
            data.setdefault("window", default["window"])
            data["window"].setdefault("x", None)
            data["window"].setdefault("y", None)
            data["window"].setdefault("width", 320)
            data["window"].setdefault("height", 400)
            data["window"].setdefault("collapsed", False)
            if not isinstance(data["tasks"], list):
                data["tasks"] = []
            return data
        except Exception:
            self._backup_corrupted()
            return default

    def save_data(self, window, tasks, collapsed):
        """将窗口状态与任务列表写入 JSON"""
        data = {
            "version": "1.0",
            "window": {
                "x": window.x(),
                "y": window.y(),
                "width": window.width(),
                "height": window.height(),
                "collapsed": collapsed,
            },
            "tasks": tasks,
        }
        tmp = self.data_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.data_file)
        except Exception:
            try:
                self.data_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

    def _backup_corrupted(self):
        """备份损坏的 JSON 文件"""
        try:
            bak = self.data_file.with_suffix(".json.bak")
            shutil.copy2(self.data_file, bak)
        except Exception:
            pass


# ──────────────────────────────────────────────
# 任务项组件
# ──────────────────────────────────────────────

class TaskItemWidget(QWidget):
    """单条任务项：复选框 + 文本 + 删除按钮"""

    def __init__(self, task, on_toggle, on_delete, parent=None):
        super().__init__(parent)
        self.task = task
        self.setFixedHeight(40)
        self._setup_ui(on_toggle, on_delete)
        self._apply_style()

    def _setup_ui(self, on_toggle, on_delete):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self.cb = QCheckBox()
        self.cb.setFixedSize(18, 18)
        self.cb.setChecked(self.task["completed"])
        self.cb.clicked.connect(lambda: on_toggle(self.task["id"]))
        layout.addWidget(self.cb)

        self.label = QLabel(self.task["text"])
        self.label.setFont(QFont("Microsoft YaHei UI", 12))
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.label.setWordWrap(False)
        self._update_text_style()
        layout.addWidget(self.label, stretch=1)

        self.btn_del = QPushButton("×")
        self.btn_del.setFixedSize(24, 24)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.setObjectName("delBtn")
        self.btn_del.clicked.connect(lambda: on_delete(self.task["id"]))
        self.btn_del.setVisible(False)
        layout.addWidget(self.btn_del)

    def _apply_style(self):
        self.cb.setStyleSheet(
            "QCheckBox::indicator {"
            "    width: 18px; height: 18px; border-radius: 9px;"
            "    border: 2px solid #d9d9d9; background: #fff;"
            "}"
            "QCheckBox::indicator:checked {"
            "    background-color: #52c41a; border-color: #52c41a;"
            "}"
            "QCheckBox::indicator:hover { border-color: #52c41a; }"
        )
        self.btn_del.setStyleSheet(
            "QPushButton#delBtn {"
            "    background: transparent; border: none;"
            "    color: #FF4444; font-size: 16px; font-weight: bold;"
            "}"
            "QPushButton#delBtn:hover {"
            "    color: #FF0000; background: rgba(255,0,0,0.08);"
            "    border-radius: 12px;"
            "}"
        )

    def _update_text_style(self):
        if self.task["completed"]:
            self.label.setStyleSheet("color: #999999; text-decoration: line-through;")
        else:
            self.label.setStyleSheet("color: #333333;")

    def enterEvent(self, event):
        self.btn_del.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_del.setVisible(False)
        super().leaveEvent(event)


# ──────────────────────────────────────────────
# 主悬浮窗
# ──────────────────────────────────────────────

BG_COLOR = "#FFFEF0"
TITLE_BG = "#FFF9DB"
INPUT_BG = "#FFFEF0"
DIVIDER = "#f0ece0"
FOLD_HEIGHT = 45
DEFAULT_W, DEFAULT_H = 320, 400
CORNER_RADIUS = 12
SHADOW_WIDTH = 16  # 阴影外扩宽度


class StickyNotes(QWidget):
    """主悬浮窗 — 圆角背景+阴影由 paintEvent 统一绘制，
       避免 WA_TranslucentBackground + QGraphicsDropShadowEffect 的 Windows 兼容问题"""

    def __init__(self):
        super().__init__()
        self.dm = DataManager()
        self.tasks = []
        self.is_collapsed = False
        self.drag_pos = None
        self.is_dragging = False
        self._shadow = SHADOW_WIDTH
        self._task_widgets = []
        self.empty_label = None  # 阴影宽度

        self._init_window()
        self._load_and_restore()
        self._setup_ui()
        self._setup_tray()
        self._restore_geometry()

    # ── 窗口初始化 ──

    def _init_window(self):
        """无边框、置顶、不在任务栏显示"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # 使用 WA_TranslucentBackground 但不用 QGraphicsDropShadowEffect，
        # 阴影在 paintEvent 中手绘，避免 Windows 下 UpdateLayeredWindowIndirect 报错
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(280, FOLD_HEIGHT)
        self.resize(DEFAULT_W, DEFAULT_H)

    # ── 数据加载 ──

    def _load_and_restore(self):
        self.dm.ensure_dir()
        data = self.dm.load_data()
        self.tasks = data.get("tasks", [])
        self._saved_window = data.get("window", {})
        self.is_collapsed = self._saved_window.get("collapsed", False)

    def _restore_geometry(self):
        """恢复上次窗口位置，无记录则屏幕右侧居中"""
        w = self._saved_window
        x, y = w.get("x"), w.get("y")
        sw, sh = w.get("width", DEFAULT_W), w.get("height", DEFAULT_H)

        screen = QApplication.primaryScreen().geometry()
        if (
            x is not None and y is not None
            and 0 <= x < screen.right() and 0 <= y < screen.bottom()
        ):
            self.move(x, y)
        else:
            x = screen.right() - DEFAULT_W - 40
            y = (screen.height() - DEFAULT_H) // 2
            self.move(max(screen.left(), x), y)

        self.resize(sw, sh)

        if self.is_collapsed:
            self._do_collapse()

    # ── UI 构建 ──

    def _setup_ui(self):
        """构建全部 UI 组件，内容区留阴影宽度的边距"""
        s = self._shadow
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(s, s, s, s)
        self.main_layout.setSpacing(0)

        # 标题栏
        self.title_bar = self._create_title_bar()
        self.main_layout.addWidget(self.title_bar)

        # 内容区
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # 滚动区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #d0d0d0; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self.task_container = QWidget()
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(0, 0, 0, 0)
        self.task_layout.setSpacing(0)
        self.scroll_area.setWidget(self.task_container)
        self.content_layout.addWidget(self.scroll_area)

        # 分隔线
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {DIVIDER};")
        self.content_layout.addWidget(divider)

        # 输入区域
        self.input_area = self._create_input_area()
        self.content_layout.addWidget(self.input_area)

        self.main_layout.addWidget(self.content_widget, stretch=1)

        self.render_tasks()

    def _create_title_bar(self) -> QWidget:
        """创建顶部标题栏"""
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(40)
        bar.setStyleSheet(
            f"QWidget#titleBar {{ "
            f"background: {TITLE_BG}; "
            f"border-top-left-radius: {CORNER_RADIUS}px; "
            f"border-top-right-radius: {CORNER_RADIUS}px; "
            f"}}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        icon = QLabel("📌")
        icon.setFont(QFont("Segoe UI Emoji", 14))
        layout.addWidget(icon)

        title = QLabel("便签")
        title.setFont(QFont("Microsoft YaHei UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #333;")
        layout.addWidget(title)

        # 任务计数
        self.counter_label = QLabel("")
        self.counter_label.setFont(QFont("Microsoft YaHei UI", 11))
        self.counter_label.setStyleSheet("color: #888;")
        layout.addWidget(self.counter_label, stretch=1)

        # 折叠按钮
        self.btn_collapse = QPushButton("—")
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.setToolTip("折叠/展开")
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        self.btn_collapse.setStyleSheet(self._title_btn_qss())
        layout.addWidget(self.btn_collapse)

        # 最小化到托盘按钮
        self.btn_minimize = QPushButton("×")
        self.btn_minimize.setFixedSize(28, 28)
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minimize.setToolTip("最小化到托盘")
        self.btn_minimize.clicked.connect(self.hide_to_tray)
        self.btn_minimize.setStyleSheet(self._title_btn_qss())
        layout.addWidget(self.btn_minimize)

        return bar

    @staticmethod
    def _title_btn_qss() -> str:
        return (
            "QPushButton { background: transparent; border: none; "
            "color: #555; font-size: 16px; font-weight: bold; border-radius: 14px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.08); color: #222; }"
            "QPushButton:pressed { background: rgba(0,0,0,0.15); }"
        )

    def _create_input_area(self) -> QWidget:
        """创建底部输入区域"""
        area = QWidget()
        area.setFixedHeight(50)
        area.setObjectName("inputArea")
        area.setStyleSheet(
            f"QWidget#inputArea {{ "
            f"background: {INPUT_BG}; "
            f"border-bottom-left-radius: {CORNER_RADIUS}px; "
            f"border-bottom-right-radius: {CORNER_RADIUS}px; "
            f"}}"
        )
        layout = QHBoxLayout(area)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("添加任务...")
        self.input_box.setFont(QFont("Microsoft YaHei UI", 12))
        self.input_box.setFixedHeight(34)
        self.input_box.setStyleSheet(
            "QLineEdit { "
            "  background: #fff; border: 1px solid #e0ddd0; "
            "  border-radius: 8px; padding: 0 12px; color: #333; "
            "}"
            "QLineEdit:focus { border-color: #52c41a; }"
        )
        self.input_box.returnPressed.connect(self._on_add_task)
        layout.addWidget(self.input_box, stretch=1)

        btn_add = QPushButton("+")
        btn_add.setFixedHeight(34)
        btn_add.setFixedWidth(34)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setFont(QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold))
        btn_add.setStyleSheet(
            "QPushButton { background: #52c41a; color: #fff; border: none; "
            "border-radius: 8px; }"
            "QPushButton:hover { background: #45a818; }"
            "QPushButton:pressed { background: #3d9215; }"
        )
        btn_add.clicked.connect(self._on_add_task)
        layout.addWidget(btn_add)

        return area

    # ── 圆角背景 + 阴影绘制 ──

    def paintEvent(self, event):
        """绘制圆角背景 + 手绘阴影，避免 QGraphicsDropShadowEffect 的兼容问题"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = self._shadow
        r = CORNER_RADIUS
        w, h = self.width(), self.height()

        # 1) 阴影（多层半透明圆角矩形模拟模糊效果）
        shadow_color = QColor(0, 0, 0, 12)
        for i in range(4):
            offset = i + 1
            rect = s - offset * 2
            path = QPainterPath()
            path.addRoundedRect(
                rect, rect, w - 2 * rect, h - 2 * rect, r, r
            )
            painter.fillPath(path, shadow_color)

        # 2) 主体圆角矩形背景
        main_rect = s
        path = QPainterPath()
        path.addRoundedRect(main_rect, main_rect, w - 2 * main_rect, h - 2 * main_rect, r, r)
        painter.fillPath(path, QColor(BG_COLOR))

    # ── 托盘 ──

    def _setup_tray(self):
        """设置系统托盘图标与右键菜单"""
        self.tray_icon = QSystemTrayIcon(self)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.GlobalColor.transparent)
            p = QPainter(pixmap)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor("#FFFEF0"))
            p.setPen(QPen(QColor("#d9d9d9"), 2))
            p.drawRoundedRect(2, 2, 60, 60, 12, 12)
            p.setFont(QFont("Segoe UI Emoji", 28))
            p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "📌")
            p.end()
            self.tray_icon.setIcon(QIcon(pixmap))

        tray_menu = QMenu()

        action_show = QAction("📋 显示主窗体", self)
        action_show.triggered.connect(self.show_from_tray)
        tray_menu.addAction(action_show)

        tray_menu.addSeparator()

        opacity_menu = tray_menu.addMenu("🔆 透明度")
        for pct in [80, 90, 100]:
            act = QAction(f"{pct}%", self)
            act.triggered.connect(lambda _, p=pct: self.set_window_opacity(p))
            opacity_menu.addAction(act)

        tray_menu.addSeparator()

        action_quit = QAction("退出应用", self)
        action_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage(
            "便签", "已最小化至托盘",
            QSystemTrayIcon.MessageIcon.Information, 1500
        )

    def _quit_app(self):
        self._save_current_state()
        QApplication.quit()

    def set_window_opacity(self, percent):
        self.setWindowOpacity(percent / 100.0)

    # ── 拖动 & 边缘吸附 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 40 + self._shadow:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.drag_pos = None
            self.edge_snap()
        super().mouseReleaseEvent(event)

    def edge_snap(self):
        """拖动释放时，靠近屏幕边缘 20px 内自动贴边"""
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        x, y = self.x(), self.y()

        if abs(x - screen.left()) < margin:
            x = screen.left()
        elif abs(x + self.width() - screen.right()) < margin:
            x = screen.right() - self.width()

        if abs(y - screen.top()) < margin:
            y = screen.top()
        elif abs(y + self.height() - screen.bottom()) < margin:
            y = screen.bottom() - self.height()

        self.move(x, y)

    # ── 折叠/展开 ──

    def toggle_collapse(self):
        if self.is_collapsed:
            self._do_expand()
        else:
            self._do_collapse()

    def _do_collapse(self):
        """折叠为仅标题栏"""
        self.is_collapsed = True
        self.content_widget.hide()
        self.setFixedHeight(FOLD_HEIGHT + self._shadow * 2)
        self.setMinimumHeight(FOLD_HEIGHT + self._shadow * 2)
        self.setMaximumHeight(FOLD_HEIGHT + self._shadow * 2)
        self.btn_collapse.setText("＋")
        self._save_current_state()

    def _do_expand(self):
        """展开恢复"""
        self.is_collapsed = False
        self.setMinimumHeight(FOLD_HEIGHT + self._shadow * 2)
        self.setMaximumHeight(QWIDGETSIZE_MAX)
        self.setFixedHeight(DEFAULT_H)
        self.content_widget.show()
        self.btn_collapse.setText("—")
        self._save_current_state()

    # ── 关闭事件 ──

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()

    # ── 双击标题栏折叠 ──

    def mouseDoubleClickEvent(self, event):
        if event.position().y() < 40 + self._shadow:
            self.toggle_collapse()
        super().mouseDoubleClickEvent(event)

    # ── 任务操作 ──

    def _on_add_task(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.add_task(text)
        self.input_box.clear()

    def add_task(self, text: str):
        task = {
            "id": int(time.time() * 1000),
            "text": text,
            "completed": False,
            "createdAt": int(time.time() * 1000),
        }
        self.tasks.append(task)
        self.render_tasks()
        self._save_current_state()

    def toggle_task(self, task_id: int):
        for t in self.tasks:
            if t["id"] == task_id:
                t["completed"] = not t["completed"]
                break
        self.render_tasks()
        self._save_current_state()

    def delete_task(self, task_id: int):
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self.render_tasks()
        self._save_current_state()

    def _save_current_state(self):
        self.dm.save_data(self, self.tasks, self.is_collapsed)

    # ── 渲染任务列表 ──

    def _create_empty_label(self):
        """创建空状态提示（每次重新创建，避免被 deleteLater 误删）"""
        label = QLabel("暂无任务，按回车添加 ✍", self.task_container)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #cccccc; font-size: 14px;")
        label.setFixedHeight(80)
        return label

    def render_tasks(self):
        """重建任务列表 UI"""
        # 清除旧组件（跳过 stretch 占位符）
        while self.task_layout.count():
            item = self.task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._task_widgets.clear()

        if not self.tasks:
            # 每次重新创建 empty_label，防止被之前的 deleteLater 销毁
            self.empty_label = self._create_empty_label()
            self.task_layout.addWidget(self.empty_label)
            self.task_layout.addStretch()
        else:
            for task in self.tasks:
                widget = self.build_task_widget(task)
                self.task_layout.addWidget(widget)
                self._task_widgets.append(widget)
            self.task_layout.addStretch()

        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t["completed"])
        self.counter_label.setText(f"共 {total} 项 · 已完成 {done} 项")

    def build_task_widget(self, task: dict) -> TaskItemWidget:
        w = TaskItemWidget(
            task,
            on_toggle=self.toggle_task,
            on_delete=self.delete_task,
            parent=self,
        )
        w.setStyleSheet(
            f"TaskItemWidget {{ border-bottom: 1px solid {DIVIDER}; }}"
        )
        return w

    def eventFilter(self, obj, event):
        if obj == self.scroll_area and event.type() == QEvent.Type.Paint:
            pass
        return super().eventFilter(obj, event)


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("StickyNotes")
    app.setQuitOnLastWindowClosed(False)

    window = StickyNotes()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
