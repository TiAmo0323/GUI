import sys
import os
import time
import requests  # 新增：用于调用接口
from datetime import datetime

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTextEdit,
    QPushButton, QSpinBox, QFileDialog, QHBoxLayout,
    QVBoxLayout, QGroupBox, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QLineEdit, QStyle, QProxyStyle
)
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen

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
            pen = QPen(QColor("#00bcd4"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.restore()
        else:
            super().drawPrimitive(element, option, painter, widget)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("InterGen 客户端 (API Mode)") # 改个标题
        self.resize(1100, 700)

        self.worker = None
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # 左侧布局
        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, 2)

        # 1. 文本描述
        prompt_group = QGroupBox("文本描述 (Text Prompt)")
        left_layout.addWidget(prompt_group)
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("例如：Two people are boxing.")
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

        self.generate_btn = QPushButton("开始生成") # 改名
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
        main_layout.addLayout(right_layout, 3)

        # 结果列表
        result_group = QGroupBox("生成历史")
        right_layout.addWidget(result_group, 3)
        result_layout = QVBoxLayout(result_group)
        self.result_list = QListWidget()
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
        QMessageBox.critical(self, "生成失败", message)

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

# --------------------- 主题 (保留) -------------------------
def apply_dark_tech_theme(app: QApplication):
    app.setStyle("Fusion")
    base_font = QFont("Microsoft YaHei", 10)
    app.setFont(base_font)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 18))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(24, 24, 24))
    palette.setColor(QPalette.AlternateBase, QColor(18, 18, 18))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(30, 30, 30))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Highlight, QColor(0, 188, 212))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { background-color: 
            #121212; color: #f5f5f5; 
            font-family: 
            "Microsoft YaHei"; 
            font-size: 20px; 
        }
            
        QGroupBox { border: 1px solid #263238; 
            border-radius: 8px;
            margin-top: 12px; 
            padding-top: 10px; 
            font-size: 20px;
         }
         
        QGroupBox::title { subcontrol-origin: margin; 
            left: 10px; 
            padding: 0 6px; 
            color: #00bcd4; 
            font-weight: 600; 
            font-size: 20px;
        }
        
        QPushButton { border: 1px solid #00bcd4; 
            border-radius: 4px; 
            padding: 4px 10px; 
            background-color: #1e1e1e; 
            font-size: 20px;
        }
        QPushButton:hover { background-color: #263238; }
        QPushButton:pressed { background-color: #004d60; }
        QPushButton:disabled { border-color: #455a64; color: #78909c; }
        
        QLineEdit, QTextEdit, QSpinBox { background-color: #1e1e1e; 
            border: 1px solid #37474f; 
            border-radius: 4px; 
            padding: 2px 4px; 
            font-size: 20px;
        }
        
        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border: 1px solid #00bcd4; }
        
        QListWidget, QProgressBar { background-color: #1e1e1e; 
            border: 1px solid #37474f; 
            border-radius: 4px; 
            font-size: 20px;
        }
        QProgressBar::chunk { background-color: #00bcd4; }
    """)

def main():
    app = QApplication(sys.argv)
    apply_dark_tech_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()