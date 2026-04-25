任务便签悬浮窗 — 技术需求文档（V2）
1. 项目概述
开发一个桌面悬浮窗级任务便签应用。启动后以一个小尺寸圆角悬浮窗常驻屏幕，始终置顶，不占用任务栏主窗口位置。支持鼠标拖动任意位置停靠，可最小化至系统托盘。所有任务数据写入本地 JSON 文件，重启电脑后任务与窗口位置均完整保留。
目标平台：跨平台桌面端（Windows/macOS/Linux），优先保证 Windows 体验。
2. 技术栈
表格
层级	技术	说明
语言	Python 3.10+	用户熟悉，生态成熟
GUI 框架	PyQt6 或 PySide6	无边框窗口、置顶、半透明、系统托盘原生支持
数据持久化	JSON + QStandardPaths	存储至系统应用数据目录，非临时文件
打包（可选）	PyInstaller / Nuitka	后续可编译为单文件 .exe 独立运行
依赖安装：
bash
复制
pip install PyQt6
3. 功能需求
3.1 核心任务功能（与之前一致）
添加任务：悬浮窗底部输入框，回车添加；空内容忽略
标记完成：每条任务左侧圆形复选框，勾选后文本置灰+删除线
删除任务：每条任务右侧悬停显示 × 按钮，点击直接删除（无需确认，保持轻量）
任务计数：标题栏或底部显示 共 N 项 · 已完成 M 项
3.2 悬浮窗特有功能
无边框圆角窗体：去除原生标题栏，自定义顶部操作栏，整体圆角 12px
始终置顶：Qt.WindowType.WindowStaysOnTopHint，不被其他窗口遮挡
鼠标拖动：按住顶部自定义标题栏（或按住窗体空白处）可拖动到屏幕任意位置
窗口位置记忆：关闭时记录窗口坐标，下次启动恢复至上一次位置
边缘自动吸附（可选增强）：拖动至距屏幕边缘 20px 内时，自动贴边对齐
折叠/展开：双击标题栏或点击「—」按钮，窗口折叠为仅显示标题栏（高度约 40px），再次操作展开
系统托盘：关闭按钮不退出程序，而是最小化至系统托盘；托盘图标右键菜单提供「显示主窗体」「退出应用」
透明度调节（可选）：右键菜单或设置中可调整窗体透明度（80%-100%）
4. 数据持久化设计
4.1 存储文件
路径：使用 QStandardPaths.StandardLocation.AppDataLocation
Windows: %APPDATA%/StickyNotes/tasks.json
macOS: ~/Library/Application Support/StickyNotes/tasks.json
Linux: ~/.local/share/StickyNotes/tasks.json
自动创建目录：启动时若目录不存在自动创建
4.2 JSON 数据结构
JSON
复制
{
  "version": "1.0",
  "window": {
    "x": 1200,
    "y": 200,
    "width": 320,
    "height": 400,
    "collapsed": false
  },
  "tasks": [
    {
      "id": 1714025600000,
      "text": "准备暑期实习简历",
      "completed": false,
      "createdAt": 1714025600000
    }
  ]
}
window 对象记录窗口几何状态，下次启动直接 move + resize
id 使用 int(time.time() * 1000) 毫秒时间戳，确保唯一
4.3 读写策略
写：任何增删改操作后立即同步写盘（无需防抖，数据量极小）
读：应用启动时一次性读取，异常时（文件损坏/不存在）回退至空列表与默认窗口位置（屏幕右侧居中）
异常处理：try-except 包裹所有文件 IO，损坏时自动重置并备份旧文件为 tasks.json.bak
5. UI/UX 设计规范
5.1 悬浮窗尺寸与外观
默认尺寸：宽 320px，高 400px（展开状态）
最小尺寸：宽 280px，高 200px
折叠尺寸：宽 320px，高 45px（仅保留标题栏）
背景色：#FFFEF0（便签黄）或 #FFFFFF 带轻微阴影
圆角：12px（主窗体）
阴影：QGraphicsDropShadowEffect，偏移 (0, 4)，模糊 16px，颜色 rgba(0,0,0,0.15)
边框：无实体边框，靠阴影区分层级
5.2 自定义标题栏（顶部 40px）
左侧：应用图标（📌）+ 标题「便签」
右侧：三个按钮依次排列
— ：折叠/展开切换
⊘ 或 × ：最小化至托盘（不是退出）
拖动区域：整个标题栏响应鼠标拖动事件
5.3 任务列表区域（中部）
背景略深于窗体（如 #FFFDF5）或分割线区分
列表可滚动，QScrollArea + QWidget 容器，最大高度自适应
单条任务项高度 40px，左右内边距 12px
左侧：自定义复选框（QCheckBox 样式表美化，圆形，选中时绿色对勾）
中间：任务文本，font-size: 14px，完成时 color: #999; text-decoration: line-through;
右侧：删除按钮 ×，默认透明度 0.3，hover 时透明度 1.0，颜色 #FF4444
任务项之间：底部边框 1px solid #f0f0f0 或留白 8px
5.4 输入区域（底部 50px）
固定在底部，背景色与窗体一致或略浅
输入框：QLineEdit，圆角 8px，占位文本 添加任务...
添加按钮：+，与输入框同高，点击或回车触发
5.5 空状态
列表为空时，中部显示居中 QLabel：暂无任务，按回车添加 ✍️，颜色 #cccccc
6. 交互逻辑与核心类设计
6.1 类结构
Python
复制
class StickyNotes(QWidget):
    """主悬浮窗"""
    def __init__(self):
        self.data_file = ...          # JSON 文件路径
        self.tasks = []               # 任务列表
        self.window_state = {}        # 窗口几何状态
        self.is_collapsed = False     # 是否折叠
        self.drag_pos = None          # 拖动用鼠标偏移记录
        
        # UI 组件
        self.title_bar = None         # 顶部自定义标题栏
        self.scroll_area = None       # 任务列表滚动区
        self.task_container = None    # 任务项父容器
        self.input_box = None         # QLineEdit
        self.tray_icon = None         # QSystemTrayIcon
        
    # 窗口行为
    def mousePressEvent(self, event): ...      # 记录拖动起点
    def mouseMoveEvent(self, event): ...       # 实时移动窗口
    def mouseReleaseEvent(self, event): ...    # 结束拖动，触发边缘吸附
    
    # 数据持久化
    def load_data(self) -> dict: ...
    def save_data(self): ...
    
    # 任务操作
    def add_task(self, text: str): ...
    def toggle_task(self, task_id: int): ...
    def delete_task(self, task_id: int): ...
    
    # 渲染
    def render_tasks(self): ...
    def build_task_widget(self, task: dict) -> QWidget: ...
    
    # 悬浮窗特性
    def toggle_collapse(self): ...
    def apply_shadow(self): ...
    def setup_tray(self): ...
    def edge_snap(self): ...         # 边缘吸附计算
6.2 关键实现细节
1. 无边框 + 置顶 + 透明
Python
复制
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint | 
    Qt.WindowType.WindowStaysOnTopHint |
    Qt.WindowType.Tool  # 不在任务栏显示独立图标
)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
2. 拖动逻辑
重写 mousePressEvent：仅当点击在标题栏区域（y < 40）时记录 self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
重写 mouseMoveEvent：若 drag_pos 存在，调用 self.move(event.globalPos() - self.drag_pos)
重写 mouseReleaseEvent：调用 edge_snap()，然后清空 drag_pos
3. 边缘吸附算法
Python
复制
def edge_snap(self):
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
4. 关闭按钮行为（最小化至托盘）
Python
复制
def closeEvent(self, event):
    event.ignore()           # 忽略真正关闭
    self.hide()              # 隐藏窗体
    self.tray_icon.showMessage("便签", "已最小化至托盘", QSystemTrayIcon.MessageIcon.Information, 2000)
5. 复选框样式（QSS）
css
复制
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid #d9d9d9;
}
QCheckBox::indicator:checked {
    background-color: #52c41a;
    border-color: #52c41a;
    image: url(:/check.svg);  /* 或使用内置勾画 */
}
7. 文件结构
plain
复制
sticky-notes/
├── main.py              # 入口文件，初始化 QApplication 并启动 StickyNotes
├── ui/
│   └── main_window.py   # StickyNotes 主类（可由 Claude 单文件实现，也可拆分）
├── assets/
│   └── icon.png         # 托盘图标与应用图标（可用 emoji 📌 临时替代或内嵌 base64）
└── requirements.txt     # PyQt6
单文件交付方案：Claude Code 也可将所有逻辑集中在单个 main.py 中（约 300-400 行），你直接 python main.py 即可运行，便于快速验证。
8. 验收标准
[ ] 运行 python main.py，屏幕出现一个圆角黄色悬浮窗，默认在屏幕右侧居中
[ ] 悬浮窗始终置顶，打开浏览器全屏也不会被遮挡
[ ] 按住顶部标题栏可拖动到屏幕任意位置，释放后若靠近边缘自动贴边
[ ] 在底部输入框打字回车，任务出现在列表，右侧有复选框
[ ] 勾选复选框，任务文本变灰出现删除线；再次点击恢复
[ ] 点击任务右侧 ×，任务消失
[ ] 点击标题栏 — 按钮，窗口折叠为一条标题栏；再次点击展开恢复原高度
[ ] 点击标题栏 × 按钮，窗口消失但程序未退出，系统托盘仍有图标
[ ] 右键系统托盘图标，选择"显示主窗体"，悬浮窗回到上次位置；选择"退出"则程序彻底关闭
[ ] 彻底关闭后重新运行，任务列表、完成状态、窗口位置与折叠状态与上次完全一致
[ ] 查看 %APPDATA%/StickyNotes/tasks.json（或对应系统路径），JSON 数据正确保存