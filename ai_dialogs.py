"""
AI 相关弹窗：配置对话框、整理输入对话框、结果预览对话框
"""

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QWidget, QFrame,
)

from ai_organizer import AIOrganizer
from task_tree import build_tree


BG_COLOR = "#FFFEF0"
TITLE_BG = "#FFF9DB"
CORNER_RADIUS = 10


class AIConfigDialog(QDialog):
    """AI 配置弹窗：输入 API 地址、Key、模型名"""

    def __init__(self, config: dict | None = None, parent=None):
        super().__init__(parent)
        self._config = config or {"endpoint": "", "api_key": "", "model": ""}
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("AI 设置")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setFixedHeight(280)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 提示
        hint = QLabel(
            "配置 OpenAI 兼容 API（如 OpenAI、DeepSeek、Ollama 等）。\n"
            "API Key 将保存在本地 JSON 文件中。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)

        # API 地址
        layout.addWidget(QLabel("API 地址："))
        self.edit_endpoint = QLineEdit()
        self.edit_endpoint.setPlaceholderText("https://api.openai.com/v1")
        self.edit_endpoint.setText(self._config.get("endpoint", ""))
        self.edit_endpoint.setFixedHeight(32)
        layout.addWidget(self.edit_endpoint)

        # API Key
        layout.addWidget(QLabel("API Key："))
        self.edit_key = QLineEdit()
        self.edit_key.setPlaceholderText("sk-...")
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_key.setText(self._config.get("api_key", ""))
        self.edit_key.setFixedHeight(32)
        layout.addWidget(self.edit_key)

        # 模型名
        layout.addWidget(QLabel("模型名称："))
        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("gpt-4o-mini（留空则使用服务端默认）")
        self.edit_model.setText(self._config.get("model", ""))
        self.edit_model.setFixedHeight(32)
        layout.addWidget(self.edit_model)

        # 按钮栏
        btn_bar = QHBoxLayout()

        self.btn_test = QPushButton("测试连接")
        self.btn_test.setFixedHeight(32)
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.clicked.connect(self._test_connection)
        btn_bar.addWidget(self.btn_test)

        btn_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setFixedWidth(70)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        btn_save = QPushButton("保存")
        btn_save.setFixedHeight(32)
        btn_save.setFixedWidth(70)
        btn_save.setObjectName("primaryBtn")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)
        btn_bar.addWidget(btn_save)

        layout.addLayout(btn_bar)

        self.setStyleSheet(
            "QDialog { background: #fff; border-radius: 10px; }"
            "QPushButton { border: 1px solid #ccc; border-radius: 6px; background: #f5f5f5; color: #333; }"
            "QPushButton:hover { background: #e8e8e8; }"
            "QPushButton#primaryBtn { background: #52c41a; border-color: #52c41a; color: #fff; }"
            "QPushButton#primaryBtn:hover { background: #45a818; }"
        )

    def _test_connection(self):
        config = self.get_config()
        if not config["endpoint"] or not config["api_key"]:
            QMessageBox.warning(self, "提示", "请先填写 API 地址和 Key")
            return

        self.btn_test.setEnabled(False)
        self.btn_test.setText("测试中...")

        def run_test():
            organizer = AIOrganizer(config)
            return organizer.test_connection()

        thread = _TestThread(run_test)
        thread.finished_signal.connect(
            lambda: self._on_test_result(thread.success, thread.message)
        )
        thread.finished_signal.connect(lambda: self.btn_test.setEnabled(True))
        thread.finished_signal.connect(lambda: self.btn_test.setText("测试连接"))
        thread.start()

    def _on_test_result(self, success, message):
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "失败", message)

    def get_config(self) -> dict:
        return {
            "endpoint": self.edit_endpoint.text().strip(),
            "api_key": self.edit_key.text().strip(),
            "model": self.edit_model.text().strip(),
        }


class AIOrganizePromptDialog(QDialog):
    """AI 整理输入弹窗：显示选中任务，让用户输入目标描述"""

    def __init__(self, focus_task: dict | None, all_tasks: list[dict], parent=None):
        super().__init__(parent)
        self._focus_task = focus_task
        self._all_tasks = all_tasks
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("AI 整理任务")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setFixedHeight(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 标题
        title = QLabel("选择要整理的任务并输入你的目标")
        title.setFont(QFont("", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #333;")
        layout.addWidget(title)

        # 任务预览
        layout.addWidget(QLabel("当前任务列表："))
        self.task_preview = QTextEdit()
        self.task_preview.setReadOnly(True)
        self.task_preview.setMaximumHeight(120)
        self.task_preview.setStyleSheet(
            "QTextEdit { background: #fafafa; border: 1px solid #e0e0e0; "
            "border-radius: 6px; padding: 8px; font-size: 12px; }"
        )
        # 填充任务预览文本
        lines = []
        for t in self._all_tasks:
            status = "[x]" if t.get("completed") else "[ ]"
            indent = "  " * (t.get("level", 1) - 1)
            lines.append(f"{indent}{status} {t['text']}")
        self.task_preview.setPlainText("\n".join(lines) if lines else "暂无任务")
        layout.addWidget(self.task_preview)

        # 目标描述
        layout.addWidget(QLabel("你的目标/说明："))
        self.goal_edit = QTextEdit()
        self.goal_edit.setPlaceholderText(
            "例如：帮我规划一下这个项目的开发步骤，按模块拆分子任务..."
        )
        self.goal_edit.setMinimumHeight(80)
        self.goal_edit.setStyleSheet(
            "QTextEdit { border: 1px solid #e0e0e0; border-radius: 6px; "
            "padding: 8px; font-size: 12px; }"
            "QTextEdit:focus { border-color: #52c41a; }"
        )
        layout.addWidget(self.goal_edit)

        # 按钮栏
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setFixedWidth(70)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        btn_send = QPushButton("发送给 AI")
        btn_send.setFixedHeight(34)
        btn_send.setFixedWidth(100)
        btn_send.setObjectName("primaryBtn")
        btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_send.clicked.connect(self._on_send)
        btn_bar.addWidget(btn_send)

        layout.addLayout(btn_bar)

        self.setStyleSheet(
            "QDialog { background: #fff; border-radius: 10px; }"
            "QPushButton { border: 1px solid #ccc; border-radius: 6px; background: #f5f5f5; color: #333; }"
            "QPushButton:hover { background: #e8e8e8; }"
            "QPushButton#primaryBtn { background: #52c41a; border-color: #52c41a; color: #fff; }"
            "QPushButton#primaryBtn:hover { background: #45a818; }"
        )

    def _on_send(self):
        goal = self.goal_edit.toPlainText().strip()
        if not goal:
            QMessageBox.warning(self, "提示", "请输入你的目标或说明")
            return
        self.accept()

    def get_user_goal(self) -> str:
        return self.goal_edit.toPlainText().strip()


class AIPreviewDialog(QDialog):
    """AI 结果预览弹窗：树形展示 + 接受/放弃/重新生成"""

    def __init__(self, ai_items: list[dict], parent=None):
        super().__init__(parent)
        self._ai_items = ai_items
        self._accepted = False
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("AI 整理结果预览")
        self.setModal(True)
        self.setMinimumSize(450, 350)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 标题
        title = QLabel("AI 整理的任务方案：")
        title.setFont(QFont("", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #333;")
        layout.addWidget(title)

        # 树形预览
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["任务", "层级"])
        self.tree.setColumnWidth(0, 340)
        self.tree.setColumnWidth(1, 50)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(20)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #e0e0e0; border-radius: 6px; "
            "background: #fff; font-size: 12px; }"
            "QTreeWidget::item { padding: 4px 8px; }"
            "QTreeWidget::item:hover { background: #f5f5f5; }"
        )
        self._populate_tree()
        layout.addWidget(self.tree)

        # 按钮栏
        btn_bar = QHBoxLayout()

        btn_discard = QPushButton("放弃")
        btn_discard.setFixedHeight(34)
        btn_discard.setFixedWidth(70)
        btn_discard.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_discard.clicked.connect(self.reject)
        btn_bar.addWidget(btn_discard)

        btn_bar.addStretch()

        btn_regenerate = QPushButton("重新生成")
        btn_regenerate.setFixedHeight(34)
        btn_regenerate.setFixedWidth(100)
        btn_regenerate.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_regenerate.clicked.connect(self._on_regenerate)
        btn_bar.addWidget(btn_regenerate)

        btn_accept = QPushButton("接受并写入")
        btn_accept.setFixedHeight(34)
        btn_accept.setFixedWidth(120)
        btn_accept.setObjectName("primaryBtn")
        btn_accept.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_accept.clicked.connect(self._on_accept)
        btn_bar.addWidget(btn_accept)

        layout.addLayout(btn_bar)

        self.setStyleSheet(
            "QDialog { background: #fff; border-radius: 10px; }"
            "QPushButton { border: 1px solid #ccc; border-radius: 6px; background: #f5f5f5; color: #333; }"
            "QPushButton:hover { background: #e8e8e8; }"
            "QPushButton#primaryBtn { background: #52c41a; border-color: #52c41a; color: #fff; }"
            "QPushButton#primaryBtn:hover { background: #45a818; }"
        )

    def _populate_tree(self):
        """将 AI 返回的 items 填充为 QTreeWidget。"""
        self.tree.clear()
        stack = []  # [(level, QTreeWidgetItem), ...]

        level_names = {1: "目标", 2: "子目标", 3: "任务", 4: "步骤"}

        for item in self._ai_items:
            level = min(max(item.get("level", 1), 1), 4)
            text = item.get("text", "")
            top = QTreeWidgetItem([text, level_names.get(level, str(level))])

            # 找父节点
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1].addChild(top)
            else:
                self.tree.addTopLevelItem(top)

            stack.append((level, top))

        self.tree.expandAll()

    def _on_accept(self):
        self._accepted = True
        self.accept()

    def _on_regenerate(self):
        """重新生成：关闭此窗口（标记为未接受），调用方会重新发起。"""
        self._accepted = False
        self.done(2)  # 自定义返回码 2 = 重新生成

    def is_accepted(self) -> bool:
        return self._accepted

    def get_ai_items(self) -> list[dict]:
        return self._ai_items


class _TestThread(QThread):
    """测试 API 连接的后台线程"""
    finished_signal = pyqtSignal()

    def __init__(self, func):
        super().__init__()
        self._func = func
        self.success = False
        self.message = ""

    def run(self):
        try:
            self.success, self.message = self._func()
        except Exception as e:
            self.success = False
            self.message = str(e)
        finally:
            self.finished_signal.emit()
