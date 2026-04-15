import sys
import os
import subprocess
import shutil
import threading
import importlib
import urllib.request
import zipfile
import tarfile
import tempfile
import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QRadioButton,
    QButtonGroup, QTextEdit, QCheckBox, QGroupBox, QMessageBox,
    QProgressBar, QDialog, QDialogButtonBox, QComboBox, QSpinBox,
    QScrollArea, QFrame
)
from PyQt5.QtCore import QProcess, pyqtSignal, QObject, Qt, QTimer, QThread
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat


class LogSignal(QObject):
    """用于线程安全的日志信号"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    status_signal = pyqtSignal(str)
    install_finished = pyqtSignal(bool, str)
    dialog_log_signal = pyqtSignal(str)
    enable_ok_signal = pyqtSignal()
    download_progress = pyqtSignal(int, int)


class EnvironmentChecker:
    """环境检查工具类"""
    
    @staticmethod
    def check_go():
        """检查Go是否可用"""
        try:
            result = subprocess.run(
                ["go", "version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def get_go_version():
        """获取Go版本"""
        try:
            result = subprocess.run(
                ["go", "version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.stdout.strip()
        except Exception:
            return None
    
    @staticmethod
    def get_go_env():
        """获取Go环境变量"""
        try:
            result = subprocess.run(
                ["go", "env", "-json"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}
    
    @staticmethod
    def check_gcc():
        """检查GCC是否可用（用于CGO）"""
        try:
            result = subprocess.run(
                ["gcc", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def check_upx():
        """检查UPX是否可用（用于压缩）"""
        try:
            result = subprocess.run(
                ["upx", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def check_mingw():
        """检查MinGW是否可用（Windows交叉编译）"""
        try:
            result = subprocess.run(
                ["x86_64-w64-mingw32-gcc", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False


class EnvironmentSetupThread(QThread):
    """环境配置线程"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    download_progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, components, platform):
        super().__init__()
        self.components = components
        self.platform = platform  # 当前操作系统
        self.temp_dir = None
    
    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="go_env_setup_")
            self.log_signal.emit(f"临时目录: {self.temp_dir}")
            
            results = {}
            total_steps = len(self.components)
            current_step = 0
            
            for component in self.components:
                current_step += 1
                progress = int((current_step - 1) / total_steps * 100)
                
                if component == "go":
                    self.progress_signal.emit(progress, f"正在安装Go ({current_step}/{total_steps})...")
                    results["go"] = self.install_go()
                elif component == "upx":
                    self.progress_signal.emit(progress, f"正在安装UPX ({current_step}/{total_steps})...")
                    results["upx"] = self.install_upx()
                elif component == "mingw":
                    self.progress_signal.emit(progress, f"正在安装MinGW ({current_step}/{total_steps})...")
                    results["mingw"] = self.install_mingw()
            
            self.progress_signal.emit(100, "环境配置完成！")
            
            # 生成结果报告
            success_count = sum(1 for v in results.values() if v)
            if success_count == len(results):
                self.finished.emit(True, f"所有组件安装成功！({success_count}/{len(results)})")
            else:
                failed = [k for k, v in results.items() if not v]
                self.finished.emit(False, f"部分组件安装失败: {', '.join(failed)}")
            
        except Exception as e:
            self.log_signal.emit(f"环境配置出错: {str(e)}")
            self.finished.emit(False, str(e))
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
    
    def install_go(self):
        """安装Go"""
        self.log_signal.emit("\n>>> 安装Go...")
        
        # 检查是否已安装
        if EnvironmentChecker.check_go():
            version = EnvironmentChecker.get_go_version()
            self.log_signal.emit(f"✓ Go已安装: {version}")
            return True
        
        # 获取最新Go版本
        go_version = "1.22.5"  # 可以从官网获取最新版本
        
        # 确定下载文件名
        system_map = {
            'win32': 'windows-amd64.zip',
            'darwin': 'darwin-amd64.tar.gz',
            'linux': 'linux-amd64.tar.gz'
        }
        
        platform_key = sys.platform
        if platform_key.startswith('win'):
            platform_key = 'win32'
        elif platform_key.startswith('darwin'):
            platform_key = 'darwin'
        elif platform_key.startswith('linux'):
            platform_key = 'linux'
        
        suffix = system_map.get(platform_key, 'linux-amd64.tar.gz')
        go_filename = f"go{go_version}.{suffix}"
        
        # 镜像源
        mirrors = [
            {
                "name": "华为云镜像",
                "url": f"https://mirrors.huaweicloud.com/golang/go{go_version}.{suffix}"
            },
            {
                "name": "阿里云镜像",
                "url": f"https://mirrors.aliyun.com/golang/go{go_version}.{suffix}"
            },
            {
                "name": "官方源",
                "url": f"https://golang.google.cn/dl/go{go_version}.{suffix}"
            },
            {
                "name": "官方源(国际)",
                "url": f"https://dl.google.com/go/go{go_version}.{suffix}"
            }
        ]
        
        # 下载
        download_path = Path(self.temp_dir) / go_filename
        if not self.download_file(mirrors, download_path, "Go"):
            return False
        
        # 安装
        self.log_signal.emit("\n正在安装Go...")
        install_dir = Path.home() / "go"
        
        try:
            # 删除旧版本
            if install_dir.exists():
                shutil.rmtree(install_dir)
            
            # 解压
            if go_filename.endswith('.zip'):
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(install_dir.parent)
            else:
                with tarfile.open(download_path, 'r:gz') as tf:
                    tf.extractall(install_dir.parent)
            
            self.log_signal.emit(f"✓ Go安装完成: {install_dir}")
            
            # 设置环境变量建议
            self.log_signal.emit("\n请手动设置以下环境变量：")
            self.log_signal.emit(f"GOROOT = {install_dir}")
            self.log_signal.emit(f"PATH = %GOROOT%\\bin")
            self.log_signal.emit(f"GOPATH = %USERPROFILE%\\go")
            self.log_signal.emit(f"GO111MODULE = on")
            self.log_signal.emit(f"GOPROXY = https://goproxy.cn,direct")
            
            return True
            
        except Exception as e:
            self.log_signal.emit(f"✗ Go安装失败: {str(e)}")
            return False
    
    def install_upx(self):
        """安装UPX压缩工具"""
        self.log_signal.emit("\n>>> 安装UPX...")
        
        # 检查是否已安装
        if EnvironmentChecker.check_upx():
            self.log_signal.emit("✓ UPX已安装")
            try:
                result = subprocess.run(["upx", "--version"], capture_output=True, text=True)
                self.log_signal.emit(f"  {result.stdout.split(chr(10))[0]}")
            except:
                pass
            return True
        
        # UPX版本
        upx_version = "4.2.4"
        
        # 确定平台
        platform_map = {
            'win32': 'win64',
            'darwin': 'macos',
            'linux': 'linux'
        }
        
        platform_key = sys.platform
        if platform_key.startswith('win'):
            platform_key = 'win32'
            filename = f"upx-{upx_version}-win64.zip"
        elif platform_key.startswith('darwin'):
            platform_key = 'darwin'
            filename = f"upx-{upx_version}-amd64_macos.tar.xz"
        else:
            platform_key = 'linux'
            filename = f"upx-{upx_version}-amd64_linux.tar.xz"
        
        mirrors = [
            {
                "name": "GitHub",
                "url": f"https://github.com/upx/upx/releases/download/v{upx_version}/{filename}"
            },
            {
                "name": "SourceForge",
                "url": f"https://sourceforge.net/projects/upx/files/upx/{upx_version}/{filename}/download"
            }
        ]
        
        # 下载
        download_path = Path(self.temp_dir) / filename
        if not self.download_file(mirrors, download_path, "UPX"):
            return False
        
        # 安装
        self.log_signal.emit("\n正在安装UPX...")
        install_dir = Path.home() / "upx"
        install_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 解压
            if filename.endswith('.zip'):
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(self.temp_dir)
            else:
                import lzma
                with tarfile.open(download_path, 'r:xz') as tf:
                    tf.extractall(self.temp_dir)
            
            # 复制可执行文件
            extracted_dir = Path(self.temp_dir) / f"upx-{upx_version}-amd64_{platform_map.get(platform_key, 'linux')}"
            if not extracted_dir.exists():
                extracted_dir = Path(self.temp_dir) / f"upx-{upx_version}-win64"
            
            exe_name = "upx.exe" if sys.platform == 'win32' else "upx"
            src_exe = extracted_dir / exe_name
            dest_exe = install_dir / exe_name
            
            if src_exe.exists():
                shutil.copy2(src_exe, dest_exe)
                if sys.platform != 'win32':
                    os.chmod(dest_exe, 0o755)
                
                self.log_signal.emit(f"✓ UPX安装完成: {install_dir}")
                self.log_signal.emit("\n请将以下路径添加到PATH环境变量：")
                self.log_signal.emit(f"{install_dir}")
                return True
            else:
                self.log_signal.emit(f"✗ 未找到UPX可执行文件")
                return False
                
        except Exception as e:
            self.log_signal.emit(f"✗ UPX安装失败: {str(e)}")
            return False
    
    def install_mingw(self):
        """安装MinGW-w64（用于Windows交叉编译）"""
        self.log_signal.emit("\n>>> 安装MinGW-w64...")
        
        if sys.platform != 'win32':
            self.log_signal.emit("MinGW仅适用于Windows系统")
            return True
        
        # 检查是否已安装
        if EnvironmentChecker.check_mingw():
            self.log_signal.emit("✓ MinGW已安装")
            return True
        
        # MinGW下载地址
        mirrors = [
            {
                "name": "GitHub",
                "url": "https://github.com/niXman/mingw-builds-binaries/releases/download/13.2.0-rt_v11-rev1/x86_64-13.2.0-release-win32-seh-ucrt-rt_v11-rev1.7z"
            },
            {
                "name": "SourceForge",
                "url": "https://sourceforge.net/projects/mingw-w64/files/Toolchains%20targetting%20Win64/Personal%20Builds/mingw-builds/13.2.0/threads-win32/seh/x86_64-13.2.0-release-win32-seh-ucrt-rt_v11-rev1.7z/download"
            }
        ]
        
        self.log_signal.emit("\n⚠ MinGW需要手动安装")
        self.log_signal.emit("请从以下地址下载并安装MinGW-w64：")
        self.log_signal.emit("https://www.mingw-w64.org/downloads/")
        self.log_signal.emit("\n或者使用MSYS2：")
        self.log_signal.emit("https://www.msys2.org/")
        self.log_signal.emit("\n安装后请将MinGW的bin目录添加到PATH环境变量")
        
        return False
    
    def download_file(self, mirrors, save_path, name):
        """下载文件，支持多镜像源尝试"""
        for mirror in mirrors:
            self.log_signal.emit(f"\n尝试从{mirror['name']}下载{name}...")
            self.log_signal.emit(f"URL: {mirror['url']}")
            
            try:
                req = urllib.request.Request(
                    mirror['url'],
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                
                with urllib.request.urlopen(req, timeout=60) as response:
                    content_length = response.headers.get('Content-Length')
                    if content_length:
                        total_size = int(content_length)
                        self.log_signal.emit(f"文件大小: {total_size / 1024 / 1024:.2f} MB")
                    else:
                        total_size = 0
                    
                    downloaded = 0
                    block_size = 8192
                    
                    with open(save_path, 'wb') as f:
                        while True:
                            data = response.read(block_size)
                            if not data:
                                break
                            f.write(data)
                            downloaded += len(data)
                            
                            if total_size > 0:
                                percent = int(downloaded * 100 / total_size)
                                if percent % 10 == 0:
                                    self.log_signal.emit(f"下载进度: {percent}%")
                                self.download_progress.emit(downloaded, total_size)
                
                self.log_signal.emit(f"✓ {name}下载完成")
                return True
                
            except Exception as e:
                self.log_signal.emit(f"  下载失败: {str(e)}")
            
            self.log_signal.emit(f"  {mirror['name']}下载失败，尝试下一个源...")
        
        return False


class EnvironmentConfigDialog(QDialog):
    """环境配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("一键配置Go打包环境")
        self.setFixedSize(700, 650)
        self.setModal(True)
        
        self.setup_thread = None
        
        self.init_ui()
        self.check_current_environment()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel("Go项目打包环境一键配置")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel("此工具将帮助您自动下载并配置Go项目打包所需的环境组件")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666666; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # 当前环境状态
        status_group = QGroupBox("当前环境状态")
        status_layout = QVBoxLayout()
        
        self.go_status = QLabel()
        self.gcc_status = QLabel()
        self.upx_status = QLabel()
        self.mingw_status = QLabel()
        
        status_layout.addWidget(self.go_status)
        status_layout.addWidget(self.gcc_status)
        status_layout.addWidget(self.upx_status)
        status_layout.addWidget(self.mingw_status)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # 组件选择
        select_group = QGroupBox("选择要安装的组件")
        select_layout = QVBoxLayout()
        
        self.go_check = QCheckBox("Go语言环境")
        self.go_check.setChecked(True)
        select_layout.addWidget(self.go_check)
        
        self.upx_check = QCheckBox("UPX (可执行文件压缩工具)")
        self.upx_check.setChecked(True)
        select_layout.addWidget(self.upx_check)
        
        self.mingw_check = QCheckBox("MinGW-w64 (Windows交叉编译工具)")
        if sys.platform != 'win32':
            self.mingw_check.setEnabled(False)
            self.mingw_check.setText("MinGW-w64 (仅适用于Windows)")
        select_layout.addWidget(self.mingw_check)
        
        select_group.setLayout(select_layout)
        layout.addWidget(select_group)
        
        # 镜像源选择
        mirror_group = QGroupBox("下载源设置")
        mirror_layout = QVBoxLayout()
        
        self.mirror_combo = QComboBox()
        self.mirror_combo.addItems([
            "优先使用国内镜像，失败后尝试官方源",
            "仅使用国内镜像",
            "仅使用官方源"
        ])
        mirror_layout.addWidget(self.mirror_combo)
        
        mirror_hint = QLabel("提示：国内镜像下载速度更快，推荐使用")
        mirror_hint.setStyleSheet("color: #666666; font-size: 11px;")
        mirror_layout.addWidget(mirror_hint)
        
        # GOPROXY设置
        goproxy_layout = QHBoxLayout()
        goproxy_layout.addWidget(QLabel("GOPROXY:"))
        self.goproxy_combo = QComboBox()
        self.goproxy_combo.addItems([
            "https://goproxy.cn,direct",
            "https://goproxy.io,direct",
            "https://proxy.golang.org,direct",
            "https://mirrors.aliyun.com/goproxy/,direct"
        ])
        self.goproxy_combo.setEditable(True)
        goproxy_layout.addWidget(self.goproxy_combo)
        mirror_layout.addLayout(goproxy_layout)
        
        mirror_group.setLayout(mirror_layout)
        layout.addWidget(mirror_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 日志输出
        log_label = QLabel("详细日志:")
        layout.addWidget(log_label)
        
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
        layout.addWidget(self.log_text)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.install_btn = QPushButton("开始配置")
        self.install_btn.clicked.connect(self.start_setup)
        self.install_btn.setFixedSize(120, 35)
        self.install_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
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
        button_layout.addWidget(self.install_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setFixedSize(120, 35)
        button_layout.addWidget(self.close_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def check_current_environment(self):
        """检查当前环境状态"""
        # Go
        if EnvironmentChecker.check_go():
            version = EnvironmentChecker.get_go_version()
            self.go_status.setText(f"✓ Go - {version}")
            self.go_status.setStyleSheet("color: #4CAF50;")
            self.go_check.setChecked(False)
            
            # 显示Go环境信息
            go_env = EnvironmentChecker.get_go_env()
            if go_env:
                goproxy = go_env.get('GOPROXY', '')
                if goproxy:
                    self.goproxy_combo.setCurrentText(goproxy)
        else:
            self.go_status.setText("✗ Go - 未安装")
            self.go_status.setStyleSheet("color: #F44336;")
        
        # GCC
        if EnvironmentChecker.check_gcc():
            self.gcc_status.setText("✓ GCC - 已安装 (支持CGO)")
            self.gcc_status.setStyleSheet("color: #4CAF50;")
        else:
            self.gcc_status.setText("⚠ GCC - 未安装 (CGO功能受限)")
            self.gcc_status.setStyleSheet("color: #FF9800;")
        
        # UPX
        if EnvironmentChecker.check_upx():
            self.upx_status.setText("✓ UPX - 已安装")
            self.upx_status.setStyleSheet("color: #4CAF50;")
            self.upx_check.setChecked(False)
        else:
            self.upx_status.setText("○ UPX - 未安装 (可选)")
            self.upx_status.setStyleSheet("color: #666666;")
        
        # MinGW
        if sys.platform == 'win32':
            if EnvironmentChecker.check_mingw():
                self.mingw_status.setText("✓ MinGW - 已安装")
                self.mingw_status.setStyleSheet("color: #4CAF50;")
                self.mingw_check.setChecked(False)
            else:
                self.mingw_status.setText("○ MinGW - 未安装 (可选)")
                self.mingw_status.setStyleSheet("color: #666666;")
        else:
            self.mingw_status.setText("- MinGW - 非Windows系统不需要")
            self.mingw_status.setStyleSheet("color: #666666;")
    
    def start_setup(self):
        """开始配置环境"""
        components = []
        
        if self.go_check.isChecked():
            components.append("go")
        if self.upx_check.isChecked():
            components.append("upx")
        if self.mingw_check.isChecked() and self.mingw_check.isEnabled():
            components.append("mingw")
        
        if not components:
            QMessageBox.information(self, "提示", "所有组件已安装，无需配置！")
            return
        
        # 设置GOPROXY
        goproxy = self.goproxy_combo.currentText()
        if goproxy:
            os.environ['GOPROXY'] = goproxy
            self.append_log(f"\n设置GOPROXY={goproxy}")
        
        self.install_btn.setEnabled(False)
        self.log_text.clear()
        
        self.setup_thread = EnvironmentSetupThread(components, sys.platform)
        self.setup_thread.log_signal.connect(self.append_log)
        self.setup_thread.progress_signal.connect(self.update_progress)
        self.setup_thread.download_progress.connect(self.update_download_progress)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()
    
    def append_log(self, text):
        """添加日志"""
        color = QColor("#d4d4d4")
        if text.startswith("✓"):
            color = QColor("#4CAF50")
        elif text.startswith("✗"):
            color = QColor("#F44336")
        elif text.startswith(">>>"):
            color = QColor("#FF9800")
        elif text.startswith("⚠"):
            color = QColor("#FFC107")
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(text + "\n", fmt)
        
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
    
    def update_progress(self, value, status):
        self.progress_bar.setValue(value)
        if status:
            self.status_label.setText(status)
    
    def update_download_progress(self, current, total):
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
            self.status_label.setText(f"下载中... {current / 1024 / 1024:.2f}/{total / 1024 / 1024:.2f} MB")
    
    def on_setup_finished(self, success, message):
        self.install_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "成功", f"环境配置完成！\n\n{message}")
        else:
            QMessageBox.warning(self, "警告", f"环境配置遇到问题：\n{message}")
        
        self.check_current_environment()


class GoPackagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project_dir = ""
        self.icon_path = ""
        self.output_dir = ""
        self.log_signal = LogSignal()
        
        # 连接信号
        self.log_signal.log_signal.connect(self.append_log)
        self.log_signal.progress_signal.connect(self.update_progress)
        self.log_signal.status_signal.connect(self.update_status)
        
        self.progress_dialog = None
        
        self.init_ui()
        
        # 启动时检查环境
        QTimer.singleShot(500, self.check_environment_on_startup)
    
    def check_environment_on_startup(self):
        self.check_environment()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Go项目打包工具 v1.0")
        self.setFixedSize(850, 900)
        
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
        
        self.setup_env_btn = QPushButton("一键配置环境")
        self.setup_env_btn.clicked.connect(self.show_environment_setup)
        self.setup_env_btn.setStyleSheet("""
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
        env_layout.addWidget(self.setup_env_btn)
        
        self.guide_btn = QPushButton("配置指南")
        self.guide_btn.clicked.connect(self.show_environment_guide)
        env_layout.addWidget(self.guide_btn)
        
        main_layout.addLayout(env_layout)
        
        # 分隔线
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #cccccc;")
        main_layout.addWidget(separator)
        
        # 项目设置
        file_group = QGroupBox("项目设置")
        file_layout = QVBoxLayout()
        
        # 项目目录
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("项目目录:"))
        self.project_dir_edit = QLineEdit()
        self.project_dir_edit.setPlaceholderText("选择Go项目根目录(包含go.mod)...")
        project_layout.addWidget(self.project_dir_edit)
        self.project_dir_btn = QPushButton("浏览")
        self.project_dir_btn.clicked.connect(self.select_project_dir)
        project_layout.addWidget(self.project_dir_btn)
        file_layout.addLayout(project_layout)
        
        # 主文件
        main_file_layout = QHBoxLayout()
        main_file_layout.addWidget(QLabel("主文件:"))
        self.main_file_edit = QLineEdit()
        self.main_file_edit.setPlaceholderText("main.go (默认)")
        main_file_layout.addWidget(self.main_file_edit)
        self.detect_main_btn = QPushButton("自动检测")
        self.detect_main_btn.clicked.connect(self.detect_main_file)
        main_file_layout.addWidget(self.detect_main_btn)
        file_layout.addLayout(main_file_layout)
        
        # 输出名称
        output_name_layout = QHBoxLayout()
        output_name_layout.addWidget(QLabel("输出名称:"))
        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("可执行文件名(默认使用目录名)")
        output_name_layout.addWidget(self.output_name_edit)
        file_layout.addLayout(output_name_layout)
        
        # 图标文件
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(QLabel("图标文件:"))
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("选择.ico图标文件(Windows)...")
        icon_layout.addWidget(self.icon_edit)
        self.icon_btn = QPushButton("浏览")
        self.icon_btn.clicked.connect(self.select_icon_file)
        icon_layout.addWidget(self.icon_btn)
        file_layout.addLayout(icon_layout)
        
        # 输出目录
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("默认：项目目录下的dist")
        output_layout.addWidget(self.output_dir_edit)
        self.output_dir_btn = QPushButton("浏览")
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_layout.addWidget(self.output_dir_btn)
        file_layout.addLayout(output_layout)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 编译选项
        build_group = QGroupBox("编译选项")
        build_layout = QVBoxLayout()
        
        # 目标平台
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("目标系统:"))
        self.os_combo = QComboBox()
        self.os_combo.addItems(["当前系统", "windows", "linux", "darwin"])
        self.os_combo.currentTextChanged.connect(self.on_platform_changed)
        platform_layout.addWidget(self.os_combo)
        
        platform_layout.addWidget(QLabel("目标架构:"))
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["amd64", "386", "arm64", "arm"])
        platform_layout.addWidget(self.arch_combo)
        build_layout.addLayout(platform_layout)
        
        # 优化选项
        opt_layout = QHBoxLayout()
        self.ldflags_edit = QLineEdit()
        self.ldflags_edit.setPlaceholderText("-s -w (减小体积)")
        self.ldflags_edit.setText("-s -w")
        opt_layout.addWidget(QLabel("ldflags:"))
        opt_layout.addWidget(self.ldflags_edit)
        build_layout.addLayout(opt_layout)
        
        # 其他选项
        options_layout = QHBoxLayout()
        self.cgo_check = QCheckBox("启用CGO")
        self.cgo_check.setChecked(False)
        options_layout.addWidget(self.cgo_check)
        
        self.race_check = QCheckBox("竞态检测(-race)")
        options_layout.addWidget(self.race_check)
        
        self.trimpath_check = QCheckBox("去除路径信息(-trimpath)")
        self.trimpath_check.setChecked(True)
        options_layout.addWidget(self.trimpath_check)
        
        options_layout.addStretch()
        build_layout.addLayout(options_layout)
        
        build_group.setLayout(build_layout)
        main_layout.addWidget(build_group)
        
        # 打包选项
        pack_group = QGroupBox("打包选项")
        pack_layout = QVBoxLayout()
        
        self.upx_check = QCheckBox("使用UPX压缩可执行文件")
        self.upx_check.setChecked(False)
        pack_layout.addWidget(self.upx_check)
        
        compress_layout = QHBoxLayout()
        compress_layout.addWidget(QLabel("UPX压缩级别:"))
        self.upx_level_combo = QComboBox()
        self.upx_level_combo.addItems(["--best", "-9", "-8", "-7", "-6", "-5", "-4", "-3", "-2", "-1"])
        self.upx_level_combo.setCurrentText("--best")
        compress_layout.addWidget(self.upx_level_combo)
        compress_layout.addStretch()
        pack_layout.addLayout(compress_layout)
        
        self.copy_resources_check = QCheckBox("复制资源文件到输出目录")
        self.copy_resources_check.setChecked(True)
        pack_layout.addWidget(self.copy_resources_check)
        
        pack_group.setLayout(pack_layout)
        main_layout.addWidget(pack_group)
        
        # 附加选项
        option_layout = QHBoxLayout()
        self.clean_check = QCheckBox("打包前清理")
        self.clean_check.setChecked(True)
        option_layout.addWidget(self.clean_check)
        
        self.tidy_check = QCheckBox("执行go mod tidy")
        self.tidy_check.setChecked(True)
        option_layout.addWidget(self.tidy_check)
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
        
        # 日志输出
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
    
    def on_platform_changed(self, text):
        """平台改变时的处理"""
        if text == "windows":
            self.icon_edit.setEnabled(True)
            self.icon_btn.setEnabled(True)
        else:
            self.icon_edit.setEnabled(False)
            self.icon_btn.setEnabled(False)
    
    def show_environment_setup(self):
        """显示环境配置对话框"""
        dialog = EnvironmentConfigDialog(self)
        dialog.exec_()
        self.update_env_status_display()
        self.check_environment()
    
    def update_env_status_display(self):
        """更新环境状态显示"""
        go_ok = EnvironmentChecker.check_go()
        upx_ok = EnvironmentChecker.check_upx()
        
        status_parts = []
        
        if go_ok:
            status_parts.append("✓ Go")
        else:
            status_parts.append("✗ Go")
        
        if upx_ok:
            status_parts.append("✓ UPX")
        else:
            status_parts.append("○ UPX")
        
        self.env_status_label.setText(" | ".join(status_parts))
        
        if go_ok:
            self.env_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.env_status_label.setStyleSheet("color: #F44336; font-weight: bold;")
    
    def check_environment(self):
        """检查环境"""
        self.log_text.clear()
        self.log("=" * 60)
        self.log("开始检查Go环境...")
        
        if EnvironmentChecker.check_go():
            self.log("✓ Go 可用")
            version = EnvironmentChecker.get_go_version()
            if version:
                self.log(f"  {version}")
            
            go_env = EnvironmentChecker.get_go_env()
            if go_env:
                self.log(f"  GOROOT: {go_env.get('GOROOT', '')}")
                self.log(f"  GOPATH: {go_env.get('GOPATH', '')}")
                self.log(f"  GOPROXY: {go_env.get('GOPROXY', '')}")
                self.log(f"  GO111MODULE: {go_env.get('GO111MODULE', '')}")
        else:
            self.log("✗ Go 未安装")
        
        if EnvironmentChecker.check_gcc():
            self.log("✓ GCC 可用 (支持CGO)")
        else:
            self.log("⚠ GCC 未安装 (CGO功能受限)")
        
        if EnvironmentChecker.check_upx():
            self.log("✓ UPX 可用")
        else:
            self.log("○ UPX 未安装 (可选)")
        
        self.update_env_status_display()
        self.log("环境检查完成")
        self.log("=" * 60)
    
    def show_environment_guide(self):
        """显示环境配置指南"""
        guide_text = """
Go项目打包环境配置指南：

方式一：一键自动配置（推荐）
点击「一键配置环境」按钮，程序将自动下载并安装Go和UPX。

方式二：手动配置

1. Go语言环境 (必需)
   - 官方下载: https://golang.google.cn/dl/
   - 国内镜像: https://mirrors.huaweicloud.com/golang/
   - 安装后设置环境变量：
     GOROOT = Go安装目录
     GOPATH = %USERPROFILE%\\go
     GOPROXY = https://goproxy.cn,direct

2. GCC (可选，用于CGO)
   - Windows: 安装MinGW-w64或TDM-GCC
   - Linux: sudo apt install build-essential
   - macOS: xcode-select --install

3. UPX (可选，用于压缩可执行文件)
   - 下载地址: https://github.com/upx/upx/releases
   - 将upx添加到PATH环境变量

4. rsrc (可选，用于Windows图标嵌入)
   - 安装: go install github.com/akavel/rsrc@latest
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("环境配置指南")
        msg_box.setText(guide_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.exec_()
    
    def select_project_dir(self):
        """选择项目目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择Go项目目录")
        if dir_path:
            self.project_dir = dir_path
            self.project_dir_edit.setText(dir_path)
            
            # 自动检测主文件
            project_path = Path(dir_path)
            if (project_path / "main.go").exists():
                self.main_file_edit.setText("main.go")
            else:
                # 查找其他可能的入口文件
                for go_file in project_path.glob("*.go"):
                    try:
                        with open(go_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if 'package main' in content and 'func main()' in content:
                                self.main_file_edit.setText(go_file.name)
                                break
                    except:
                        pass
            
            # 设置默认输出名称
            self.output_name_edit.setText(project_path.name)
    
    def detect_main_file(self):
        """自动检测主文件"""
        if not self.project_dir:
            QMessageBox.warning(self, "警告", "请先选择项目目录！")
            return
        
        project_path = Path(self.project_dir)
        main_files = []
        
        for go_file in project_path.glob("*.go"):
            try:
                with open(go_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'package main' in content and 'func main()' in content:
                        main_files.append(go_file.name)
            except:
                pass
        
        if main_files:
            if len(main_files) == 1:
                self.main_file_edit.setText(main_files[0])
                self.log(f"检测到主文件: {main_files[0]}")
            else:
                self.log(f"检测到多个可能的main文件: {', '.join(main_files)}")
                self.main_file_edit.setText(main_files[0])
        else:
            self.log("未检测到包含main函数的Go文件")
    
    def select_icon_file(self):
        """选择图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标文件", "", "Icon Files (*.ico)"
        )
        if file_path:
            self.icon_path = file_path
            self.icon_edit.setText(file_path)
    
    def select_output_dir(self):
        """选择输出目录"""
        default_dir = self.project_dir if self.project_dir else ""
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", default_dir)
        if dir_path:
            self.output_dir = dir_path
            self.output_dir_edit.setText(dir_path)
    
    def append_log(self, text):
        """添加日志"""
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
        pass
    
    def update_status(self, message):
        self.statusBar().showMessage(message)
    
    def start_packaging(self):
        """开始打包"""
        if not self.project_dir:
            QMessageBox.warning(self, "警告", "请先选择项目目录！")
            return
        
        if not EnvironmentChecker.check_go():
            reply = QMessageBox.question(
                self, "环境检查",
                "Go环境未配置，是否现在配置？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.show_environment_setup()
            return
        
        # 禁用按钮
        self._set_buttons_enabled(False)
        
        # 清空日志
        self.log_text.clear()
        self.log("=" * 60)
        self.log("开始Go项目打包流程...")
        
        thread = threading.Thread(target=self._packaging_thread, daemon=True)
        thread.start()
    
    def _set_buttons_enabled(self, enabled):
        self.pack_btn.setEnabled(enabled)
        self.check_env_btn.setEnabled(enabled)
        self.setup_env_btn.setEnabled(enabled)
        self.guide_btn.setEnabled(enabled)
    
    def _packaging_thread(self):
        """后台线程执行打包"""
        try:
            project_path = Path(self.project_dir)
            
            # 确定输出目录
            if self.output_dir and os.path.isdir(self.output_dir):
                output_dir = Path(self.output_dir)
            else:
                output_dir = project_path / "dist"
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定输出名称
            output_name = self.output_name_edit.text().strip()
            if not output_name:
                output_name = project_path.name
            
            # 确定目标平台
            target_os = self.os_combo.currentText()
            if target_os == "当前系统":
                target_os = ""
            
            target_arch = self.arch_combo.currentText()
            
            # 设置环境变量
            env = os.environ.copy()
            if target_os:
                env['GOOS'] = target_os
                env['GOARCH'] = target_arch
                self.log(f"目标平台: {target_os}/{target_arch}")
            
            if self.cgo_check.isChecked():
                env['CGO_ENABLED'] = '1'
                self.log("启用CGO")
            else:
                env['CGO_ENABLED'] = '0'
            
            # 输出文件名
            exe_suffix = ".exe" if target_os == "windows" or (not target_os and sys.platform == 'win32') else ""
            output_file = output_dir / f"{output_name}{exe_suffix}"
            
            self.log(f"项目目录: {project_path}")
            self.log(f"输出文件: {output_file}")
            
            # 执行go mod tidy
            if self.tidy_check.isChecked() and (project_path / "go.mod").exists():
                self.log("\n>>> 执行 go mod tidy...")
                cmd = ["go", "mod", "tidy"]
                self._run_command(cmd, project_path, env)
            
            # 处理Windows图标
            if target_os == "windows" and self.icon_path and os.path.exists(self.icon_path):
                self.log("\n>>> 生成图标资源...")
                self._generate_windows_resource(project_path)
            
            # 构建命令
            self.log("\n>>> 开始编译...")
            cmd = ["go", "build"]
            
            # 添加ldflags
            ldflags = self.ldflags_edit.text().strip()
            if ldflags:
                cmd.extend(["-ldflags", ldflags])
                self.log(f"ldflags: {ldflags}")
            
            # 添加其他选项
            if self.race_check.isChecked():
                cmd.append("-race")
                self.log("启用竞态检测")
            
            if self.trimpath_check.isChecked():
                cmd.append("-trimpath")
                self.log("启用路径去除")
            
            # 输出文件
            cmd.extend(["-o", str(output_file)])
            
            # 主文件
            main_file = self.main_file_edit.text().strip()
            if main_file:
                cmd.append(str(project_path / main_file))
            else:
                cmd.append(".")
            
            # 执行编译
            self._run_command(cmd, project_path, env)
            
            if output_file.exists():
                size_mb = output_file.stat().st_size / 1024 / 1024
                self.log(f"\n✓ 编译完成！文件大小: {size_mb:.2f} MB")
                
                # UPX压缩
                if self.upx_check.isChecked() and EnvironmentChecker.check_upx():
                    self.log("\n>>> 使用UPX压缩...")
                    upx_level = self.upx_level_combo.currentText()
                    upx_cmd = ["upx", upx_level, str(output_file)]
                    self._run_command(upx_cmd, output_dir)
                    
                    if output_file.exists():
                        new_size = output_file.stat().st_size / 1024 / 1024
                        self.log(f"压缩后大小: {new_size:.2f} MB (压缩率: {(1 - new_size/size_mb)*100:.1f}%)")
                
                # 复制资源文件
                if self.copy_resources_check.isChecked():
                    self._copy_resources(project_path, output_dir)
                
                self.log("=" * 60)
                self.log("✓ 打包完成！")
                self.log(f"输出文件: {output_file}")
                self.log_signal.status_signal.emit("打包完成")
                
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self, "成功",
                    f"打包完成！\n输出文件: {output_file}"
                ))
            else:
                raise RuntimeError("编译失败，未生成输出文件")
            
        except Exception as e:
            self.log(f"✗ 打包失败: {str(e)}")
            self.log_signal.status_signal.emit("打包失败")
            
            QTimer.singleShot(0, lambda err=str(e): QMessageBox.critical(
                self, "错误", f"打包失败：{err}"
            ))
        
        finally:
            QTimer.singleShot(0, lambda: self._set_buttons_enabled(True))
    
    def _generate_windows_resource(self, project_path):
        """生成Windows资源文件"""
        try:
            # 检查rsrc是否安装
            result = subprocess.run(["rsrc", "-help"], capture_output=True)
            if result.returncode != 0:
                self.log("正在安装rsrc...")
                subprocess.run(["go", "install", "github.com/akavel/rsrc@latest"], cwd=str(project_path))
            
            # 生成syso文件
            manifest = project_path / "app.manifest"
            if not manifest.exists():
                manifest_content = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
    <assemblyIdentity version="1.0.0.0" processorArchitecture="*" name="App" type="win32"/>
    <dependency>
        <dependentAssembly>
            <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
        </dependentAssembly>
    </dependency>
</assembly>'''
                with open(manifest, 'w') as f:
                    f.write(manifest_content)
            
            cmd = ["rsrc", "-ico", self.icon_path, "-o", str(project_path / "rsrc.syso")]
            subprocess.run(cmd, cwd=str(project_path))
            self.log("✓ 图标资源生成完成")
            
        except Exception as e:
            self.log(f"⚠ 图标资源生成失败: {str(e)}")
    
    def _copy_resources(self, project_path, output_dir):
        """复制资源文件"""
        self.log("\n>>> 复制资源文件...")
        
        resource_dirs = ["assets", "resources", "static", "config", "conf"]
        
        for dir_name in resource_dirs:
            src_dir = project_path / dir_name
            if src_dir.exists() and src_dir.is_dir():
                dest_dir = output_dir / dir_name
                if dest_dir.exists():
                    shutil.rmtree(dest_dir)
                shutil.copytree(src_dir, dest_dir)
                self.log(f"  复制目录: {dir_name}")
        
        # 复制配置文件
        for ext in [".yaml", ".yml", ".json", ".toml", ".ini", ".conf"]:
            for config_file in project_path.glob(f"*{ext}"):
                dest_file = output_dir / config_file.name
                shutil.copy2(config_file, dest_file)
                self.log(f"  复制文件: {config_file.name}")
    
    def _run_command(self, cmd, work_dir, env=None):
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
            env=env,
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


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = GoPackagerGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
