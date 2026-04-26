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

from PyQt6.QtCore import Qt, QEvent, QStandardPaths, pyqtSignal, QMimeData, QTimer
from PyQt6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QIcon, QPixmap, QAction, QRegion,
    QDrag, QCursor,
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
    """单条任务项：复选框 + 文本 + 删除按钮，支持拖拽排序"""

    DRAG_THRESHOLD = 5  # 像素，超过此距离才视为拖拽

    def __init__(self, task, on_toggle, on_delete, show_detail=None, parent=None):
        super().__init__(parent)
        self.task = task
        self._full_text = task["text"]
        self._show_detail = show_detail
        self._drag_start_pos = None
        self._drag_started = False
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start_pos is not None
            and not self._drag_started
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= self.DRAG_THRESHOLD:
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_started = False
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        """启动拖拽：携带任务 ID 作为 MIME 数据"""
        self._drag_started = True
        mime = QMimeData()
        mime.setText(str(self.task["id"]))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._make_drag_pixmap())
        drag.setHotSpot(QCursor.pos() - self.mapToGlobal(self.rect().topLeft()))
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_started = False
        self._drag_start_pos = None

    def _make_drag_pixmap(self) -> QPixmap:
        """生成拖拽时的半透明截图"""
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 120))
        painter.end()
        return pixmap

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
DEAD_ZONE_RATIO = 0.40  # 死区占单条高度的比例，避免交界处抽搐
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
        self._drag_source_id = None
        self._drag_indicator = None
        self._drag_target_idx = -1
        self._drag_last_viewport_y = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(20)
        self._scroll_timer.timeout.connect(self._on_scroll_tick)
        self._scroll_dir = 0  # -1=up, 1=down, 0=none

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
        self.scroll_area.viewport().setAcceptDrops(True)
        self.scroll_area.viewport().installEventFilter(self)
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

    # ── 拖拽排序 ──

    def _get_cursor_in_container_y(self) -> int:
        """获取当前鼠标在 task_container 坐标系中的 Y 值"""
        global_pt = QCursor.pos()
        container_pt = self.task_container.mapFromGlobal(global_pt)
        return container_pt.y()

    def _ensure_drag_indicator(self):
        """创建或获取拖拽占位指示线"""
        if self._drag_indicator is None:
            indicator = QFrame()
            indicator.setFixedHeight(3)
            indicator.setStyleSheet(
                "QFrame { background: #52c41a; border-radius: 1.5px; }"
            )
            indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._drag_indicator = indicator

    def _handle_add_drag(self, event):
        event.acceptProposedAction()
        if event.mimeData().hasText():
            tid = int(event.mimeData().text())
            for t in self.tasks:
                if t["id"] == tid:
                    self._drag_source_id = tid
                    break

    def _get_gap_at_y(self, y):
        """根据 Y 坐标算出应该插入的间隙索引（0 ~ len(tasks)）。
           调用前指示线必须不在 layout 中。"""
        for i, w in enumerate(self._task_widgets):
            if w is None or not w.isVisible():
                continue
            center = w.y() + w.height() // 2
            if y < center:
                return i
        return len(self.tasks)

    def _handle_move_drag(self, event):
        if self._drag_source_id is None:
            return

        vp_y = event.position().y()
        self._drag_last_viewport_y = vp_y

        # 计算边缘滚动：检测区为视口 1/3
        vp_h = self.scroll_area.viewport().height()
        detect_zone = vp_h / 3
        scroll_dir = 0
        if vp_y < detect_zone:
            scroll_dir = -1
        elif vp_y > vp_h - detect_zone:
            scroll_dir = 1

        if scroll_dir != self._scroll_dir:
            self._scroll_dir = scroll_dir
            if scroll_dir != 0 and not self._scroll_timer.isActive():
                self._scroll_timer.start()
            elif scroll_dir == 0 and self._scroll_timer.isActive():
                self._scroll_timer.stop()

        # 更新指示线位置
        y = self._get_cursor_in_container_y()
        self._ensure_drag_indicator()
        layout = self.task_layout

        # 先移除指示线，拿到未偏移的真实 widget 位置
        layout.removeWidget(self._drag_indicator)

        new_gap = self._get_gap_at_y(y)

        # 死区：同一位置不动
        if new_gap == self._drag_target_idx:
            # 重新插回原位置
            self._show_indicator_at(new_gap)
            return
        self._drag_target_idx = new_gap

        self._show_indicator_at(new_gap)
        self._drag_indicator.show()
        event.acceptProposedAction()

    def _show_indicator_at(self, gap_idx):
        """在指定间隙索引处插入指示线"""
        layout = self.task_layout
        if gap_idx >= len(self.tasks):
            layout.addWidget(self._drag_indicator)
        else:
            target_w = self._task_widgets[gap_idx]
            target_idx = layout.indexOf(target_w)
            layout.insertWidget(target_idx, self._drag_indicator)
        self._drag_indicator.show()

    def _on_scroll_tick(self):
        """定时器触发：根据鼠标位置驱动滚动条，然后刷新指示线位置"""
        if self._drag_last_viewport_y is None:
            self._scroll_timer.stop()
            return

        vp_h = self.scroll_area.viewport().height()
        y_vp = self._drag_last_viewport_y

        detect_zone = vp_h / 3
        direction = 0
        if y_vp < detect_zone:
            direction = -1
            d = y_vp
        elif y_vp > vp_h - detect_zone:
            direction = 1
            d = vp_h - y_vp
        else:
            return

        # 距检测区内缘到 1/4 检测区位置逐渐加速，之后一直保持最快
        threshold = detect_zone / 4
        if d <= threshold:
            ratio = 1.0
        else:
            ratio = (detect_zone - d) / (detect_zone - threshold)

        # 加速：1~20px/20ms
        speed = int(1 + 19 * ratio) * direction
        bar = self.scroll_area.verticalScrollBar()
        new_val = bar.value() + speed
        bar.setValue(new_val)

        # 滚动后重新计算指示线
        y_container = self._get_cursor_in_container_y()
        self._ensure_drag_indicator()
        layout = self.task_layout
        layout.removeWidget(self._drag_indicator)
        new_gap = self._get_gap_at_y(y_container)
        if new_gap != self._drag_target_idx:
            self._drag_target_idx = new_gap
        self._show_indicator_at(new_gap)

    def _stop_auto_scroll(self):
        """停止自动滚动"""
        self._scroll_timer.stop()
        self._scroll_dir = 0

    def _handle_leave_drag(self):
        self._drag_source_id = None
        self._drag_target_idx = None
        self._stop_auto_scroll()
        if self._drag_indicator is not None:
            self._drag_indicator.hide()

    def _handle_drop(self, event):
        if self._drag_source_id is None:
            return
        if not event.mimeData().hasText():
            return

        task_id = int(event.mimeData().text())

        # 从列表移除
        old_idx = None
        for i, t in enumerate(self.tasks):
            if t["id"] == task_id:
                old_idx = i
                break
        if old_idx is None:
            return
        task = self.tasks.pop(old_idx)

        # 目标索引用死区计算出的值
        if self._drag_target_idx is None:
            target_idx = len(self.tasks)
        else:
            target_idx = self._drag_target_idx
            # pop 后目标可能前移
            if old_idx < target_idx:
                target_idx -= 1
            target_idx = max(0, min(target_idx, len(self.tasks)))

        if target_idx >= len(self.tasks):
            self.tasks.append(task)
        else:
            self.tasks.insert(target_idx, task)

        # 清理
        self._stop_auto_scroll()
        self._drag_indicator.hide()
        self._drag_indicator = None
        self._drag_source_id = None
        self._drag_target_idx = None
        self.render_tasks()
        self._save_current_state()

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
        viewport = self.scroll_area.viewport()
        if obj == viewport:
            etype = event.type()
            if etype == QEvent.Type.DragEnter:
                self._handle_add_drag(event)
                return True
            elif etype == QEvent.Type.DragMove:
                self._handle_move_drag(event)
                return True
            elif etype == QEvent.Type.DragLeave:
                self._handle_leave_drag()
                return True
            elif etype == QEvent.Type.Drop:
                self._handle_drop(event)
                return True
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
