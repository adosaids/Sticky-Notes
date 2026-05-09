"""
异步聊天 Worker：QThread 内运行 asyncio 事件循环
将流式 chunk 通过 pyqtSignal 推送到 UI
"""

import asyncio
from PyQt6.QtCore import QThread, pyqtSignal


class AsyncChatWorker(QThread):
    """流式 AI 聊天后台线程（asyncio inside QThread）"""
    chunk_received = pyqtSignal(str)
    stream_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, organizer, messages: list[dict], mode: str = "discuss"):
        super().__init__()
        self._organizer = organizer
        self._messages = messages
        self._mode = mode

    def run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        await self._organizer.chat(
            self._messages,
            on_chunk=self.chunk_received.emit,
            on_complete=lambda: self.stream_complete.emit(),
            on_error=self.error_occurred.emit,
            mode=self._mode,
        )
