"""
AI 聊天面板：浮动对话窗口，异步流式输出，多轮对话
"""

import json
import re

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QWidget, QScrollArea, QFrame, QMessageBox,
)

from ai_async_worker import AsyncChatWorker

# 延迟导入，避免循环依赖
_main_module = None

def _get_main():
    global _main_module
    if _main_module is None:
        import main as _main_module
    return _main_module


BG_COLOR = "#FFFEF0"
USER_BUBBLE = "#dcf8c6"
AI_BUBBLE = "#FFFFFF"
WRITE_INSTRUCTION = (
    "请将上述讨论内容整理为层级化任务列表，返回 JSON 数组。\n"
    '每个对象格式：{"text": "...", "level": 1~4}\n'
    "只返回 JSON，不要其他文字。"
)


class AIChatPanel(QDialog):
    """浮动聊天面板：async 流式 + 多轮对话 + 讨论/写入分离"""

    tasks_accepted = pyqtSignal(list)

    def __init__(self, tasks: list[dict], ai_organizer, user_goal: str = "", parent=None):
        super().__init__(parent)
        self._organizer = ai_organizer
        self._all_tasks = tasks
        self._messages = []  # [{role, content}, ...]
        self._current_ai_text = ""
        self._bubbles = []
        self._is_streaming = False
        self._write_mode = False  # 是否处于写入模式

        self._setup_ui()
        self._position()

        # 预填提示文本，用户自己编辑发送
        if user_goal:
            self.input_box.setPlainText(user_goal)
            self.input_box.setFocus()

        # 拖拽支持
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 只在标题栏区域（顶部 40px）触发拖拽
            if event.position().y() <= 40:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _setup_ui(self):
        self.setWindowTitle("AI 任务整理")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(400, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 外层容器
        container = QWidget()
        container.setObjectName("chatContainer")
        container.setStyleSheet(
            "QWidget#chatContainer {"
            f"  background: {BG_COLOR}; border-radius: 10px;"
            "}"
        )
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setObjectName("chatTitleBar")
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(
            "QWidget#chatTitleBar {"
            f"  background: #FFF9DB; border-top-left-radius: 10px; border-top-right-radius: 10px;"
            "}"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)

        title_icon = QLabel("🤖")
        title_icon.setFont(_ui_font(14))
        title_layout.addWidget(title_icon)

        title_label = QLabel("AI 任务整理")
        title_label.setFont(_ui_font(13, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333;")
        title_layout.addWidget(title_label, stretch=1)

        btn_close = QPushButton("×")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setObjectName("chatCloseBtn")
        btn_close.setStyleSheet(
            "QPushButton#chatCloseBtn {"
            "  background: transparent; border: none; color: #999;"
            "  font-size: 20px; font-weight: bold; border-radius: 14px;"
            "}"
            "QPushButton#chatCloseBtn:hover {"
            "  background: rgba(0,0,0,0.08); color: #333;"
            "}"
        )
        btn_close.clicked.connect(self.hide)
        title_layout.addWidget(btn_close)
        inner.addWidget(title_bar)

        # 消息滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #d0d0d0; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self.msg_container = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(12, 12, 12, 12)
        self.msg_layout.setSpacing(8)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_container)
        inner.addWidget(self.scroll, stretch=1)

        # 分隔线
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #e0ddd0;")
        inner.addWidget(divider)

        # 底部输入区
        input_bar = QWidget()
        input_bar.setObjectName("chatInputBar")
        input_bar.setStyleSheet(
            "QWidget#chatInputBar {"
            f"  background: {BG_COLOR}; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;"
            "}"
        )
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入追问或补充说明...")
        self.input_box.setMaximumHeight(60)
        self.input_box.setMinimumHeight(34)
        self.input_box.setFont(_ui_font(12))
        self.input_box.setStyleSheet(
            "QTextEdit {"
            "  background: #fff; border: 1px solid #e0ddd0;"
            "  border-radius: 8px; padding: 6px 10px; color: #333;"
            "}"
            "QTextEdit:focus { border-color: #52c41a; }"
        )
        self.input_box.setAcceptRichText(False)
        self.input_box.textChanged.connect(self._on_input_resize)
        input_layout.addWidget(self.input_box, stretch=1)

        self.btn_send = QPushButton("发送")
        self.btn_send.setFixedHeight(34)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.setObjectName("chatSendBtn")
        self.btn_send.setStyleSheet(
            "QPushButton#chatSendBtn {"
            "  background: #52c41a; color: #fff; border: none;"
            "  border-radius: 8px; font-size: 13px; padding: 0 14px;"
            "}"
            "QPushButton#chatSendBtn:hover { background: #45a818; }"
            "QPushButton#chatSendBtn:disabled { background: #ccc; }"
        )
        self.btn_send.clicked.connect(self._on_send)
        input_layout.addWidget(self.btn_send)

        self.btn_write = QPushButton("写入任务")
        self.btn_write.setFixedHeight(34)
        self.btn_write.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_write.setObjectName("chatWriteBtn")
        self.btn_write.setStyleSheet(
            "QPushButton#chatWriteBtn {"
            "  background: #1890ff; color: #fff; border: none;"
            "  border-radius: 8px; font-size: 13px; padding: 0 14px;"
            "}"
            "QPushButton#chatWriteBtn:hover { background: #1278d8; }"
            "QPushButton#chatWriteBtn:disabled { background: #ccc; }"
        )
        self.btn_write.clicked.connect(self._on_write_tasks)
        self.btn_write.setEnabled(False)
        input_layout.addWidget(self.btn_write)

        inner.addWidget(input_bar)
        layout.addWidget(container)

    def _on_input_resize(self):
        """输入框多行时自动调整高度。"""
        doc = self.input_box.document()
        h = min(60, max(34, int(doc.size().height()) + 16))
        self.input_box.setFixedHeight(h)

    def _position(self):
        if self.parent():
            geo = self.parent().geometry()
            x = geo.right() + 6
            y = geo.top()
            screen = self.screen().geometry()
            if x + self.minimumWidth() > screen.right():
                x = max(screen.left() + 10, geo.left() - self.minimumWidth() - 6)
            x = max(screen.left() + 10, min(x, screen.right() - self.minimumWidth() - 10))
            y = max(screen.top() + 10, min(y, screen.bottom() - self.minimumHeight() - 10))
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    # ── 消息气泡 ──

    def _add_user_bubble(self, text: str):
        bubble = self._create_bubble(text, USER_BUBBLE, align_right=True)
        self._insert_bubble(bubble)

    def _add_ai_bubble_start(self):
        self._current_ai_text = ""
        bubble = self._create_bubble("", AI_BUBBLE, align_right=False)
        self._insert_bubble(bubble)
        return bubble

    def _update_ai_bubble(self, text: str, bubble):
        self._current_ai_text += text
        label = bubble.findChild(QLabel, "bubbleContent")
        if label:
            display = self._format_display(self._current_ai_text)
            label.setText(display)
        self._scroll_to_bottom()

    def _finalize_ai_bubble(self, bubble):
        label = bubble.findChild(QLabel, "bubbleContent")
        if label:
            self._messages.append({"role": "assistant", "content": self._current_ai_text})
        self.btn_send.setEnabled(True)
        self._is_streaming = False

        # 写入模式：流式结束后解析 JSON 并弹窗确认
        if self._write_mode:
            self._write_mode = False
            self._confirm_write_tasks()
        else:
            self.btn_write.setEnabled(True)

    @staticmethod
    def _format_display(text: str) -> str:
        """流式文本格式化显示：支持 markdown 和 JSON。"""
        stripped = text.strip()

        # 1. 如果整体是合法 JSON 数组 → 渲染为任务列表
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                items = json.loads(stripped)
                if isinstance(items, list):
                    return _render_tasks(items)
            except json.JSONDecodeError:
                pass

        # 2. 提取 markdown 代码块中的 JSON
        md_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if md_match:
            json_str = md_match.group(1).strip()
            try:
                items = json.loads(json_str)
                if isinstance(items, list):
                    return _render_tasks(items)
            except json.JSONDecodeError:
                partial = _partial_json_items(json_str)
                if partial:
                    return _render_tasks(partial)

        # 3. 非 JSON → 渲染 markdown 为基本 HTML
        return _render_markdown(text)

    def _create_bubble(self, text: str, bg_color: str, align_right: bool) -> QWidget:
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        if align_right:
            wl.setAlignment(Qt.AlignmentFlag.AlignRight)

        label = QLabel(text if text else "思考中...")
        label.setObjectName("bubbleContent")
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet(
            f"QLabel {{ background: {bg_color}; padding: 8px 10px; "
            "border-radius: 10px; color: #333; font-size: 12px; }}"
        )
        # 用 setMaximumWidth 替代 QSS max-width
        label.setMaximumWidth(320)
        label.setMinimumWidth(80)
        wl.addWidget(label)
        return wrapper

    def _insert_bubble(self, bubble):
        self.msg_layout.addWidget(bubble)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(50, lambda: bar.setValue(bar.maximum()))

    # ── 发送消息 ──

    def _on_send(self):
        text = self.input_box.toPlainText().strip()
        if not text or self._is_streaming:
            return
        self.input_box.clear()
        self.send_message(text, mode="discuss")

    def send_message(self, text: str, mode: str = "discuss"):
        self._add_user_bubble(text)
        self._messages.append({"role": "user", "content": text})

        ai_bubble = self._add_ai_bubble_start()
        self._is_streaming = True
        self._write_mode = (mode == "write")
        self.btn_send.setEnabled(False)
        self.btn_write.setEnabled(False)

        worker = AsyncChatWorker(self._organizer, list(self._messages), mode=mode)
        worker.chunk_received.connect(lambda t: self._update_ai_bubble(t, ai_bubble))
        worker.stream_complete.connect(lambda: self._finalize_ai_bubble(ai_bubble))
        worker.error_occurred.connect(self._on_stream_error)
        worker.start()
        self._stream_worker = worker

    def _on_stream_error(self, msg: str):
        self._is_streaming = False
        self._write_mode = False
        self.btn_send.setEnabled(True)
        if self._bubbles and not self._current_ai_text:
            self._finalize_ai_bubble(self._bubbles[-1])
        QMessageBox.warning(self, "AI 错误", f"流式请求失败:\n{msg}")

    # ── 写入任务 ──

    def _on_write_tasks(self):
        if not self._messages:
            return

        last_assistant = None
        for m in reversed(self._messages):
            if m["role"] == "assistant":
                last_assistant = m["content"]
                break

        if not last_assistant:
            QMessageBox.information(self, "提示", "还没有 AI 的回复，无法写入任务。")
            return

        # 先尝试从已有回复中解析 JSON
        tasks = _parse_tasks_from_text(last_assistant)
        if tasks:
            self._confirm_tasks(tasks)
            return

        # 没有 JSON → 发起新一轮 AI 请求（写入模式）
        self._messages.append({"role": "user", "content": WRITE_INSTRUCTION})
        self._is_streaming = True
        self.btn_write.setEnabled(False)
        self.btn_send.setEnabled(False)

        ai_bubble = self._add_ai_bubble_start()
        worker = AsyncChatWorker(self._organizer, list(self._messages), mode="write")
        worker.chunk_received.connect(lambda t: self._update_ai_bubble(t, ai_bubble))
        worker.stream_complete.connect(lambda: self._finalize_ai_bubble(ai_bubble))
        worker.error_occurred.connect(self._on_stream_error)
        worker.start()
        self._stream_worker = worker

    def _confirm_write_tasks(self):
        """从最新 AI 回复解析 JSON 后弹窗确认。"""
        last_assistant = None
        for m in reversed(self._messages):
            if m["role"] == "assistant":
                last_assistant = m["content"]
                break
        if not last_assistant:
            return
        tasks = _parse_tasks_from_text(last_assistant)
        if tasks:
            self._confirm_tasks(tasks)

    def _confirm_tasks(self, tasks: list[dict]):
        task_count = len(tasks)
        reply = QMessageBox.question(
            self, "确认写入",
            f"共 {task_count} 项任务，是否写入到便签？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.tasks_accepted.emit(tasks)

    def show_again(self):
        """重新打开聊天面板。"""
        self._position()


def _ui_font(size, weight=QFont.Weight.Normal):
    m = _get_main()
    return m.UI_FONT(size, weight)


# ── 任务列表渲染 ──

def _render_tasks(items: list[dict]) -> str:
    """将任务列表渲染为 HTML（用于 QLabel RichText 显示）。"""
    lines = []
    level_icons = {1: "🎯", 2: "📂", 3: "📋", 4: "📌"}
    for item in items:
        level = item.get("level", 1)
        text = item.get("text", "")
        indent = (level - 1) * 20
        icon = level_icons.get(level, "•")
        lines.append(
            f'<div style="margin-left:{indent}px;padding:2px 0;">'
            f'<span style="color:#888;">{icon}</span> {text}</div>'
        )
    return "".join(lines)


def _partial_json_items(text: str) -> list[dict]:
    """从部分 JSON 文本中尝试提取已完整的任务项。"""
    # 尝试逐个匹配 {"text":"...","level":N} 片段
    pattern = r'\{[^{}]*"text"\s*:\s*"([^"]*)"[^{}]*"level"\s*:\s*(\d+)[^{}]*\}'
    matches = re.findall(pattern, text)
    if matches:
        return [{"text": t, "level": int(l)} for t, l in matches]
    return []


def _render_markdown(text: str) -> str:
    """将简单 markdown 转为 HTML（用于 QLabel RichText 显示）。"""
    # 先转义 HTML 特殊字符
    lines = text.split("\n")
    html_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 代码块：跳过（保留原始）
        if line.startswith("```"):
            html_lines.append('<pre style="background:#f5f5f5;padding:6px;border-radius:4px;'
                              'font-family:Consolas,monospace;font-size:11px;">')
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                html_lines.append(lines[i].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                i += 1
            if i < len(lines):
                i += 1  # skip closing ```
            html_lines.append("</pre>")
            continue

        # H3: ###
        if line.startswith("### "):
            html_lines.append(f'<b style="font-size:13px;color:#333;">{line[4:]}</b><br>')
            i += 1
            continue

        # H2: ##
        if line.startswith("## "):
            html_lines.append(f'<b style="font-size:14px;color:#1a1a1a;margin-top:4px;">{line[3:]}</b><br>')
            i += 1
            continue

        # H1: #
        if line.startswith("# "):
            html_lines.append(f'<b style="font-size:15px;color:#1a1a1a;margin-top:4px;">{line[2:]}</b><br>')
            i += 1
            continue

        # 列表项：- xxx 或 * xxx
        if re.match(r"^\s*[-*] ", line):
            indent = len(line) - len(line.lstrip())
            content = re.sub(r"^\s*[-*] ", "", line)
            content = _inline_md(content)
            left = 8 + indent
            html_lines.append(
                f'<div style="margin-left:{left}px;padding:1px 0;">'
                f'<span style="color:#888;">&#8226;</span> {content}</div>'
            )
            i += 1
            continue

        # 数字列表：1. xxx
        if re.match(r"^\s*\d+\.\s", line):
            content = re.sub(r"^\s*\d+\.\s", "", line)
            content = _inline_md(content)
            html_lines.append(
                f'<div style="margin-left:8px;padding:1px 0;">'
                f'{content}</div>'
            )
            i += 1
            continue

        # 空行
        if line.strip() == "":
            html_lines.append('<br>')
            i += 1
            continue

        # 普通文本（处理行内 markdown）
        html_lines.append(f'<div style="padding:1px 0;">{_inline_md(line)}</div>')
        i += 1

    return "".join(html_lines)


def _inline_md(text: str) -> str:
    """处理行内 markdown：**加粗**、`代码`、~~删除线~~。"""
    # 转义 HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # **加粗**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # *斜体*
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    # `代码`
    text = re.sub(r"`(.+?)`", r'<code style="background:#f0f0f0;padding:1px 4px;'
                  'border-radius:3px;font-family:Consolas,monospace;font-size:11px;">\1</code>', text)
    # ~~删除线~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    return text


def _parse_tasks_from_text(text: str) -> list[dict] | None:
    """从文本中提取 JSON 数组。"""
    try:
        items = json.loads(text)
        if isinstance(items, list):
            return items
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n?```", text)
    if match:
        try:
            items = json.loads(match.group(1))
            if isinstance(items, list):
                return items
        except json.JSONDecodeError:
            pass

    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            items = json.loads(match.group(0))
            if isinstance(items, list):
                return items
        except json.JSONDecodeError:
            pass

    return None
