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
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QRadioButton,
    QButtonGroup, QTextEdit, QCheckBox, QGroupBox, QMessageBox,
    QProgressBar, QDialog, QDialogButtonBox, QComboBox, QTabWidget,
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
    download_progress = pyqtSignal(int, int)  # current, total


class EnvironmentChecker:
    """环境检查工具类"""
    
    @staticmethod
    def check_java():
        """检查Java是否可用"""
        try:
            result = subprocess.run(
                ["java", "-version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0 or "version" in result.stderr.lower()
        except Exception:
            return False
    
    @staticmethod
    def get_java_version():
        """获取Java版本"""
        try:
            result = subprocess.run(
                ["java", "-version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            output = result.stderr if result.stderr else result.stdout
            lines = output.split('\n')
            if lines:
                return lines[0].strip()
        except Exception:
            return None
        return None
    
    @staticmethod
    def check_maven():
        """检查Maven是否可用"""
        try:
            result = subprocess.run(
                ["mvn", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def get_maven_version():
        """获取Maven版本"""
        try:
            result = subprocess.run(
                ["mvn", "--version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            lines = result.stdout.split('\n')
            if lines:
                return lines[0].strip()
        except Exception:
            return None
        return None
    
    @staticmethod
    def check_gradle():
        """检查Gradle是否可用"""
        try:
            if sys.platform == 'win32':
                cmd = ["gradle.bat", "--version"]
            else:
                cmd = ["gradle", "--version"]
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def get_gradle_version():
        """获取Gradle版本"""
        try:
            cmd = ["gradle.bat", "--version"] if sys.platform == 'win32' else ["gradle", "--version"]
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=10
            )
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Gradle' in line:
                    return line.strip()
        except Exception:
            return None
        return None
    
    @staticmethod
    def check_launch4j():
        """检查Launch4j是否可用"""
        launch4j_path = os.environ.get('LAUNCH4J_HOME', '')
        if launch4j_path:
            exe_name = "launch4jc.exe" if sys.platform == 'win32' else "launch4jc"
            exe_path = Path(launch4j_path) / exe_name
            return exe_path.exists()
        return False


class EnvironmentSetupThread(QThread):
    """环境配置线程"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    download_progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, components):
        super().__init__()
        self.components = components  # 要安装的组件列表
        self.temp_dir = None
    
    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="java_env_setup_")
            self.log_signal.emit(f"临时目录: {self.temp_dir}")
            
            results = {}
            total_steps = len(self.components)
            current_step = 0
            
            for component in self.components:
                current_step += 1
                progress = int((current_step - 1) / total_steps * 100)
                
                if component == "maven":
                    self.progress_signal.emit(progress, f"正在安装Maven ({current_step}/{total_steps})...")
                    results["maven"] = self.install_maven()
                elif component == "gradle":
                    self.progress_signal.emit(progress, f"正在安装Gradle ({current_step}/{total_steps})...")
                    results["gradle"] = self.install_gradle()
                elif component == "launch4j":
                    self.progress_signal.emit(progress, f"正在安装Launch4j ({current_step}/{total_steps})...")
                    results["launch4j"] = self.install_launch4j()
                elif component == "java":
                    self.progress_signal.emit(progress, f"正在检查Java环境 ({current_step}/{total_steps})...")
                    results["java"] = self.check_java_environment()
            
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
            # 清理临时目录
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
    
    def check_java_environment(self):
        """检查Java环境并提供下载指引"""
        self.log_signal.emit("\n>>> 检查Java环境...")
        
        if EnvironmentChecker.check_java():
            version = EnvironmentChecker.get_java_version()
            self.log_signal.emit(f"✓ Java已安装: {version}")
            
            # 检查JAVA_HOME
            java_home = os.environ.get('JAVA_HOME', '')
            if java_home:
                self.log_signal.emit(f"✓ JAVA_HOME: {java_home}")
            else:
                self.log_signal.emit("⚠ JAVA_HOME环境变量未设置")
                self.log_signal.emit("  建议手动设置JAVA_HOME环境变量")
            
            return True
        else:
            self.log_signal.emit("✗ Java未安装")
            self.log_signal.emit("\n请手动安装Java JDK 8或更高版本：")
            self.log_signal.emit("官方下载: https://www.oracle.com/java/technologies/downloads/")
            self.log_signal.emit("国内镜像: https://mirrors.huaweicloud.com/java/jdk/")
            self.log_signal.emit("安装后请设置JAVA_HOME环境变量")
            return False
    
    def install_maven(self):
        """安装Maven"""
        self.log_signal.emit("\n>>> 安装Maven...")
        
        # 检查是否已安装
        if EnvironmentChecker.check_maven():
            version = EnvironmentChecker.get_maven_version()
            self.log_signal.emit(f"✓ Maven已安装: {version}")
            return True
        
        # Maven下载地址（优先国内镜像）
        maven_version = "3.9.6"
        maven_filename = f"apache-maven-{maven_version}-bin.zip"
        
        mirrors = [
            {
                "name": "华为云镜像",
                "url": f"https://mirrors.huaweicloud.com/apache/maven/maven-3/{maven_version}/binaries/{maven_filename}"
            },
            {
                "name": "阿里云镜像",
                "url": f"https://mirrors.aliyun.com/apache/maven/maven-3/{maven_version}/binaries/{maven_filename}"
            },
            {
                "name": "清华镜像",
                "url": f"https://mirrors.tuna.tsinghua.edu.cn/apache/maven/maven-3/{maven_version}/binaries/{maven_filename}"
            },
            {
                "name": "官方源",
                "url": f"https://archive.apache.org/dist/maven/maven-3/{maven_version}/binaries/{maven_filename}"
            }
        ]
        
        # 尝试下载
        download_path = Path(self.temp_dir) / maven_filename
        if not self.download_file(mirrors, download_path, "Maven"):
            return False
        
        # 解压到用户目录
        self.log_signal.emit("\n正在解压Maven...")
        install_dir = Path.home() / "apache-maven" / f"apache-maven-{maven_version}"
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(download_path, 'r') as zf:
                zf.extractall(install_dir.parent)
            
            self.log_signal.emit(f"✓ Maven解压完成: {install_dir}")
            
            # 设置环境变量建议
            self.log_signal.emit("\n请手动设置以下环境变量：")
            self.log_signal.emit(f"MAVEN_HOME = {install_dir}")
            self.log_signal.emit(f"PATH = %MAVEN_HOME%\\bin")
            
            return True
            
        except Exception as e:
            self.log_signal.emit(f"✗ Maven解压失败: {str(e)}")
            return False
    
    def install_gradle(self):
        """安装Gradle"""
        self.log_signal.emit("\n>>> 安装Gradle...")
        
        # 检查是否已安装
        if EnvironmentChecker.check_gradle():
            version = EnvironmentChecker.get_gradle_version()
            self.log_signal.emit(f"✓ Gradle已安装: {version}")
            return True
        
        # Gradle下载地址
        gradle_version = "8.5"
        gradle_filename = f"gradle-{gradle_version}-bin.zip"
        
        mirrors = [
            {
                "name": "华为云镜像",
                "url": f"https://mirrors.huaweicloud.com/gradle/gradle-{gradle_version}-bin.zip"
            },
            {
                "name": "腾讯云镜像",
                "url": f"https://mirrors.cloud.tencent.com/gradle/gradle-{gradle_version}-bin.zip"
            },
            {
                "name": "官方源",
                "url": f"https://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip"
            }
        ]
        
        # 尝试下载
        download_path = Path(self.temp_dir) / gradle_filename
        if not self.download_file(mirrors, download_path, "Gradle"):
            return False
        
        # 解压到用户目录
        self.log_signal.emit("\n正在解压Gradle...")
        install_dir = Path.home() / "gradle" / f"gradle-{gradle_version}"
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(download_path, 'r') as zf:
                zf.extractall(install_dir.parent)
            
            self.log_signal.emit(f"✓ Gradle解压完成: {install_dir}")
            
            # 设置环境变量建议
            self.log_signal.emit("\n请手动设置以下环境变量：")
            self.log_signal.emit(f"GRADLE_HOME = {install_dir}")
            self.log_signal.emit(f"PATH = %GRADLE_HOME%\\bin")
            
            return True
            
        except Exception as e:
            self.log_signal.emit(f"✗ Gradle解压失败: {str(e)}")
            return False
    
    def install_launch4j(self):
        """安装Launch4j"""
        self.log_signal.emit("\n>>> 安装Launch4j...")
        
        # 检查是否已安装
        if EnvironmentChecker.check_launch4j():
            launch4j_path = os.environ.get('LAUNCH4J_HOME', '')
            self.log_signal.emit(f"✓ Launch4j已安装: {launch4j_path}")
            return True
        
        # Launch4j下载地址
        launch4j_version = "3.14"
        if sys.platform == 'win32':
            launch4j_filename = f"launch4j-{launch4j_version}-win32.zip"
        else:
            launch4j_filename = f"launch4j-{launch4j_version}-linux.tgz"
        
        mirrors = [
            {
                "name": "SourceForge",
                "url": f"https://sourceforge.net/projects/launch4j/files/launch4j-3/{launch4j_version}/{launch4j_filename}/download"
            },
            {
                "name": "GitHub",
                "url": f"https://github.com/TheBoegl/launch4j/releases/download/v{launch4j_version}/{launch4j_filename}"
            }
        ]
        
        # 尝试下载
        download_path = Path(self.temp_dir) / launch4j_filename
        if not self.download_file(mirrors, download_path, "Launch4j"):
            return False
        
        # 解压到用户目录
        self.log_signal.emit("\n正在解压Launch4j...")
        install_dir = Path.home() / "launch4j" / f"launch4j-{launch4j_version}"
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if launch4j_filename.endswith('.zip'):
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(install_dir.parent)
            else:
                with tarfile.open(download_path, 'r:gz') as tf:
                    tf.extractall(install_dir.parent)
            
            # Launch4j解压后可能多一层目录
            extracted_dir = install_dir.parent / "launch4j"
            if extracted_dir.exists() and extracted_dir != install_dir:
                shutil.move(str(extracted_dir), str(install_dir))
            
            self.log_signal.emit(f"✓ Launch4j解压完成: {install_dir}")
            
            # 设置环境变量建议
            self.log_signal.emit("\n请手动设置以下环境变量：")
            self.log_signal.emit(f"LAUNCH4J_HOME = {install_dir}")
            
            return True
            
        except Exception as e:
            self.log_signal.emit(f"✗ Launch4j解压失败: {str(e)}")
            return False
    
    def download_file(self, mirrors, save_path, name):
        """下载文件，支持多镜像源尝试"""
        for mirror in mirrors:
            self.log_signal.emit(f"\n尝试从{mirror['name']}下载{name}...")
            self.log_signal.emit(f"URL: {mirror['url']}")
            
            try:
                # 创建请求
                req = urllib.request.Request(
                    mirror['url'],
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                
                # 打开连接
                with urllib.request.urlopen(req, timeout=30) as response:
                    # 获取文件大小
                    content_length = response.headers.get('Content-Length')
                    if content_length:
                        total_size = int(content_length)
                        self.log_signal.emit(f"文件大小: {total_size / 1024 / 1024:.2f} MB")
                    else:
                        total_size = 0
                    
                    # 下载文件
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
                                    self.log_signal.emit(f"下载进度: {percent}% ({downloaded / 1024 / 1024:.2f}/{total_size / 1024 / 1024:.2f} MB)")
                                self.download_progress.emit(downloaded, total_size)
                
                self.log_signal.emit(f"✓ {name}下载完成")
                return True
                
            except urllib.error.HTTPError as e:
                self.log_signal.emit(f"  HTTP错误: {e.code} {e.reason}")
            except urllib.error.URLError as e:
                self.log_signal.emit(f"  网络错误: {e.reason}")
            except Exception as e:
                self.log_signal.emit(f"  下载失败: {str(e)}")
            
            self.log_signal.emit(f"  {mirror['name']}下载失败，尝试下一个源...")
        
        self.log_signal.emit(f"✗ 所有镜像源均下载失败")
        return False


class EnvironmentConfigDialog(QDialog):
    """环境配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("一键配置Java打包环境")
        self.setFixedSize(700, 600)
        self.setModal(True)
        
        self.setup_thread = None
        
        self.init_ui()
        
        # 检查当前环境
        self.check_current_environment()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel("Java项目打包环境一键配置")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 说明
        desc = QLabel("此工具将帮助您自动下载并配置Java项目打包所需的环境组件")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666666; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # 当前环境状态
        status_group = QGroupBox("当前环境状态")
        status_layout = QVBoxLayout()
        
        self.java_status = QLabel()
        self.maven_status = QLabel()
        self.gradle_status = QLabel()
        self.launch4j_status = QLabel()
        
        status_layout.addWidget(self.java_status)
        status_layout.addWidget(self.maven_status)
        status_layout.addWidget(self.gradle_status)
        status_layout.addWidget(self.launch4j_status)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # 组件选择
        select_group = QGroupBox("选择要安装的组件")
        select_layout = QVBoxLayout()
        
        self.java_check = QCheckBox("Java JDK (需要手动安装)")
        self.java_check.setEnabled(False)
        self.java_check.setChecked(True)
        select_layout.addWidget(self.java_check)
        
        self.maven_check = QCheckBox("Apache Maven (项目构建工具)")
        self.maven_check.setChecked(True)
        select_layout.addWidget(self.maven_check)
        
        self.gradle_check = QCheckBox("Gradle (项目构建工具)")
        select_layout.addWidget(self.gradle_check)
        
        self.launch4j_check = QCheckBox("Launch4j (JAR转EXE工具)")
        select_layout.addWidget(self.launch4j_check)
        
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
        # Java
        if EnvironmentChecker.check_java():
            version = EnvironmentChecker.get_java_version()
            self.java_status.setText(f"✓ Java - {version}")
            self.java_status.setStyleSheet("color: #4CAF50;")
            self.java_check.setChecked(False)
        else:
            self.java_status.setText("✗ Java - 未安装")
            self.java_status.setStyleSheet("color: #F44336;")
        
        # Maven
        if EnvironmentChecker.check_maven():
            version = EnvironmentChecker.get_maven_version()
            self.maven_status.setText(f"✓ Maven - {version}")
            self.maven_status.setStyleSheet("color: #4CAF50;")
            self.maven_check.setChecked(False)
        else:
            self.maven_status.setText("✗ Maven - 未安装")
            self.maven_status.setStyleSheet("color: #F44336;")
        
        # Gradle
        if EnvironmentChecker.check_gradle():
            version = EnvironmentChecker.get_gradle_version()
            self.gradle_status.setText(f"✓ Gradle - {version}")
            self.gradle_status.setStyleSheet("color: #4CAF50;")
            self.gradle_check.setChecked(False)
        else:
            self.gradle_status.setText("✗ Gradle - 未安装")
            self.gradle_status.setStyleSheet("color: #F44336;")
        
        # Launch4j
        if EnvironmentChecker.check_launch4j():
            launch4j_path = os.environ.get('LAUNCH4J_HOME', '')
            self.launch4j_status.setText(f"✓ Launch4j - {launch4j_path}")
            self.launch4j_status.setStyleSheet("color: #4CAF50;")
            self.launch4j_check.setChecked(False)
        else:
            self.launch4j_status.setText("✗ Launch4j - 未配置")
            self.launch4j_status.setStyleSheet("color: #F44336;")
    
    def start_setup(self):
        """开始配置环境"""
        # 收集要安装的组件
        components = []
        
        if self.java_check.isChecked():
            components.append("java")
        if self.maven_check.isChecked():
            components.append("maven")
        if self.gradle_check.isChecked():
            components.append("gradle")
        if self.launch4j_check.isChecked():
            components.append("launch4j")
        
        if not components:
            QMessageBox.information(self, "提示", "所有组件已安装，无需配置！")
            return
        
        # 禁用按钮
        self.install_btn.setEnabled(False)
        self.log_text.clear()
        
        # 创建并启动线程
        self.setup_thread = EnvironmentSetupThread(components)
        self.setup_thread.log_signal.connect(self.append_log)
        self.setup_thread.progress_signal.connect(self.update_progress)
        self.setup_thread.download_progress.connect(self.update_download_progress)
        self.setup_thread.finished.connect(self.on_setup_finished)
        self.setup_thread.start()
    
    def append_log(self, text):
        """添加日志"""
        # 根据内容设置颜色
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
        """更新进度"""
        self.progress_bar.setValue(value)
        if status:
            self.status_label.setText(status)
    
    def update_download_progress(self, current, total):
        """更新下载进度"""
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
            self.status_label.setText(f"下载中... {current / 1024 / 1024:.2f}/{total / 1024 / 1024:.2f} MB")
    
    def on_setup_finished(self, success, message):
        """配置完成"""
        self.install_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "成功", f"环境配置完成！\n\n{message}\n\n请重启程序以应用新的环境变量。")
        else:
            QMessageBox.warning(self, "警告", f"环境配置遇到问题：\n{message}")
        
        # 刷新状态
        self.check_current_environment()


class JavaPackagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.java_file_path = ""
        self.project_dir = ""
        self.icon_path = ""
        self.output_dir = ""
        self.manifest_path = ""
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
        """启动时检查环境"""
        self.check_environment()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Java项目打包工具 v2.0")
        self.setFixedSize(850, 850)
        
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
        
        # 项目类型选择
        project_type_group = QGroupBox("项目类型")
        project_type_layout = QHBoxLayout()
        project_type_layout.addWidget(QLabel("构建工具:"))
        
        self.project_type_combo = QComboBox()
        self.project_type_combo.addItems(["Maven项目", "Gradle项目", "普通Java项目"])
        self.project_type_combo.currentIndexChanged.connect(self.on_project_type_changed)
        project_type_layout.addWidget(self.project_type_combo)
        project_type_layout.addStretch()
        
        project_type_group.setLayout(project_type_layout)
        main_layout.addWidget(project_type_group)
        
        # 文件选择区域
        file_group = QGroupBox("项目设置")
        file_layout = QVBoxLayout()
        
        # 项目目录选择
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("项目目录:"))
        self.project_dir_edit = QLineEdit()
        self.project_dir_edit.setPlaceholderText("选择Java项目根目录...")
        project_layout.addWidget(self.project_dir_edit)
        self.project_dir_btn = QPushButton("浏览")
        self.project_dir_btn.clicked.connect(self.select_project_dir)
        project_layout.addWidget(self.project_dir_btn)
        file_layout.addLayout(project_layout)
        
        # 主类选择
        main_class_layout = QHBoxLayout()
        main_class_layout.addWidget(QLabel("主类:"))
        self.main_class_edit = QLineEdit()
        self.main_class_edit.setPlaceholderText("例如: com.example.Main")
        main_class_layout.addWidget(self.main_class_edit)
        self.detect_main_btn = QPushButton("自动检测")
        self.detect_main_btn.clicked.connect(self.detect_main_class)
        main_class_layout.addWidget(self.detect_main_btn)
        file_layout.addLayout(main_class_layout)
        
        # 图标文件选择
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(QLabel("图标文件:"))
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("选择.ico图标文件（打包EXE时使用）...")
        icon_layout.addWidget(self.icon_edit)
        self.icon_btn = QPushButton("浏览")
        self.icon_btn.clicked.connect(self.select_icon_file)
        icon_layout.addWidget(self.icon_btn)
        file_layout.addLayout(icon_layout)
        
        # 输出目录选择
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("默认：项目目录下的target或build")
        output_layout.addWidget(self.output_dir_edit)
        self.output_dir_btn = QPushButton("浏览")
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_layout.addWidget(self.output_dir_btn)
        file_layout.addLayout(output_layout)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 打包格式选择
        format_group = QGroupBox("打包格式")
        format_layout = QVBoxLayout()
        
        self.jar_radio = QRadioButton("JAR包 (可执行JAR)")
        self.jar_radio.setChecked(True)
        format_layout.addWidget(self.jar_radio)
        
        self.exe_radio = QRadioButton("EXE文件 (需要Launch4j)")
        format_layout.addWidget(self.exe_radio)
        
        format_hint = QLabel("提示：打包EXE需要先安装配置Launch4j，点击「一键配置环境」自动安装")
        format_hint.setStyleSheet("color: #666666; font-size: 11px;")
        format_hint.setWordWrap(True)
        format_layout.addWidget(format_hint)
        
        format_group.setLayout(format_layout)
        main_layout.addWidget(format_group)
        
        # JAR打包选项
        jar_options_group = QGroupBox("JAR打包选项")
        jar_options_layout = QVBoxLayout()
        
        self.include_deps_check = QCheckBox("包含依赖库")
        self.include_deps_check.setChecked(True)
        jar_options_layout.addWidget(self.include_deps_check)
        
        self.include_resources_check = QCheckBox("包含资源文件")
        self.include_resources_check.setChecked(True)
        jar_options_layout.addWidget(self.include_resources_check)
        
        jar_options_group.setLayout(jar_options_layout)
        main_layout.addWidget(jar_options_group)
        
        # 附加选项
        option_layout = QHBoxLayout()
        self.clean_check = QCheckBox("打包前清理旧文件")
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
    
    def show_environment_setup(self):
        """显示环境配置对话框"""
        dialog = EnvironmentConfigDialog(self)
        dialog.exec_()
        
        # 刷新环境状态
        self.update_env_status_display()
        self.check_environment()
    
    # ... 其余方法与之前相同（select_project_dir, detect_main_class等）
    
    def on_project_type_changed(self, index):
        """项目类型改变时的处理"""
        pass
    
    def update_env_status_display(self):
        """更新环境状态显示"""
        java_ok = EnvironmentChecker.check_java()
        maven_ok = EnvironmentChecker.check_maven()
        gradle_ok = EnvironmentChecker.check_gradle()
        launch4j_ok = EnvironmentChecker.check_launch4j()
        
        status_parts = []
        
        if java_ok:
            status_parts.append("✓ Java")
        else:
            status_parts.append("✗ Java")
        
        if maven_ok:
            status_parts.append("✓ Maven")
        else:
            status_parts.append("✗ Maven")
        
        if gradle_ok:
            status_parts.append("✓ Gradle")
        else:
            status_parts.append("✗ Gradle")
        
        if launch4j_ok:
            status_parts.append("✓ Launch4j")
        else:
            status_parts.append("✗ Launch4j")
        
        self.env_status_label.setText(" | ".join(status_parts))
        
        if java_ok:
            self.env_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.env_status_label.setStyleSheet("color: #F44336; font-weight: bold;")
    
    def check_environment(self):
        """检查环境"""
        self.log_text.clear()
        self.log("=" * 60)
        self.log("开始检查Java环境...")
        
        # 检查Java
        if EnvironmentChecker.check_java():
            self.log("✓ Java 可用")
            version = EnvironmentChecker.get_java_version()
            if version:
                self.log(f"  {version}")
        else:
            self.log("✗ Java 未安装或未配置到PATH")
            self.log("  请安装JDK 8或更高版本，或点击「一键配置环境」获取指引")
        
        # 检查Javac
        try:
            result = subprocess.run(
                ["javac", "-version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.log(f"✓ Javac 可用: {result.stdout.strip() or result.stderr.strip()}")
            else:
                self.log("✗ Javac 不可用")
        except Exception:
            self.log("✗ Javac 不可用")
        
        # 检查Maven
        if EnvironmentChecker.check_maven():
            self.log("✓ Maven 可用")
            version = EnvironmentChecker.get_maven_version()
            if version:
                self.log(f"  {version}")
        else:
            self.log("✗ Maven 未安装")
        
        # 检查Gradle
        if EnvironmentChecker.check_gradle():
            self.log("✓ Gradle 可用")
            version = EnvironmentChecker.get_gradle_version()
            if version:
                self.log(f"  {version}")
        else:
            self.log("✗ Gradle 未安装")
        
        # 检查Launch4j
        if EnvironmentChecker.check_launch4j():
            self.log("✓ Launch4j 可用")
            launch4j_path = os.environ.get('LAUNCH4J_HOME', '')
            self.log(f"  LAUNCH4J_HOME: {launch4j_path}")
        else:
            self.log("✗ Launch4j 未配置")
        
        self.update_env_status_display()
        self.log("环境检查完成")
        self.log("=" * 60)
    
    def show_environment_guide(self):
        """显示环境配置指南"""
        guide_text = """
环境配置指南：

方式一：一键自动配置（推荐）
点击「一键配置环境」按钮，程序将自动下载并安装所需组件。

方式二：手动配置

1. Java JDK (必需)
   - 官方下载: https://www.oracle.com/java/technologies/downloads/
   - 国内镜像: https://mirrors.huaweicloud.com/java/jdk/
   - 安装后设置 JAVA_HOME 环境变量

2. Apache Maven (可选)
   - 官方下载: https://maven.apache.org/download.cgi
   - 国内镜像: https://mirrors.huaweicloud.com/apache/maven/
   - 设置 MAVEN_HOME 环境变量

3. Gradle (可选)
   - 官方下载: https://gradle.org/releases/
   - 国内镜像: https://mirrors.huaweicloud.com/gradle/
   - 设置 GRADLE_HOME 环境变量

4. Launch4j (可选，用于打包EXE)
   - 下载地址: https://sourceforge.net/projects/launch4j/
   - 设置 LAUNCH4J_HOME 环境变量
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("环境配置指南")
        msg_box.setText(guide_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.exec_()
    
    def select_project_dir(self):
        """选择项目目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择Java项目目录")
        if dir_path:
            self.project_dir = dir_path
            self.project_dir_edit.setText(dir_path)
    
    def detect_main_class(self):
        """自动检测主类"""
        QMessageBox.information(self, "提示", "自动检测主类功能开发中...")
    
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
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
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
        """更新进度"""
        pass
    
    def update_status(self, message):
        """更新状态栏"""
        self.statusBar().showMessage(message)
    
    def start_packaging(self):
        """开始打包"""
        if not self.project_dir:
            QMessageBox.warning(self, "警告", "请先选择项目目录！")
            return
        
        if not EnvironmentChecker.check_java():
            reply = QMessageBox.question(
                self, "环境检查",
                "Java环境未配置，是否现在配置？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.show_environment_setup()
            return
        
        QMessageBox.information(self, "提示", "打包功能开发中...")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = JavaPackagerGUI()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()