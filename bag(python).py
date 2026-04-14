import sys
import os
import subprocess
import shutil
import threading
import importlib
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QRadioButton,
    QButtonGroup, QTextEdit, QCheckBox, QGroupBox, QMessageBox,
    QProgressBar, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import QProcess, pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat


class LogSignal(QObject):
    """用于线程安全的日志信号"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)  # value, status
    status_signal = pyqtSignal(str)
    install_finished = pyqtSignal(bool, str)
    dialog_log_signal = pyqtSignal(str)
    enable_ok_signal = pyqtSignal()


class EnvironmentChecker:
    """环境检查工具类"""
    
    @staticmethod
    def check_pip():
        """检查pip是否可用"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def check_module(module_name):
        """检查Python模块是否已安装"""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def get_missing_packages():
        """获取缺失的依赖包列表"""
        required = {
            'PyInstaller': 'pyinstaller',
            'pyarmor': 'pyarmor'
        }
        missing = []
        for module, package in required.items():
            if not EnvironmentChecker.check_module(module):
                missing.append(package)
        return missing


class InstallProgressDialog(QDialog):
    """安装进度对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("安装环境依赖")
        self.setFixedSize(600, 400)
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        title = QLabel("正在安装所需环境...")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("准备中...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.log_text)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def append_log(self, text):
        if self.isVisible():
            self.log_text.append(text)
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)
    
    def update_progress(self, value, status=""):
        if self.isVisible():
            self.progress_bar.setValue(value)
            if status:
                self.status_label.setText(status)
    
    def enable_ok_button(self):
        if self.isVisible():
            self.ok_button.setEnabled(True)


class PackagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.py_file_path = ""
        self.icon_path = ""
        self.output_dir = ""  # 输出目录，空字符串表示默认
        self.log_signal = LogSignal()
        
        # 连接信号
        self.log_signal.log_signal.connect(self.append_log)
        self.log_signal.progress_signal.connect(self.update_progress)
        self.log_signal.status_signal.connect(self.update_status)
        self.log_signal.install_finished.connect(self.on_install_finished)
        self.log_signal.dialog_log_signal.connect(self._safe_dialog_log)
        self.log_signal.enable_ok_signal.connect(self._safe_enable_ok)
        
        self.progress_dialog = None
        
        self.init_ui()
        
        # 启动时检查环境
        QTimer.singleShot(500, self.check_environment_on_startup)
    
    def _safe_dialog_log(self, text):
        """安全地更新进度对话框日志"""
        if self.progress_dialog and self.progress_dialog.isVisible():
            self.progress_dialog.append_log(text)
    
    def _safe_enable_ok(self):
        """安全地启用确定按钮"""
        if self.progress_dialog and self.progress_dialog.isVisible():
            self.progress_dialog.enable_ok_button()
    
    def check_environment_on_startup(self):
        """启动时检查环境"""
        self.check_environment()
        missing = EnvironmentChecker.get_missing_packages()
        if missing:
            QTimer.singleShot(500, lambda: self.prompt_install_environment(missing))
    
    def prompt_install_environment(self, missing_packages):
        """提示安装环境"""
        msg = "检测到以下依赖包未安装：\n\n"
        msg += "\n".join([f"• {pkg}" for pkg in missing_packages])
        msg += "\n\n是否立即安装？"
        
        reply = QMessageBox.question(
            self, "环境检查", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.install_environment()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Python一键打包工具 v2.1")
        self.setFixedSize(750, 720)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        
        # 环境状态栏
        env_layout = QHBoxLayout()
        env_layout.addWidget(QLabel("环境状态:"))
        
        self.env_status_label = QLabel()
        self.update_env_status_display()
        env_layout.addWidget(self.env_status_label)
        env_layout.addStretch()
        
        self.check_env_btn = QPushButton("检查环境")
        self.check_env_btn.clicked.connect(self.check_environment)
        env_layout.addWidget(self.check_env_btn)
        
        self.install_env_btn = QPushButton("一键安装/更新环境")
        self.install_env_btn.clicked.connect(self.install_environment)
        self.install_env_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        env_layout.addWidget(self.install_env_btn)
        
        main_layout.addLayout(env_layout)
        
        # 分隔线
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #cccccc;")
        main_layout.addWidget(separator)
        
        # 文件选择区域
        file_group = QGroupBox("文件设置")
        file_layout = QVBoxLayout()
        
        # 主py文件选择
        py_layout = QHBoxLayout()
        py_layout.addWidget(QLabel("主Python文件:"))
        self.py_file_edit = QLineEdit()
        self.py_file_edit.setPlaceholderText("选择要打包的.py文件...")
        py_layout.addWidget(self.py_file_edit)
        self.py_file_btn = QPushButton("浏览")
        self.py_file_btn.clicked.connect(self.select_py_file)
        py_layout.addWidget(self.py_file_btn)
        file_layout.addLayout(py_layout)
        
        # 图标文件选择
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(QLabel("图标文件:"))
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("选择.ico图标文件（可选）...")
        icon_layout.addWidget(self.icon_edit)
        self.icon_btn = QPushButton("浏览")
        self.icon_btn.clicked.connect(self.select_icon_file)
        icon_layout.addWidget(self.icon_btn)
        file_layout.addLayout(icon_layout)
        
        # 输出目录选择（新增）
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("默认：与源代码同目录")
        output_layout.addWidget(self.output_dir_edit)
        self.output_dir_btn = QPushButton("浏览")
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_layout.addWidget(self.output_dir_btn)
        file_layout.addLayout(output_layout)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 打包模式选择
        mode_group = QGroupBox("打包模式")
        mode_layout = QVBoxLayout()
        
        self.normal_radio = QRadioButton("普通打包 (PyInstaller)")
        self.normal_radio.setChecked(True)
        mode_layout.addWidget(self.normal_radio)
        
        self.encrypt_radio = QRadioButton("加密打包 (PyArmor + PyInstaller)")
        mode_layout.addWidget(self.encrypt_radio)
        
        mode_hint = QLabel("提示：加密打包需要先安装PyArmor，可点击上方「一键安装环境」按钮安装")
        mode_hint.setStyleSheet("color: #666666; font-size: 11px;")
        mode_hint.setWordWrap(True)
        mode_layout.addWidget(mode_hint)
        
        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)
        
        # 附加选项
        option_layout = QHBoxLayout()
        self.clean_check = QCheckBox("自动清理冗余文件，仅保留最终EXE")
        self.clean_check.setChecked(True)
        option_layout.addWidget(self.clean_check)
        option_layout.addStretch()
        main_layout.addLayout(option_layout)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.pack_btn = QPushButton("开始打包")
        self.pack_btn.clicked.connect(self.start_packaging)
        self.pack_btn.setFixedSize(150, 40)
        self.pack_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        btn_layout.addWidget(self.pack_btn)
        btn_layout.addStretch()
        
        main_layout.addLayout(btn_layout)
        
        # 日志输出区域
        log_label = QLabel("实时日志输出:")
        main_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333333;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.log_text)
        
        self.statusBar().showMessage("就绪")
    
    def update_env_status_display(self):
        """更新环境状态显示"""
        missing = EnvironmentChecker.get_missing_packages()
        
        if not missing:
            self.env_status_label.setText("✓ 环境完整")
            self.env_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.env_status_label.setText(f"⚠ 缺少 {len(missing)} 个依赖")
            self.env_status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
    
    def check_environment(self):
        """检查环境"""
        self.log_text.clear()
        self.log("=" * 50)
        self.log("开始检查环境...")
        
        if EnvironmentChecker.check_pip():
            self.log("✓ pip 可用")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    capture_output=True,
                    text=True
                )
                self.log(f"  {result.stdout.strip()}")
            except Exception:
                pass
        else:
            self.log("✗ pip 不可用，请确保Python安装正确")
        
        modules = {
            'PyInstaller': 'pyinstaller',
            'pyarmor': 'pyarmor'
        }
        
        for module, package in modules.items():
            if EnvironmentChecker.check_module(module):
                self.log(f"✓ {package} 已安装")
                try:
                    mod = importlib.import_module(module)
                    if hasattr(mod, '__version__'):
                        self.log(f"  版本: {mod.__version__}")
                except Exception:
                    pass
            else:
                self.log(f"✗ {package} 未安装")
        
        self.update_env_status_display()
        self.log("环境检查完成")
        self.log("=" * 50)
        
        missing = EnvironmentChecker.get_missing_packages()
        if missing:
            self.log("提示：可以点击「一键安装环境」按钮安装缺失的依赖")
    
    def select_output_dir(self):
        """选择输出目录"""
        # 默认打开源代码所在目录
        default_dir = ""
        if self.py_file_path:
            default_dir = str(Path(self.py_file_path).parent)
        
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择EXE输出目录", default_dir
        )
        if dir_path:
            self.output_dir = dir_path
            self.output_dir_edit.setText(dir_path)
    
    def install_environment(self):
        """一键安装环境依赖"""
        self.install_env_btn.setEnabled(False)
        self.check_env_btn.setEnabled(False)
        
        self.progress_dialog = InstallProgressDialog(self)
        
        thread = threading.Thread(target=self._install_environment_thread, daemon=True)
        thread.start()
        
        self.progress_dialog.exec_()
        
        self.install_env_btn.setEnabled(True)
        self.check_env_btn.setEnabled(True)
        self.update_env_status_display()
    
    def _install_environment_thread(self):
        """后台线程执行环境安装"""
        try:
            # 升级pip
            self.log_signal.progress_signal.emit(10, "正在升级pip...")
            self.log_signal.log_signal.emit("\n>>> 升级pip...")
            
            success, _ = self._run_pip_install(["--upgrade", "pip"])
            if success:
                self.log_signal.log_signal.emit("✓ pip升级成功")
            else:
                self.log_signal.log_signal.emit("⚠ pip升级失败，继续安装其他包...")
            
            # 安装PyInstaller
            self.log_signal.progress_signal.emit(30, "正在安装PyInstaller...")
            self.log_signal.log_signal.emit("\n>>> 安装PyInstaller...")
            
            success, msg = self._run_pip_install(["pyinstaller"])
            if success:
                self.log_signal.log_signal.emit("✓ PyInstaller 安装成功")
            else:
                self.log_signal.log_signal.emit(f"✗ PyInstaller 安装失败: {msg}")
            
            # 安装PyArmor
            self.log_signal.progress_signal.emit(70, "正在安装PyArmor...")
            self.log_signal.log_signal.emit("\n>>> 安装PyArmor...")
            
            success, msg = self._run_pip_install(["pyarmor"])
            if success:
                self.log_signal.log_signal.emit("✓ PyArmor 安装成功")
            else:
                self.log_signal.log_signal.emit(f"✗ PyArmor 安装失败: {msg}")
            
            # 验证安装
            self.log_signal.progress_signal.emit(90, "验证安装...")
            self.log_signal.log_signal.emit("\n>>> 验证安装...")
            
            missing = EnvironmentChecker.get_missing_packages()
            if missing:
                self.log_signal.log_signal.emit(f"⚠ 以下包未成功安装: {', '.join(missing)}")
                self.log_signal.install_finished.emit(False, f"部分包安装失败: {', '.join(missing)}")
            else:
                self.log_signal.log_signal.emit("✓ 所有依赖安装成功！")
                self.log_signal.install_finished.emit(True, "所有依赖安装成功")
            
            self.log_signal.progress_signal.emit(100, "安装完成")
            self.log_signal.enable_ok_signal.emit()
            
        except Exception as e:
            self.log_signal.log_signal.emit(f"\n✗ 安装过程出错: {str(e)}")
            self.log_signal.progress_signal.emit(0, "安装失败")
            self.log_signal.install_finished.emit(False, str(e))
            self.log_signal.enable_ok_signal.emit()
    
    def _run_pip_install(self, packages):
        """执行pip安装命令，自动尝试多个镜像源"""
        # 镜像源列表，包含trusted-host避免SSL问题
        mirror_sources = [
            {
                "args": ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                "hosts": ["--trusted-host", "pypi.tuna.tsinghua.edu.cn"],
                "name": "清华源"
            },
            {
                "args": ["-i", "https://mirrors.aliyun.com/pypi/simple/"],
                "hosts": ["--trusted-host", "mirrors.aliyun.com"],
                "name": "阿里云源"
            },
            {
                "args": ["-i", "https://pypi.douban.com/simple/"],
                "hosts": ["--trusted-host", "pypi.douban.com"],
                "name": "豆瓣源"
            },
            {
                "args": [],
                "hosts": [],
                "name": "默认源"
            }
        ]
        
        for source in mirror_sources:
            cmd = [sys.executable, "-m", "pip", "install"]
            cmd.extend(packages)
            if source["args"]:
                cmd.extend(source["args"])
            if source["hosts"]:
                cmd.extend(source["hosts"])
            
            self.log_signal.log_signal.emit(f"尝试从{source['name']}安装...")
            
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # 关键修复：合并stderr避免死锁
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                
                # 实时读取输出
                while True:
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        continue
                    line = line.strip()
                    if line:
                        self.log_signal.log_signal.emit(f"  {line}")
                        self.log_signal.dialog_log_signal.emit(line)
                
                if process.returncode == 0:
                    return True, "安装成功"
                else:
                    self.log_signal.log_signal.emit(f"  {source['name']}安装失败，尝试下一个...")
                    
            except subprocess.TimeoutExpired:
                self.log_signal.log_signal.emit(f"  {source['name']}超时，尝试下一个...")
                process.kill()
            except Exception as e:
                self.log_signal.log_signal.emit(f"  {source['name']}出错: {str(e)}，尝试下一个...")
        
        return False, "所有镜像源都安装失败"
    
    def on_install_finished(self, success, message):
        """安装完成回调"""
        if success:
            QMessageBox.information(self, "成功", f"环境安装完成！\n{message}")
        else:
            QMessageBox.warning(self, "警告", f"环境安装遇到问题：\n{message}\n\n请检查网络连接后重试。")
    
    def select_py_file(self):
        """选择Python主文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Python文件", "", "Python Files (*.py)"
        )
        if file_path:
            self.py_file_path = file_path
            self.py_file_edit.setText(file_path)
    
    def select_icon_file(self):
        """选择图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标文件", "", "Icon Files (*.ico)"
        )
        if file_path:
            self.icon_path = file_path
            self.icon_edit.setText(file_path)
    
    def append_log(self, text):
        """添加日志到输出框"""
        color_map = {
            "✓": QColor("#4CAF50"),
            "✗": QColor("#F44336"),
            ">>>": QColor("#FF9800"),
            "=": QColor("#2196F3"),
            "⚠": QColor("#FFC107"),
        }
        
        color = QColor("#d4d4d4")
        for prefix, c in color_map.items():
            if text.startswith(prefix):
                color = c
                break
        
        self._append_colored_log(text, color)
    
    def _append_colored_log(self, text, color):
        """添加带颜色的日志"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(text + "\n", fmt)
        
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
    
    def log(self, message):
        """发送日志信号"""
        self.log_signal.log_signal.emit(message)
    
    def update_progress(self, value, status=""):
        """更新进度"""
        if self.progress_dialog:
            self.progress_dialog.update_progress(value, status)
    
    def update_status(self, message):
        """更新状态栏"""
        self.statusBar().showMessage(message)
    
    def start_packaging(self):
        """开始打包流程"""
        # 验证输入
        if not self.py_file_path:
            QMessageBox.warning(self, "警告", "请先选择要打包的Python文件！")
            return
        
        if not os.path.exists(self.py_file_path):
            QMessageBox.warning(self, "警告", "选择的Python文件不存在！")
            return
        
        if self.icon_path and not os.path.exists(self.icon_path):
            QMessageBox.warning(self, "警告", "选择的图标文件不存在！")
            return
        
        # 验证输出目录（如果指定了）
        output_dir = self.output_dir if self.output_dir else ""
        if output_dir and not os.path.isdir(output_dir):
            QMessageBox.warning(self, "警告", "指定的输出目录不存在！")
            return
        
        # 检查必需的环境
        missing = EnvironmentChecker.get_missing_packages()
        if 'pyinstaller' in missing:
            reply = QMessageBox.question(
                self, "环境检查",
                "PyInstaller未安装，是否立即安装？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.install_environment()
            return
        
        if self.encrypt_radio.isChecked() and 'pyarmor' in missing:
            reply = QMessageBox.question(
                self, "环境检查",
                "PyArmor未安装，加密打包需要PyArmor。是否立即安装？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.install_environment()
            return
        
        # 禁用按钮防止重复操作
        self._set_buttons_enabled(False)
        
        # 清空日志
        self.log_text.clear()
        self.log("=" * 50)
        self.log("开始打包流程...")
        
        thread = threading.Thread(target=self._packaging_thread, daemon=True)
        thread.start()
    
    def _set_buttons_enabled(self, enabled):
        """设置按钮状态"""
        self.pack_btn.setEnabled(enabled)
        self.install_env_btn.setEnabled(enabled)
        self.check_env_btn.setEnabled(enabled)
    
    def _packaging_thread(self):
        """后台线程执行打包"""
        try:
            py_file = Path(self.py_file_path)
            source_dir = py_file.parent
            py_name = py_file.stem
            
            # 确定输出目录：如果用户指定了就用指定的，否则用源代码目录
            if self.output_dir and os.path.isdir(self.output_dir):
                output_dir = Path(self.output_dir)
            else:
                output_dir = source_dir
            
            self.log(f"源代码目录: {source_dir}")
            self.log(f"主文件: {py_file.name}")
            self.log(f"输出目录: {output_dir}")
            
            if self.encrypt_radio.isChecked():
                self.log("使用加密打包模式...")
                self.log_signal.status_signal.emit("正在加密打包...")
                
                # 步骤1: PyArmor加密
                self.log("步骤1: PyArmor加密...")
                encrypt_output = source_dir / "dist_encrypted"
                
                # 清理旧的加密目录
                if encrypt_output.exists():
                    shutil.rmtree(encrypt_output)
                
                encrypt_cmd = [
                    sys.executable, "-m", "pyarmor", "gen",
                    "--output", str(encrypt_output),
                    str(py_file)
                ]
                
                self._run_command(encrypt_cmd, source_dir)
                
                # 步骤2: 查找加密后的文件
                encrypted_py = None
                if encrypt_output.exists():
                    # 尝试原文件名
                    potential_file = encrypt_output / py_file.name
                    if potential_file.exists():
                        encrypted_py = potential_file
                    else:
                        # 查找目录中的任何.py文件
                        py_files = list(encrypt_output.glob("*.py"))
                        if py_files:
                            encrypted_py = py_files[0]
                            self.log(f"找到加密文件: {encrypted_py.name}")
                        else:
                            # 可能在子目录中
                            for sub_py in encrypt_output.rglob("*.py"):
                                encrypted_py = sub_py
                                self.log(f"找到加密文件: {encrypted_py.name}")
                                break
                
                if not encrypted_py or not encrypted_py.exists():
                    raise RuntimeError("未找到PyArmor加密后的文件，请检查加密是否成功")
                
                # 步骤3: PyInstaller打包
                self.log("步骤2: PyInstaller打包加密文件...")
                pack_cmd = self._build_pyinstaller_cmd(encrypted_py, output_dir, source_dir)
                self._run_command(pack_cmd, source_dir)
                
            else:
                self.log("使用普通打包模式...")
                self.log_signal.status_signal.emit("正在打包...")
                
                pack_cmd = self._build_pyinstaller_cmd(py_file, output_dir, source_dir)
                self._run_command(pack_cmd, source_dir)
            
            # 清理临时文件
            if self.clean_check.isChecked():
                self.log("正在清理临时文件...")
                self._clean_temp_files(source_dir, output_dir)
            
            self.log("=" * 50)
            self.log("✓ 打包完成！")
            final_output = output_dir / 'dist'
            self.log(f"输出目录: {final_output}")
            self.log_signal.status_signal.emit("打包完成")
            
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "成功",
                f"打包完成！\n输出文件位于: {final_output}"
            ))
            
        except Exception as e:
            self.log(f"✗ 打包失败: {str(e)}")
            self.log_signal.status_signal.emit("打包失败")
            
            QTimer.singleShot(0, lambda err=str(e): QMessageBox.critical(
                self, "错误", f"打包失败：{err}"
            ))
        
        finally:
            # 线程安全地恢复按钮
            QTimer.singleShot(0, lambda: self._set_buttons_enabled(True))
    
    def _build_pyinstaller_cmd(self, py_file, output_dir, work_dir):
        """构建PyInstaller命令"""
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--noconsole",
            "--clean",
            f"--name={py_file.stem}",
            f"--distpath={output_dir / 'dist'}",
            f"--workpath={work_dir / 'build'}",
            f"--specpath={work_dir}",
        ]
        
        if self.icon_path:
            cmd.append(f"--icon={self.icon_path}")
        
        cmd.append(str(py_file))
        
        return cmd
    
    def _run_command(self, cmd, work_dir):
        """执行命令并实时输出日志"""
        self.log(f"执行命令: {' '.join(str(c) for c in cmd)}")
        
        process = subprocess.Popen(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            line = line.strip()
            if line:
                self.log(line)
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
    
    def _clean_temp_files(self, source_dir, output_dir):
        """清理临时文件"""
        # 在源目录清理
        temp_dirs = ['build', '__pycache__']
        
        for dir_name in temp_dirs:
            dir_path = source_dir / dir_name
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    self.log(f"已删除目录: {dir_name}")
                except Exception as e:
                    self.log(f"删除目录失败 {dir_name}: {str(e)}")
        
        # 清理spec文件
        for spec_file in source_dir.glob("*.spec"):
            try:
                spec_file.unlink()
                self.log(f"已删除文件: {spec_file.name}")
            except Exception as e:
                self.log(f"删除文件失败 {spec_file.name}: {str(e)}")
        
        # 清理加密临时目录
        encrypted_dir = source_dir / "dist_encrypted"
        if encrypted_dir.exists():
            try:
                shutil.rmtree(encrypted_dir)
                self.log("已清理加密临时目录")
            except Exception as e:
                self.log(f"清理加密目录失败: {str(e)}")
        
        self.log("临时文件清理完成")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = PackagerGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
