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

from PyQt6.QtCore import Qt, QEvent, QStandardPaths, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QIcon, QPixmap, QAction, QRegion,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea,
    QCheckBox, QSystemTrayIcon, QMenu, QFrame,
    QWIDGETSIZE_MAX, QTextEdit, QMessageBox,
    QGraphicsDropShadowEffect,
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
                "width": DEFAULT_W, "height": DEFAULT_H,
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
            data["window"].setdefault("width", DEFAULT_W)
            data["window"].setdefault("height", DEFAULT_H)
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

class RoundCheckBox(QWidget):
    """自定义圆形复选框：手绘圆形，确保各平台都显示为完美圆形"""
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._hover = False
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, state):
        self._checked = state
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)

        if self._checked:
            painter.setBrush(QColor("#52c41a"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(r)
            pen = QPen(QColor("#fff"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            cx, cy = r.center().x(), r.center().y()
            painter.drawLine(int(cx - 3), int(cy), int(cx - 1), int(cy + 2))
            painter.drawLine(int(cx - 1), int(cy + 2), int(cx + 4), int(cy - 2))
        else:
            painter.setPen(QPen(QColor("#52c41a" if self._hover else "#d9d9d9"), 2))
            painter.setBrush(QColor("#fff"))
            painter.drawEllipse(r)


class TaskDetailPopup(QWidget):
    """双击任务条后弹出的详情悬浮窗：圆角 + 阴影 + 自动换行完整文本 + 删除按钮"""

    delete_requested = pyqtSignal(int)

    def __init__(self, task_text: str, task_id: int, on_delete, parent=None):
        super().__init__(parent)
        self.task_text = task_text
        self.task_id = task_id
        self.on_delete = on_delete
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 内部容器（圆角背景 + 白色填充）
        container = QWidget()
        container.setObjectName("detailContainer")
        container.setStyleSheet(
            "QWidget#detailContainer {"
            f"  background: {BG_COLOR}; border-radius: {CORNER_RADIUS}px;"
            "}"
        )
        inner = QVBoxLayout(container)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(8)

        # 顶部栏：标题 + 关闭按钮
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        title = QLabel("任务详情")
        title.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #333;")
        top_bar.addWidget(title, stretch=1)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setObjectName("detailCloseBtn")
        btn_close.setStyleSheet(
            "QPushButton#detailCloseBtn {"
            "  background: transparent; border: none; color: #999;"
            "  font-size: 18px; font-weight: bold; border-radius: 11px;"
            "}"
            "QPushButton#detailCloseBtn:hover {"
            "  background: rgba(0,0,0,0.08); color: #333;"
            "}"
        )
        btn_close.clicked.connect(self.close)
        top_bar.addWidget(btn_close)
        inner.addLayout(top_bar)

        # 内容区：只读 QTextEdit（自动换行）
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(self.task_text)
        self.text_edit.setFont(QFont("Microsoft YaHei UI", 12))
        self.text_edit.setStyleSheet(
            "QTextEdit {"
            "  background: #fff; border: 1px solid #e0ddd0;"
            "  border-radius: 8px; padding: 8px 10px; color: #333;"
            "}"
        )
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setMinimumHeight(100)
        inner.addWidget(self.text_edit)

        # 底部：删除按钮
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 4, 0, 0)
        btn_bar.addStretch()

        btn_del = QPushButton("删除任务")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setObjectName("detailDelBtn")
        btn_del.setStyleSheet(
            "QPushButton#detailDelBtn {"
            "  background: transparent; border: 1px solid #FF4444;"
            "  color: #FF4444; border-radius: 6px;"
            "  font-size: 12px; padding: 4px 14px;"
            "}"
            "QPushButton#detailDelBtn:hover {"
            "  background: #FF4444; color: #fff;"
            "}"
        )
        btn_del.clicked.connect(self._on_delete)
        btn_bar.addWidget(btn_del)
        inner.addLayout(btn_bar)

        layout.addWidget(container)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 50))
        container.setGraphicsEffect(shadow)

        # 固定宽度，高度根据内容自适应
        self.setFixedWidth(300)

    def _on_delete(self):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条任务吗？\n{self.task_text[:60]}{'...' if len(self.task_text) > 60 else ''}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.task_id)
            self.close()

    def show_at(self, parent_widget):
        """定位到父组件右侧弹出，超出屏幕则换到左侧"""
        geo = parent_widget.geometry()
        screen = QApplication.primaryScreen().geometry()
        popup_w = self.width()
        super().show()
        # 用 QTextEdit.document().size() 估算内容高度
        doc_h = self.text_edit.document().size().height()
        # 加上顶部标题栏、边距、底部按钮的大致高度
        estimated_h = max(200, min(450, int(doc_h + 90)))
        self.setFixedHeight(estimated_h)

        popup_h = self.height()
        x = geo.right() + 6
        y = geo.top()
        # 右侧不够 → 左侧
        if x + popup_w > screen.right():
            x = geo.left() - popup_w - 6
        x = max(screen.left() + 10, min(x, screen.right() - popup_w - 10))
        y = max(screen.top() + 10, min(y, screen.bottom() - popup_h - 10))
        self.move(x, y)


class TaskItemWidget(QWidget):
    """单条任务项：复选框 + 文本 + 删除按钮"""

    def __init__(self, task, on_toggle, on_delete, show_detail=None, parent=None):
        super().__init__(parent)
        self.task = task
        self._full_text = task["text"]
        self._show_detail = show_detail
        self.setFixedHeight(40)
        self._setup_ui(on_toggle, on_delete)
        self._apply_style()

    def _setup_ui(self, on_toggle, on_delete):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self.cb = RoundCheckBox(checked=self.task["completed"])
        self.cb.toggled.connect(lambda: on_toggle(self.task["id"]))
        layout.addWidget(self.cb)

        self.label = QLabel(self.task["text"])
        self.label.setFont(QFont("Microsoft YaHei UI", 12))
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.label.setWordWrap(False)
        self.label.setMinimumWidth(40)
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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._show_detail:
            # 点击 checkbox 区域不触发详情
            cb_rect = self.cb.geometry()
            if not cb_rect.contains(event.position().toPoint()):
                self._show_detail(self.task["id"])
                return
        super().mouseDoubleClickEvent(event)


# ──────────────────────────────────────────────
# 主悬浮窗
# ──────────────────────────────────────────────

BG_COLOR = "#FFFEF0"
TITLE_BG = "#FFF9DB"
INPUT_BG = "#FFFEF0"
DIVIDER = "#f0ece0"
FOLD_HEIGHT = 32
DEFAULT_W, DEFAULT_H = 260, 300
CORNER_RADIUS = 10
SHADOW_WIDTH = 4  # 阴影外扩宽度


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
        self._task_widgets = []
        self.empty_label = None

        self._init_window()
        self._load_and_restore()
        self._setup_ui()
        self._setup_tray()
        self._restore_geometry()

    # ── 窗口初始化 ──

    def _init_window(self):
        """无边框、置顶、不在任务栏显示，setMask 裁剪圆角"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMinimumSize(DEFAULT_W, FOLD_HEIGHT)
        self.resize(DEFAULT_W, DEFAULT_H)
        self.setStyleSheet(f"background: {BG_COLOR};")
        self._apply_mask()

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
        """构建全部 UI 组件"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
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
        self.btn_collapse = QPushButton("-")
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

    # ── 圆角裁剪 ──

    def _apply_mask(self):
        """用 setMask 裁剪窗口为圆角矩形"""
        r = CORNER_RADIUS
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def resizeEvent(self, event):
        """窗口大小变化时重新应用圆角裁剪"""
        super().resizeEvent(event)
        self._apply_mask()

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
            if event.position().y() < 40:
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
        self.setFixedHeight(FOLD_HEIGHT + SHADOW_WIDTH * 2)
        self.setMinimumHeight(FOLD_HEIGHT + SHADOW_WIDTH * 2)
        self.setMaximumHeight(FOLD_HEIGHT + SHADOW_WIDTH * 2)
        self.btn_collapse.setText("＋")
        self._save_current_state()

    def _do_expand(self):
        """展开恢复"""
        self.is_collapsed = False
        self.setMinimumHeight(FOLD_HEIGHT + SHADOW_WIDTH * 2)
        self.setMaximumHeight(QWIDGETSIZE_MAX)
        self.setFixedHeight(DEFAULT_H)
        self.content_widget.show()
        self.btn_collapse.setText("-")
        self._save_current_state()

    # ── 关闭事件 ──

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()

    # ── 双击标题栏折叠 ──

    def mouseDoubleClickEvent(self, event):
        if event.position().y() < 40 + SHADOW_WIDTH:
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
            show_detail=self._show_task_detail,
            parent=self,
        )
        w.setStyleSheet(
            f"TaskItemWidget {{ border-bottom: 1px solid {DIVIDER}; }}"
        )
        return w

    def _show_task_detail(self, task_id: int):
        """双击任务条时弹出详情悬浮窗"""
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            return
        # 关闭已存在的弹窗
        if hasattr(self, "_detail_popup") and self._detail_popup.isVisible():
            self._detail_popup.close()
        popup = TaskDetailPopup(task["text"], task_id, self.delete_task, self)
        popup.delete_requested.connect(self.delete_task)
        self._detail_popup = popup
        # 找到对应的 TaskItemWidget
        for w in self._task_widgets:
            if w.task["id"] == task_id:
                popup.show_at(w)
                break

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
