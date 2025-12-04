import sys
import os
import time
import requests  # 新增：用于调用接口
from datetime import datetime

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTextEdit,
    QPushButton, QSpinBox, QFileDialog, QHBoxLayout,
    QVBoxLayout, QGroupBox, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QLineEdit, QStyle, QProxyStyle, QLabel
)
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen, QBrush, QLinearGradient
import math  # 动态背景：用于计算渐变的平滑变化


# ===== 统一 QSS 样式构建函数（只保留深色科技蓝主题） =====
def build_common_qss() -> str:
    """
    4a4e69 灰紫主题 QSS（统一圆角 + 半透明）
    """
    return """
    QWidget {
        background-color: #4a4e69;               /* 主题底色 */
        color: #f2e9e4;
        font-family: "Microsoft YaHei";
        font-size: 11pt;
    }

    QMainWindow {
        background-color: #4a4e69;
    }

    QLabel {
        background-color: rgba(0, 0, 0, 10);
        border-radius: 6px;
        padding: 2px 6px;
    }

    /* ========== 卡片外框 ========== */
    QGroupBox {
        background-color: rgba(74, 78, 105, 200);       /* 4a4e69 半透明 */
        border: 1px solid rgba(154, 140, 152, 200);     /* 9a8c98 柔和高亮边 */
        border-radius: 18px;
        margin-top: 18px;
        padding: 12px 12px 14px 12px;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px;
        color: #f2e9e4;
        font-weight: 700;
        font-size: 12pt;
        letter-spacing: 1px;
        font-family: "Microsoft YaHei";
    }

    QGroupBox:hover {
        border-color: #c9ada7;
    }

    /* ========== 按钮（含开始生成） ========== */
    QPushButton {
        border: 1px solid #9a8c98;
        border-radius: 10px;
        padding: 6px 16px;
        background-color: rgba(60, 63, 88, 220);
        font-size: 10pt;
        font-weight: 500;
        color: #f2e9e4;
    }

    QPushButton:hover {
        background-color: rgba(82, 86, 113, 220);
    }

    QPushButton:pressed {
        background-color: #c9ada7;
    }

    QPushButton:disabled {
        border-color: #6b6b7f;
        color: #b0b0c0;
        background-color: rgba(60, 63, 88, 220);
    }

    QPushButton#PrimaryButton {
        background-color: #9a8c98;      /* 主按钮：偏暖灰紫 */
        border: 1px solid #c9ada7;
        color: #2b2d42;
    }

    QPushButton#PrimaryButton:hover {
        background-color: #c9ada7;
    }

    QPushButton#PrimaryButton:pressed {
        background-color: #f2e9e4;
    }

    /* ========== 输入框 / 数字框 ========== */
    QLineEdit,
    QSpinBox {
        background-color: rgba(43, 45, 66, 220);   /* 稍深的灰紫 */
        border: 1px solid #3b3f59;
        border-radius: 10px;
        padding: 4px 6px;
        font-size: 10pt;
    }

    QLineEdit:focus,
    QSpinBox:focus {
        border: 1px solid #c9ada7;
    }

    QCheckBox {
        background-color: rgba(43, 45, 66, 250);
        border-radius: 10px;
        padding: 2px 8px;
    }

    /* ========== 文本区域 / 列表 ========== */
    QTextEdit,
    QListWidget {
        background-color: rgba(39, 41, 61, 250);
        border: 1px solid rgba(33, 35, 52, 250);
        border-radius: 14px;
        padding: 4px;
    }

    QListWidget::item {
        padding: 4px 6px;
    }

    QListWidget::item:hover {
        background-color: rgba(82, 86, 113, 240);
    }

    QListWidget::item:selected {
        background-color: #9a8c98;
        color: #2b2d42;
    }

    QTextEdit#LogText,
    QListWidget#HistoryList {
        background-color: rgba(33, 35, 52, 240);
        border-radius: 14px;
        border: 1px solid rgba(23, 24, 38, 240);
        font-family: "Consolas", "Cascadia Code", "Courier New";
        font-size: 9pt;
        padding: 4px;
    }

    /* ========== 进度条 ========== */
    QProgressBar {
        background-color: rgba(33, 35, 52, 220);
        border: 1px solid #3b3f59;
        border-radius: 12px;
        text-align: center;
        padding: 2px;
        color: #f2e9e4;
    }

    QProgressBar::chunk {
        border-radius: 10px;
        background-color: qlineargradient(
            spread:pad, x1:0, y1:0, x2:1, y2:0,
            stop:0 #9a8c98,
            stop:1 #c9ada7
        );
    }

    /* ========== 滚动条 ========== */
    QScrollBar:vertical {
        background: transparent;
        width: 10px;
        margin: 2px 0 2px 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(154, 140, 152, 240);
        border-radius: 5px;
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        background: transparent;
        height: 10px;
        margin: 0 2px 0 2px;
    }
    QScrollBar::handle:horizontal {
        background: rgba(154, 140, 152, 240);
        border-radius: 5px;
    }
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        width: 0;
    }

    /* ========== 弹窗 & 标题 & 状态徽章 ========== */
    QMessageBox {
        background-color: #4a4e69;
    }

    QMessageBox QLabel {
        color: #f2e9e4;
    }

    QLabel#TitleLabel {
        font-size: 14pt;
        font-weight: 700;
        letter-spacing: 3px;
        font-family: "Microsoft YaHei";
        background-color: rgba(0, 0, 0, 0);
        border-radius: 6px;
        padding: 4px 10px;
    }

    QLabel#StatusBadge {
        padding: 2px 10px;
        border-radius: 999px;
        background-color: #3b3f59;
        color: #f2e9e4;
        font-size: 9pt;
        font-family: "Microsoft YaHei";
    }
    """

#Config
# 你的 FastAPI 服务器地址
# 如果是本地测试用 127.0.0.1，如果是远程服务器请填写真实 IP
API_URL = "http://127.0.0.1:8000/generate_motion"

# --------- 原 InterGen 模型部分 (已删除) ---------
# 不需要再 import torch 或 infer 了
# 也不需要加载 heavy model checkponts
# -----------------------------------------------

def call_api_generate(prompt: str, output_dir: str, log_callback=None) -> str:
    """
    调用 FastAPI 接口生成视频，并保存到本地。
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    _log(f"正在连接服务器: {API_URL} ...")

    # 1. 准备请求数据
    # 注意：根据你之前的 FastAPI 代码，接口只接受 {"text": "..."}
    # 如果后续服务端更新支持了 num_frames 或 seed，可以在这里添加到 payload 中
    payload = {
        "text": prompt
    }

    try:
        # 2. 发送请求 (设置超时时间，因为生成视频可能较慢)
        # stream=True 允许我们分块下载大文件（虽然这里视频不大，但好习惯）
        start_time = time.time()
        response = requests.post(API_URL, json=payload, stream=True, timeout=300)
        
        if response.status_code == 200:
            _log("服务器处理成功，正在下载视频...")
            
            # 3. 构造保存路径
            os.makedirs(output_dir, exist_ok=True)
            safe_prompt = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt)
            safe_prompt = safe_prompt.strip().replace(" ", "_")[:40] or "motion"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_prompt}_{timestamp}.mp4"
            save_path = os.path.join(output_dir, filename)

            # 4. 写入文件
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            elapsed = time.time() - start_time
            _log(f"下载完成！耗时: {elapsed:.2f}s")
            return save_path
        else:
            # 处理服务器错误信息
            error_detail = "Unknown Error"
            try:
                error_detail = response.json().get("detail", response.text)
            except:
                error_detail = response.text
            raise Exception(f"Server Error ({response.status_code}): {error_detail}")

    except requests.exceptions.ConnectionError:
        raise Exception(f"无法连接到服务器。请确认服务器已启动且地址正确: {API_URL}")
    except Exception as e:
        raise e


# --------- PyQt5 界面部分 (保留你的逻辑，修改 Worker) ---------

class GenerationWorker(QThread):
    """在子线程中调用 API，避免卡死界面。"""
    progress_changed = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished_ok = pyqtSignal(str, dict)
    error = pyqtSignal(str)

    def __init__(self, prompt: str, params: dict, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.params = params
        self._is_interrupted = False

    def run(self):
        try:
            def log_cb(msg: str):
                self.log_message.emit(msg)

            self.log_message.emit(">>> 开始请求远程生成...")
            self.progress_changed.emit(10) # 模拟进度

            # 调用 API 函数
            output_dir = self.params.get("output_dir")

            # 注意：API请求通常是阻塞的，很难获得精确的“生成进度百分比”。
            # 我们只能模拟一个“等待中”的状态。
            self.progress_changed.emit(30)

            if self._is_interrupted: raise RuntimeError("用户取消")

            # 支持先调用翻译接口将 prompt 翻译为目标语言（默认英语）
            translate_flag = self.params.get("translate", False)
            target_lang = self.params.get("target_lang", "English")
            prompt_to_send = self.prompt

            if translate_flag:
                try:
                    self.log_message.emit(">>> 请求翻译服务，将 prompt 翻译为目标语言...")
                    base = API_URL.rsplit('/', 1)[0]
                    translate_url = f"{base}/translate"
                    tr_resp = requests.post(translate_url, json={"text": self.prompt, "target_lang": target_lang}, timeout=30)
                    if tr_resp.status_code == 200:
                        tr_json = tr_resp.json()
                        translated = tr_json.get("translation") or tr_json.get("translated")
                        if translated:
                            prompt_to_send = translated
                            self.log_message.emit(f">>> 翻译完成: {translated}")
                        else:
                            raise RuntimeError("翻译响应格式不包含 translation 字段")
                    else:
                        raise RuntimeError(f"翻译服务错误 ({tr_resp.status_code}): {tr_resp.text}")
                except Exception as e:
                    self.error.emit(f"翻译失败: {e}")
                    return

            # --- 核心修改：调用 API 而不是本地模型 ---
            output_path = call_api_generate(
                prompt_to_send,
                output_dir,
                log_callback=log_cb
            )
            # -------------------------------------

            if self._is_interrupted:
                self.error.emit("生成已被用户中断")
            else:
                self.progress_changed.emit(100)
                self.finished_ok.emit(output_path, self.params)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_interrupted = True

class CheckBoxBorderStyle(QProxyStyle):
    """保留你的样式类"""
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_IndicatorCheckBox:
            super().drawPrimitive(element, option, painter, widget)
            rect = option.rect.adjusted(1, 1, -1, -1)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            # 这里原来是 #00bcd4（青色），改成主题相关的柔和灰紫
            pen = QPen(QColor("#c9ada7"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.restore()
        else:
            super().drawPrimitive(element, option, painter, widget)


class AnimatedBackgroundWidget(QWidget):
    """
    背景容器（已去掉渐变和动画）：
    - 使用一个纯色背景 #4a4e69
    - 作为 central widget，内部再放现有的 layout 和控件
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 不需要定时器和相位等动画变量了
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        # 纯色背景：4a4e69
        painter.fillRect(rect, QBrush(QColor("#4a4e69")))



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(" 智 创 帧 生 ") # 改个标题
        self.resize(1100, 700)

        self.worker = None
        self._init_ui()

    def _init_ui(self):
        # 使用带动态渐变背景的容器作为 central widget
        central = AnimatedBackgroundWidget(self)  # 动态背景
        self.setCentralWidget(central)

        # ===== 美化修改：外层使用垂直布局，上方放标题栏，下方放左右分栏 =====
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # ---------- 顶部标题栏 ----------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        root_layout.addLayout(header_layout)

        self.title_label = QLabel("智创帧生——多模态驱动的交互式人体动画生成平台")
        self.title_label.setObjectName("TitleLabel")  # 绑定 QSS 样式
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.status_label = QLabel("API: 未检测")
        self.status_label.setObjectName("StatusBadge")  # 绑定 QSS 样式
        header_layout.addWidget(self.status_label)

        # ---------- 主体左右分栏 ----------
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)
        root_layout.addLayout(main_layout)

        # 左侧布局
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)  # 左侧内部控件间距
        main_layout.addLayout(left_layout, 2)

        # 1. 文本描述
        prompt_group = QGroupBox("文本描述 (Text Prompt)")
        left_layout.addWidget(prompt_group)
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("例如：两个人正在跳舞/Two people are boxing.（支持不同语言输入）")
        prompt_layout.addWidget(self.prompt_edit)

        # 2. 生成参数
        params_group = QGroupBox("生成参数")
        left_layout.addWidget(params_group)
        form = QFormLayout(params_group)

        # 注意：因为目前的服务器端代码只接收 'text'，
        # 这里的 '帧数' 和 '种子' 暂时无法生效，除非更新服务器代码。
        # 我保留界面，但添加提示。
        
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(10, 2000)
        self.frames_spin.setValue(210)
        self.frames_spin.setEnabled(False) # 暂时禁用，因为服务端是固定的
        self.frames_spin.setToolTip("当前服务端版本使用固定帧数")
        form.addRow("帧数 (服务端固定)：", self.frames_spin)

        seed_layout = QHBoxLayout()
        self.seed_spin = QSpinBox()
        self.seed_spin.setEnabled(False) # 暂时禁用
        self.random_seed_checkbox = QCheckBox("随机种子")
        self.random_seed_checkbox.setChecked(True)
        self.random_seed_checkbox.setEnabled(False) # 暂时禁用
        self.random_seed_checkbox.setStyle(CheckBoxBorderStyle(self.random_seed_checkbox.style()))
        seed_layout.addWidget(self.seed_spin)
        seed_layout.addWidget(self.random_seed_checkbox)
        form.addRow("随机种子 (服务端控制)：", seed_layout)

        # 输出目录
        outdir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        # 默认保存到当前目录下的 downloaded_videos
        default_save = os.path.join(os.getcwd(), "downloaded_videos")
        self.output_dir_edit.setText(default_save)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._choose_output_dir)
        outdir_layout.addWidget(self.output_dir_edit)
        outdir_layout.addWidget(browse_btn)
        form.addRow("保存路径：", outdir_layout)

        # 按钮区域
        btn_layout = QHBoxLayout()
        left_layout.addLayout(btn_layout)

        self.generate_btn = QPushButton("开始生成")
        self.generate_btn.setObjectName("PrimaryButton")  # 美化：设为主按钮样式
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        btn_layout.addWidget(self.generate_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)

        open_dir_btn = QPushButton("打开文件夹")
        open_dir_btn.clicked.connect(self._open_output_dir)
        btn_layout.addWidget(open_dir_btn)


        # 右侧布局
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)  # ===== 右侧内部控件间距 =====
        main_layout.addLayout(right_layout, 3)

        # 结果列表
        result_group = QGroupBox("生成历史")
        right_layout.addWidget(result_group, 3)
        result_layout = QVBoxLayout(result_group)
        self.result_list = QListWidget()
        self.result_list.setObjectName("HistoryList")  # 美化：统一历史列表样式
        self.result_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        result_layout.addWidget(self.result_list)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(24)
        right_layout.addWidget(self.progress_bar, 0)

        # 日志
        log_group = QGroupBox("客户端日志")
        right_layout.addWidget(log_group, 2)
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setObjectName("LogText")  # 美化：统一日志区域样式
        log_layout.addWidget(self.log_edit)

    # ---------- 逻辑部分 ----------

    def _choose_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def _on_generate_clicked(self):
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "请输入文本描述")
            return

        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            output_dir = os.path.join(os.getcwd(), "downloaded_videos")
            self.output_dir_edit.setText(output_dir)

        # 参数收集（虽然部分目前没用，但保留结构）
        params = {
            "output_dir": output_dir,
            # 是否先调用后端翻译接口将 prompt 翻译为英语再生成
            "translate": True,
            "target_lang": "English",
        }

        self._log(">>> 准备请求生成...")
        self._log(f"Prompt: {prompt}")

        # UI 状态更新
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        if hasattr(self, "status_label"):
            self.status_label.setText("API: 请求中...")

        # 启动线程
        self.worker = GenerationWorker(prompt, params)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.log_message.connect(self._log)
        self.worker.finished_ok.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_generation_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_stop_clicked(self):
        if self.worker:
            self.worker.stop()
            self._log("尝试中断请求（如果数据已在传输中可能无法立刻停止）...")

    def _open_output_dir(self):
        dir_path = self.output_dir_edit.text().strip()
        if not os.path.isdir(dir_path):
             # 尝试创建
            try:
                os.makedirs(dir_path, exist_ok=True)
            except:
                pass
        
        if os.path.isdir(dir_path):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(dir_path)
                elif sys.platform == "darwin":
                    os.system(f'open "{dir_path}"')
                else:
                    os.system(f'xdg-open "{dir_path}"')
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def _play_video_in_widget(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        self._log(f"播放: {abs_path}")
        try:
            if sys.platform.startswith("win"):
                os.startfile(abs_path)
            elif sys.platform == "darwin":
                os.system(f'open "{abs_path}"')
            else:
                os.system(f'xdg-open "{abs_path}"')
        except Exception as e:
            QMessageBox.warning(self, "播放失败", str(e))

    def _on_result_double_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path and os.path.isfile(path):
            self._play_video_in_widget(path)
        else:
            QMessageBox.warning(self, "错误", "文件不存在")

    def _on_progress_changed(self, value: int):
        self.progress_bar.setValue(value)

    def _on_generation_finished(self, output_path: str, params: dict):
        self._log(f"保存成功: {output_path}")
        if hasattr(self, "status_label"):
            self.status_label.setText("API: 正常")
        item_text = f"[{datetime.now().strftime('%H:%M:%S')}] {os.path.basename(output_path)}"
        item = QListWidgetItem(item_text)
        item.setToolTip(output_path)
        item.setData(Qt.UserRole, output_path)
        self.result_list.addItem(item)
        self.result_list.scrollToBottom()

        reply = QMessageBox.question(self, "完成", "视频已下载，是否立即播放？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            self._play_video_in_widget(output_path)

    def _on_generation_error(self, message: str):
        self._log(f"错误: {message}")
        if hasattr(self, "status_label"):
            self.status_label.setText("API: 错误")
        QMessageBox.critical(self, "生成失败", message)
        if hasattr(self, "status_label") and "错误" not in self.status_label.text():
            # 如果不是错误状态，则标记为空闲/待命
            self.status_label.setText("API: 待命")

    def _on_worker_finished(self):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.worker = None

    def _log(self, message: str):
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        text = f"{timestamp} {message}"
        if self.log_edit:
            self.log_edit.append(text)
            self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        print(text)

# --------------------- 主题 (保留 + QSS 美化) -------------------------
def apply_dark_tech_theme(app: QApplication):
    app.setStyle("Fusion")
    base_font = QFont("Microsoft YaHei", 10)
    app.setFont(base_font)

    palette = QPalette()

    # 整体背景：4a4e69 系列
    palette.setColor(QPalette.Window, QColor("#4a4e69"))
    palette.setColor(QPalette.AlternateBase, QColor("#3b3f59"))

    # 内容区 / 输入框
    palette.setColor(QPalette.Base,   QColor("#2b2d42"))
    palette.setColor(QPalette.Button, QColor("#5c607a"))

    # 文本颜色
    palette.setColor(QPalette.WindowText, QColor("#f2e9e4"))
    palette.setColor(QPalette.Text,       QColor("#f2e9e4"))
    palette.setColor(QPalette.ButtonText, QColor("#f2e9e4"))
    palette.setColor(QPalette.ToolTipBase, QColor("#f2e9e4"))
    palette.setColor(QPalette.ToolTipText, QColor("#2b2d42"))

    # 高亮：用偏暖灰紫，而不是蓝色/绿色
    palette.setColor(QPalette.Highlight,        QColor("#c9ada7"))
    palette.setColor(QPalette.HighlightedText,  QColor("#2b2d42"))

    # 错误/警告用略偏橘红
    palette.setColor(QPalette.BrightText, QColor("#e07a5f"))

    app.setPalette(palette)

    # 应用统一 QSS
    app.setStyleSheet(build_common_qss())




def main():
    app = QApplication(sys.argv)
    apply_dark_tech_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()