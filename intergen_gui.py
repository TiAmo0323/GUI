import sys
import os
import time
import random
from datetime import datetime
from collections import OrderedDict

import torch

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
# from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
# from PyQt5.QtMultimediaWidgets import QVideoWidget
# from PyQt5.QAxContainer import QAxWidget

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QTextEdit,
    QPushButton, QSpinBox, QFileDialog, QHBoxLayout,
    QVBoxLayout, QGroupBox, QFormLayout, QCheckBox,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QStyle, QProxyStyle
)

from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen   # 导入颜色库等

# --------- InterGen 模型封装部分 ---------

# 假设本文件和 infer.py 在同一目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

# 为了兼容 infer.py 里对 sys.path 的处理，这里也把上级目录加进去
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from infer import LitGenModel, build_models, get_config  # 来自你原来的 infer.py

# 配置文件路径（如果你的路径和原来的 infer.py 不一样，请在这里修改）
# 这里使用相对路径：上一级目录 + configs
MODEL_CFG_PATH = os.path.join(REPO_ROOT, "configs", "model.yaml")
INFER_CFG_PATH = os.path.join(REPO_ROOT, "configs", "infer.yaml")

_INTERGEN_MODEL = None   # type: LitGenModel
_MODEL_CFG = None
_INFER_CFG = None


def get_litmodel(log_callback=None) -> LitGenModel:
    """
    懒加载 InterGen 模型：第一次调用时加载，以后直接复用。
    """
    global _INTERGEN_MODEL, _MODEL_CFG, _INFER_CFG

    if _INTERGEN_MODEL is not None:
        return _INTERGEN_MODEL

    def _log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    _log("开始加载 InterGen 配置和模型...")

    # 1. 读取配置
    model_cfg = get_config(MODEL_CFG_PATH)
    infer_cfg = get_config(INFER_CFG_PATH)

    # 2. 构建模型
    model = build_models(model_cfg)

    # 3. 加载 checkpoint（完全照搬你 infer.py 里的写法）
    if getattr(model_cfg, "CHECKPOINT", None):
        _log(f"从 {model_cfg.CHECKPOINT} 加载 checkpoint...")
        ckpt = torch.load(model_cfg.CHECKPOINT, map_location="cpu")
        for k in list(ckpt["state_dict"].keys()):
            if "model" in k:
                ckpt["state_dict"][k.replace("model.", "")] = ckpt["state_dict"].pop(k)
        model.load_state_dict(ckpt["state_dict"], strict=False)
        _log("checkpoint state loaded!")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    litmodel = LitGenModel(model, infer_cfg).to(device)
    litmodel.eval()

    _INTERGEN_MODEL = litmodel
    _MODEL_CFG = model_cfg
    _INFER_CFG = infer_cfg

    _log("InterGen 模型加载完成。")

    return _INTERGEN_MODEL


def generate_motion_with_intergen(prompt: str, params: dict,
                                  progress_callback=None,
                                  log_callback=None) -> str:
    """
    使用 InterGen 生成一段双人动作，并保存为 mp4，返回文件路径。
    这里直接调用你 infer.py 里的 LitGenModel.generate_loop 和 plot_t2m。
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    # 1. 获取 / 初始化模型
    litmodel = get_litmodel(log_callback=_log)

    # 2. 设置随机种子（如果用户不勾选“随机种子”）
    if not params.get("use_random_seed", True) and params.get("seed") is not None:
        seed = int(params["seed"])
        _log(f"使用固定随机种子：{seed}")
        random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    else:
        _log("使用随机种子（不固定）。")

    # 3. 构造 batch，并调用 generate_loop
    device = next(litmodel.parameters()).device
    batch = OrderedDict()
    batch["motion_lens"] = torch.zeros(1, 1, dtype=torch.long, device=device)
    batch["prompt"] = prompt

    num_frames = int(params.get("num_frames", 210))
    _log(f"准备生成 {num_frames} 帧的动作序列...")
    if progress_callback:
        progress_callback(10)

    # 这一行就是调用 InterGen 的真正推理
    sequences = litmodel.generate_loop(batch, num_frames)

    if progress_callback:
        progress_callback(70)

    # 4. 保存为 mp4（利用 LitGenModel 里已经写好的 plot_t2m）
    output_dir = params.get("output_dir") or os.path.join(CURRENT_DIR, "results")
    os.makedirs(output_dir, exist_ok=True)

    # 用时间戳和前若干个字符生成文件名
    safe_prompt = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt)
    safe_prompt = safe_prompt.strip().replace(" ", "_")[:40] or "motion"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_prompt}_{timestamp}.mp4"

    result_path = os.path.join(output_dir, filename)

    # 调用原来的可视化函数
    litmodel.plot_t2m([sequences[0], sequences[1]], result_path, prompt)
    _log(f"已保存到：{result_path}")

    if progress_callback:
        progress_callback(100)

    return result_path


# --------- PyQt5 界面部分 ---------


class GenerationWorker(QThread):
    """在子线程中调用 InterGen 推理，避免卡死界面。"""
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
            def progress_cb(value: int):
                if self._is_interrupted:
                    raise RuntimeError("生成已被用户中断")
                self.progress_changed.emit(value)

            def log_cb(msg: str):
                self.log_message.emit(msg)

            output_path = generate_motion_with_intergen(
                self.prompt,
                self.params,
                progress_callback=progress_cb,
                log_callback=log_cb
            )

            if self._is_interrupted:
                self.error.emit("生成已被用户中断")
            else:
                self.finished_ok.emit(output_path, self.params)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        # 注意：这只是设置一个标记，不能立刻中断 GPU 计算
        self._is_interrupted = True

class CheckBoxBorderStyle(QProxyStyle):
    """只给 QCheckBox 的对勾区域画一圈边框，保留系统原本的对勾"""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_IndicatorCheckBox:
            # 1. 先让基类画原来的对勾
            super().drawPrimitive(element, option, painter, widget)

            # 2. 再在同一块区域外面画一个方形边框
            rect = option.rect.adjusted(1, 1, -1, -1)  # 稍微缩一点，避免贴边
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor("#00bcd4"))   # 你的科技蓝
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.restore()
        else:
            # 其它元素保持默认效果
            super().drawPrimitive(element, option, painter, widget)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("InterGen 双人动作生成 - PyQt5 GUI")
        self.resize(1100, 700)

        self.worker = None

        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # 左侧：文本 + 参数 + 按钮
        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, 2)

        # 文本描述
        prompt_group = QGroupBox("文本描述 (Text Prompt)")
        left_layout.addWidget(prompt_group)
        prompt_layout = QVBoxLayout(prompt_group)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("例如：Two people are boxing.")
        prompt_layout.addWidget(self.prompt_edit)

        # 生成参数
        params_group = QGroupBox("生成参数 (Generation Parameters)")
        left_layout.addWidget(params_group)
        form = QFormLayout(params_group)

        # 帧数
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(10, 2000)
        self.frames_spin.setValue(210)  # 和原 infer.py 中 window_size 一致
        form.addRow("帧数 (num_frames)：", self.frames_spin)

        # 随机种子
        seed_layout = QHBoxLayout()
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.random_seed_checkbox = QCheckBox("使用随机种子（忽略左边的数值）")
        self.random_seed_checkbox.setChecked(True)
        # “带边框”的界面样式
        self.random_seed_checkbox.setStyle(CheckBoxBorderStyle(self.random_seed_checkbox.style()))

        seed_layout.addWidget(self.seed_spin)
        seed_layout.addWidget(self.random_seed_checkbox)
        form.addRow("随机种子 (seed)：", seed_layout)

        # 输出目录
        outdir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录，默认是 ./results")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._choose_output_dir)
        outdir_layout.addWidget(self.output_dir_edit)
        outdir_layout.addWidget(browse_btn)
        form.addRow("输出目录：", outdir_layout)

        # 按钮区域
        btn_layout = QHBoxLayout()
        left_layout.addLayout(btn_layout)

        self.generate_btn = QPushButton("开始生成")
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        btn_layout.addWidget(self.generate_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)

        open_dir_btn = QPushButton("打开输出目录")
        open_dir_btn.clicked.connect(self._open_output_dir)
        btn_layout.addWidget(open_dir_btn)

        # 右侧：结果列表 + 进度条 + 日志
        right_layout = QVBoxLayout()
        main_layout.addLayout(right_layout, 3)

        # 结果列表：上方视频预览，下方结果列表
        result_group = QGroupBox("生成结果 (Generated Videos)")
        right_layout.addWidget(result_group,3)
        result_layout = QVBoxLayout(result_group)

        # 用列表占满整个结果区域，双击后用系统默认播放器打开
        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        result_layout.addWidget(self.result_list)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(24)
        right_layout.addWidget(self.progress_bar,0)

        # 日志
        log_group = QGroupBox("日志 (Log)")
        right_layout.addWidget(log_group,2)
        log_layout = QVBoxLayout(log_group)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)

        # 注释掉这部分内容，使三个空间把右边区域占满
        # right_layout.addStretch(1)

    # ---------- 左侧按钮逻辑 ----------

    def _choose_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def _on_generate_clicked(self):
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "请先输入文本描述（prompt）")
            return

        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            output_dir = os.path.join(CURRENT_DIR, "results")
            self.output_dir_edit.setText(output_dir)

        params = {
            "num_frames": self.frames_spin.value(),
            "use_random_seed": self.random_seed_checkbox.isChecked(),
            "seed": None if self.random_seed_checkbox.isChecked() else self.seed_spin.value(),
            "output_dir": output_dir,
        }

        self._log("开始生成任务...")
        self._log(f"Prompt: {prompt}")
        self._log(f"参数: {params}")

        # UI 状态
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
        if self.worker is not None:
            self._log("请求停止生成（注意：正在进行的推理无法立刻中断）...")
            self.worker.stop()

    def _open_output_dir(self):
        dir_path = self.output_dir_edit.text().strip()
        if not dir_path:
            dir_path = os.path.join(CURRENT_DIR, "results")
        if not os.path.isdir(dir_path):
            QMessageBox.warning(self, "错误", f"目录不存在：{dir_path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(dir_path)
            elif sys.platform == "darwin":
                os.system(f'open "{dir_path}"')
            else:
                os.system(f'xdg-open "{dir_path}"')
        except Exception as e:
            QMessageBox.warning(self, "错误", f"打开目录失败：{e}")

    # ---------- 内嵌视频播放辅助函数 ----------
    # ---------- 视频播放辅助函数（使用系统默认播放器） ----------
    def _play_video_in_widget(self, file_path: str):
        """使用系统默认播放器播放指定本地视频"""
        abs_path = os.path.abspath(file_path)
        self._log(f"尝试使用系统默认播放器播放：{abs_path}")

        try:
            if sys.platform.startswith("win"):
                os.startfile(abs_path)
            elif sys.platform == "darwin":
                os.system(f'open "{abs_path}"')
            else:
                os.system(f'xdg-open "{abs_path}"')
        except Exception as e2:
            self._log(f"系统默认播放器播放失败：{e2}")
            QMessageBox.warning(self, "视频播放错误",
                                f"无法播放视频：\n{e2}")

    # ---------- 右侧交互 ----------

    def _on_result_double_clicked(self, item: QListWidgetItem):
        """双击历史结果时，使用系统默认播放器播放对应视频"""
        path = item.data(Qt.UserRole)
        if path and os.path.isfile(path):
            self._play_video_in_widget(path)
        else:
            QMessageBox.warning(self, "错误", "文件不存在或路径无效。")

    def _on_progress_changed(self, value: int):
        self.progress_bar.setValue(value)

    def _on_generation_finished(self, output_path: str, params: dict):
        self._log(f"生成完成：{output_path}")

        # 仍然把结果记录到列表中
        item_text = f"[{datetime.now().strftime('%H:%M:%S')}] {os.path.basename(output_path)}"
        item = QListWidgetItem(item_text)
        item.setToolTip(output_path)
        item.setData(Qt.UserRole, output_path)
        self.result_list.addItem(item)
        self.result_list.scrollToBottom()

        # 生成完成后弹出对话框，询问是否立即播放视频
        reply = QMessageBox.question(
            self,
            "生成完成",
            f"生成完成！\n文件已保存到：\n{output_path}\n\n是否立即播放该视频？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self._play_video_in_widget(output_path)
        else:
            self._log("用户选择暂不立即播放视频。")

    def _on_generation_error(self, message: str):
        self._log(f"错误：{message}")
        QMessageBox.critical(self, "错误", f"生成过程中出现错误：\n{message}")

    def _on_worker_finished(self):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.worker = None

    # ---------- 日志输出 ----------

    def _log(self, message: str):
        """将日志写入右侧日志框，并同步打印到控制台"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        text = f"{timestamp} {message}"

        # 写到 QTextEdit
        if hasattr(self, "log_edit") and self.log_edit is not None:
            self.log_edit.append(text)
            # 自动滚动到底部
            scroll = self.log_edit.verticalScrollBar()
            scroll.setValue(scroll.maximum())

        # 同时输出到终端，方便调试
        print(text)


# ---------------------主题设置函数-------------------------
def apply_dark_tech_theme(app: QApplication):
    """应用深色科技风主题到整个应用"""
    # 使用 Fusion 基础风格，方便统一重绘
    app.setStyle("Fusion")

    base_font = QFont("Microsoft YaHei", 11)  # 11pt 大小，可根据需要再调大/调小
    app.setFont(base_font)

    # 1）调色板：控制系统控件的基础颜色
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 18))         # 主背景
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(24, 24, 24))           # 文本编辑框背景
    palette.setColor(QPalette.AlternateBase, QColor(18, 18, 18))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(30, 30, 30))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Highlight, QColor(0, 188, 212))     # 高亮：青蓝色
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    # 2）样式表：做“科技感”的细节优化
    app.setStyleSheet("""
        QWidget {
            background-color: #121212;
            color: #f5f5f5;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            font-size: 20px;
        }

        QGroupBox {
            border: 1px solid #263238;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #00bcd4;
            font-weight: 600;
            font-size: 20px;
        }

        QPushButton {
            border: 1px solid #00bcd4;
            border-radius: 4px;
            padding: 4px 10px;
            background-color: #1e1e1e;
            font-size: 20px;
        }
        QPushButton:hover {
            background-color: #263238;
        }
        QPushButton:pressed {
            background-color: #004d60;
        }
        QPushButton:disabled {
            border-color: #455a64;
            color: #78909c;
        }


        QLineEdit, QTextEdit, QSpinBox {
            background-color: #1e1e1e;
            border: 1px solid #37474f;
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 20px;
        }
        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {
            border: 1px solid #00bcd4;
        }

        QListWidget {
            background-color: #1e1e1e;
            border: 1px solid #37474f;
            border-radius: 4px;
            font-size: 20px;
        }

        QProgressBar {
            background-color: #1e1e1e;
            border: 1px solid #37474f;
            border-radius: 4px;
            text-align: center;
            font-size: 20px;
        }
        QProgressBar::chunk {
            background-color: #00bcd4;
        }
    """)



def main():
    app = QApplication(sys.argv)
    apply_dark_tech_theme(app)  # 设置深色科技主题
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
