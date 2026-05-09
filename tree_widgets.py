"""
层级任务组件：带缩进 + 展开/收起箭头 + 右键菜单
"""

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor, QPixmap, QDrag, QAction
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QMenu,
)

from task_tree import has_children


DIVIDER = "#f0ece0"
INDENT_PX = 20  # 每级缩进像素


class HierarchicalTaskItemWidget(QWidget):
    """单条层级任务项：[展开箭头] [复选框] [文本] [删除]

    保留原 TaskItemWidget 的拖拽排序、双击详情等行为。
    """

    DRAG_THRESHOLD = 5

    def __init__(
        self,
        task,
        on_toggle,
        on_delete,
        on_expand_toggle=None,
        show_detail=None,
        on_ai_organize=None,
        parent=None,
    ):
        super().__init__(parent)
        self.task = task
        self._full_text = task["text"]
        self._show_detail = show_detail
        self._on_expand_toggle = on_expand_toggle
        self._on_ai_organize = on_ai_organize
        self._drag_start_pos = None
        self._drag_started = False

        level = task.get("level", 1)
        indent = (level - 1) * INDENT_PX
        self.setFixedHeight(40)
        self._setup_ui(on_toggle, on_delete, indent)
        self._apply_style()

    def _setup_ui(self, on_toggle, on_delete, indent):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12 + indent, 4, 12, 4)
        layout.setSpacing(6)

        # 展开/收起箭头
        self.btn_expand = QPushButton()
        self.btn_expand.setFixedSize(16, 16)
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setObjectName("expandBtn")
        self.btn_expand.clicked.connect(self._on_expand_click)
        self._update_expand_icon()
        layout.addWidget(self.btn_expand)

        self.cb = RoundCheckBox(checked=self.task["completed"])
        self.cb.toggled.connect(lambda: on_toggle(self.task["id"]))
        layout.addWidget(self.cb)

        self.label = QLabel(self.task["text"])
        self.label.setFont(_ui_font(12))
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
        self.btn_expand.setStyleSheet(
            "QPushButton#expandBtn {"
            "    background: transparent; border: none;"
            "    color: #888; font-size: 10px;"
            "}"
            "QPushButton#expandBtn:hover {"
            "    color: #333;"
            "}"
        )

    def _update_text_style(self):
        if self.task["completed"]:
            self.label.setStyleSheet("color: #999999; text-decoration: line-through;")
        else:
            self.label.setStyleSheet("color: #333333;")

    def _update_expand_icon(self):
        """更新展开/收起箭头图标。有子任务才显示箭头。"""
        if not hasattr(self, "btn_expand"):
            return
        pid = self.task["id"]
        parent_tasks = getattr(self, "_all_tasks", [])
        if has_children(pid, parent_tasks):
            collapsed = self.task.get("collapsed", False)
            icon = "▶" if collapsed else "▼"
            self.btn_expand.setText(icon)
            self.btn_expand.setVisible(True)
        else:
            self.btn_expand.setVisible(False)

    def _on_expand_click(self):
        if self._on_expand_toggle:
            self._on_expand_toggle(self.task["id"])

    def enterEvent(self, event):
        self.btn_del.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_del.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_started = False
        super().mousePressEvent(event)

    def _show_context_menu(self, global_pos):
        """右键菜单：AI 整理任务"""
        if not self._on_ai_organize:
            return
        menu = QMenu(self)
        ai_action = QAction("AI 整理任务", self)
        ai_action.triggered.connect(lambda: self._on_ai_organize(self.task["id"]))
        menu.addAction(ai_action)
        menu.exec(global_pos)

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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._show_detail:
            cb_rect = self.cb.geometry()
            expand_rect = self.btn_expand.geometry()
            pos = event.position().toPoint()
            # 点击 checkbox 或展开箭头区域不触发详情
            if not cb_rect.contains(pos) and not expand_rect.contains(pos):
                self._show_detail(self.task["id"])
                return
        super().mouseDoubleClickEvent(event)

    def _start_drag(self):
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
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 120))
        painter.end()
        return pixmap


class RoundCheckBox(QWidget):
    """自定义圆形复选框（与 main.py 中的 RoundCheckBox 相同）"""

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


def _ui_font(size, weight=QFont.Weight.Normal):
    """从 main.py 获取 UI 字体（延迟导入避免循环）"""
    from main import UI_FONT
    return UI_FONT(size, weight)
