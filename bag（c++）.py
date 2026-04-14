import sys
import os
import subprocess
import threading
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QRadioButton,
    QTextEdit, QCheckBox, QGroupBox, QMessageBox,
    QProgressBar, QDialog, QDialogButtonBox, QComboBox
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat


class LogSignal(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    status_signal = pyqtSignal(str)
    install_finished = pyqtSignal(bool, str)
    dialog_log_signal = pyqtSignal(str)
    enable_ok_signal = pyqtSignal()


class EnvChecker:
    """C++ 编译环境检测"""

    @staticmethod
    def check_compiler():
        for name in ('g++', 'clang++'):
            try:
                r = subprocess.run([name, '--version'], capture_output=True, text=True, timeout=10,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                if r.returncode == 0:
                    return name, r.stdout.strip().split('\n')[0]
            except Exception:
                pass
        return None, None

    @staticmethod
    def check_upx():
        try:
            r = subprocess.run(['upx', '-V'], capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return r.returncode == 0, r.stdout.strip().split('\n')[0] if r.returncode == 0 else None
        except Exception:
            return False, None

    @staticmethod
    def check_windres():
        try:
            r = subprocess.run(['windres', '--version'], capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return r.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_missing_required():
        c, _ = EnvChecker.check_compiler()
        return [] if c else ['g++ / MinGW-w64']

    @staticmethod
    def get_missing_optional():
        m = []
        if not EnvChecker.check_upx()[0]:
            m.append('upx')
        if not EnvChecker.check_windres():
            m.append('windres')
        return m


class InstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("安装编译环境")
        self.setFixedSize(600, 400)
        self.setModal(True)
        lay = QVBoxLayout(self)
        t = QLabel("正在安装C++编译环境...")
        t.setFont(QFont("Arial", 12, QFont.Bold))
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        self.status = QLabel("准备中...")
        self.status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        self.log_box.setStyleSheet("background:#1e1e1e;color:#d4d4d4;")
        lay.addWidget(self.log_box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        self.ok_btn = bb.button(QDialogButtonBox.Ok)
        self.ok_btn.setEnabled(False)
        lay.addWidget(bb)

    def add_log(self, text):
        if self.isVisible():
            self.log_box.append(text)
            c = self.log_box.textCursor()
            c.movePosition(QTextCursor.End)
            self.log_box.setTextCursor(c)

    def set_prog(self, v, s=""):
        if self.isVisible():
            self.bar.setValue(v)
            if s:
                self.status.setText(s)

    def enable_ok(self):
        if self.isVisible():
            self.ok_btn.setEnabled(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.src_path = ""
        self.icon_path = ""
        self.out_dir = ""
        self.sig = LogSignal()
        self.sig.log_signal.connect(self._append_log)
        self.sig.progress_signal.connect(self._update_prog)
        self.sig.status_signal.connect(lambda m: self.statusBar().showMessage(m))
        self.sig.install_finished.connect(self._on_install_done)
        self.sig.dialog_log_signal.connect(self._safe_dlg_log)
        self.sig.enable_ok_signal.connect(self._safe_dlg_ok)
        self.dlg = None
        self._build_ui()
        QTimer.singleShot(500, self._auto_check)

    # ── 信号安全转发 ──
    def _safe_dlg_log(self, t):
        if self.dlg and self.dlg.isVisible():
            self.dlg.add_log(t)

    def _safe_dlg_ok(self):
        if self.dlg and self.dlg.isVisible():
            self.dlg.enable_ok()

    def _update_prog(self, v, s=""):
        if self.dlg:
            self.dlg.set_prog(v, s)

    # ── UI 构建 ──
    def _build_ui(self):
        self.setWindowTitle("C++ 一键打包工具 v2.1")
        self.setFixedSize(750, 780)
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setSpacing(10)

        # 环境状态栏
        eh = QHBoxLayout()
        eh.addWidget(QLabel("环境状态:"))
        self.env_lbl = QLabel()
        self._refresh_env_label()
        eh.addWidget(self.env_lbl)
        eh.addStretch()
        b1 = QPushButton("检查环境")
        b1.clicked.connect(self._do_check)
        eh.addWidget(b1)
        b2 = QPushButton("一键安装环境")
        b2.setStyleSheet("QPushButton{background:#2196F3;color:white;padding:5px 10px;border-radius:3px}"
                         "QPushButton:hover{background:#1976D2}")
        b2.clicked.connect(self._do_install)
        eh.addWidget(b2)
        root.addLayout(eh)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#ccc")
        root.addWidget(sep)

        # 文件设置
        fg = QGroupBox("文件设置")
        fl = QVBoxLayout()
        for label_text, placeholder, browse_slot, attr in [
            ("C++ 源文件:", "选择 .cpp 文件...", self._pick_src, "src_edit"),
            ("图标文件:", "选择 .ico 文件（可选）...", self._pick_icon, "icon_edit"),
            ("输出目录:", "默认：与源文件同目录", self._pick_out, "out_edit"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            setattr(self, attr, edit)
            row.addWidget(edit)
            btn = QPushButton("浏览")
            btn.clicked.connect(browse_slot)
            row.addWidget(btn)
            fl.addLayout(row)
        fg.setLayout(fl)
        root.addWidget(fg)

        # 打包模式
        mg = QGroupBox("打包模式")
        ml = QVBoxLayout()
        self.mode_normal = QRadioButton("普通编译  (-O2)")
        self.mode_normal.setChecked(True)
        ml.addWidget(self.mode_normal)
        self.mode_protect = QRadioButton("加固编译  (-O3 -s + UPX 加壳)")
        ml.addWidget(self.mode_protect)
        hint = QLabel("加固模式：最高优化 + 剥离符号表 + UPX 压缩加壳，显著增加逆向难度")
        hint.setStyleSheet("color:#666;font-size:11px")
        hint.setWordWrap(True)
        ml.addWidget(hint)
        mg.setLayout(ml)
        root.addWidget(mg)

        # 编译选项
        og = QGroupBox("编译选项")
        ol = QVBoxLayout()
        sr = QHBoxLayout()
        sr.addWidget(QLabel("C++ 标准:"))
        self.std_cb = QComboBox()
        self.std_cb.addItems(["C++11", "C++14", "C++17", "C++20", "C++23"])
        self.std_cb.setCurrentIndex(2)
        sr.addWidget(self.std_cb)
        sr.addStretch()
        ol.addLayout(sr)
        self.chk_static = QCheckBox("静态链接（推荐，减少运行时依赖）")
        self.chk_static.setChecked(True)
        ol.addWidget(self.chk_static)
        self.chk_clean = QCheckBox("编译后自动清理临时文件")
        self.chk_clean.setChecked(True)
        ol.addWidget(self.chk_clean)
        og.setLayout(ol)
        root.addWidget(og)

        # 开始按钮
        bh = QHBoxLayout()
        bh.addStretch()
        self.btn_go = QPushButton("开始编译")
        self.btn_go.setFixedSize(150, 40)
        self.btn_go.setStyleSheet(
            "QPushButton{background:#4CAF50;color:white;font-weight:bold;font-size:14px;border-radius:4px}"
            "QPushButton:hover{background:#45a049}"
            "QPushButton:disabled{background:#ccc}")
        self.btn_go.clicked.connect(self._start)
        bh.addWidget(self.btn_go)
        bh.addStretch()
        root.addLayout(bh)

        # 日志
        root.addWidget(QLabel("实时日志:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        self.log_box.setStyleSheet("QTextEdit{background:#1e1e1e;color:#d4d4d4;border:1px solid #333;border-radius:3px}")
        root.addWidget(self.log_box)
        self.statusBar().showMessage("就绪")

    # ── 环境标签 ──
    def _refresh_env_label(self):
        mr = EnvChecker.get_missing_required()
        mo = EnvChecker.get_missing_optional()
        if not mr and not mo:
            self.env_lbl.setText("✓ 环境完整")
            self.env_lbl.setStyleSheet("color:#4CAF50;font-weight:bold")
        elif not mr:
            self.env_lbl.setText(f"⚠ 缺 {len(mo)} 个可选工具")
            self.env_lbl.setStyleSheet("color:#FF9800;font-weight:bold")
        else:
            self.env_lbl.setText(f"✗ 缺 {len(mr)} 个必需工具")
            self.env_lbl.setStyleSheet("color:#F44336;font-weight:bold")

    # ── 文件选择 ──
    def _pick_src(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择C++文件", "", "C++ (*.cpp *.cc *.cxx);;All (*)")
        if p:
            self.src_path = p
            self.src_edit.setText(p)

    def _pick_icon(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图标", "", "Icon (*.ico)")
        if p:
            self.icon_path = p
            self.icon_edit.setText(p)

    def _pick_out(self):
        d = str(Path(self.src_path).parent) if self.src_path else ""
        p = QFileDialog.getExistingDirectory(self, "输出目录", d)
        if p:
            self.out_dir = p
            self.out_edit.setText(p)

    # ── 日志 ──
    def _append_log(self, text):
        cmap = {"✓": "#4CAF50", "✗": "#F44336", ">>>": "#FF9800", "=": "#2196F3", "⚠": "#FFC107"}
        c = "#d4d4d4"
        for k, v in cmap.items():
            if text.startswith(k):
                c = v
                break
        cur = self.log_box.textCursor()
        cur.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(c))
        cur.insertText(text + "\n", fmt)
        self.log_box.setTextCursor(cur)
        self.log_box.ensureCursorVisible()

    def log(self, msg):
        self.sig.log_signal.emit(msg)

    # ── 环境检查 ──
    def _auto_check(self):
        self._do_check()
        mr = EnvChecker.get_missing_required()
        if mr:
            QTimer.singleShot(500, lambda: self._ask_install(mr))

    def _ask_install(self, items):
        msg = "以下工具未安装：\n\n" + "\n".join(f"• {i}" for i in items)
        msg += "\n\n是否自动安装？"
        if QMessageBox.question(self, "环境检查", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._do_install()

    def _do_check(self):
        self.log_box.clear()
        self.log("=" * 50)
        self.log("检查 C++ 编译环境...")

        c, v = EnvChecker.check_compiler()
        if c:
            self.log(f"✓ {c} 可用")
            self.log(f"  {v}")
        else:
            self.log("✗ 未找到 g++ / clang++")
            self.log("  推荐安装 MinGW-w64: https://www.mingw-w64.org/")
            self.log("  或 MSYS2: pacman -S mingw-w64-x86_64-gcc")

        ok, v2 = EnvChecker.check_upx()
        if ok:
            self.log(f"✓ UPX 可用 — {v2}")
        else:
            self.log("⚠ UPX 未安装（加固模式需要）")

        if EnvChecker.check_windres():
            self.log("✓ windres 可用（图标嵌入）")
        else:
            self.log("⚠ windres 未安装（图标功能需要）")

        self._refresh_env_label()
        self.log("检查完成")
        self.log("=" * 50)

    # ── 环境安装 ──
    def _do_install(self):
        self.dlg = InstallDialog(self)
        threading.Thread(target=self._install_thread, daemon=True).start()
        self.dlg.exec_()

    def _install_thread(self):
        try:
            self.sig.progress_signal.emit(5, "检测包管理器...")
            self.sig.log_signal.emit("\n>>> 检测包管理器...")

            mgrs = []
            checks = [
                ("winget", ['winget', '--version'],
                 ['winget', 'install', '-e', '--id', 'mingw', '--accept-source-agreements', '--accept-package-agreements'],
                 ['winget', 'install', '-e', '--id', 'upx.upx', '--accept-source-agreements', '--accept-package-agreements']),
                ("choco", ['choco', '--version'],
                 ['choco', 'install', 'mingw', '-y'],
                 ['choco', 'install', 'upx', '-y']),
                ("scoop", ['scoop', '--version'],
                 ['scoop', 'install', 'mingw'],
                 ['scoop', 'install', 'upx']),
            ]
            for name, vc, cg, cu in checks:
                try:
                    r = subprocess.run(vc, capture_output=True, text=True, timeout=10,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    if r.returncode == 0:
                        mgrs.append((name, cg, cu))
                except Exception:
                    pass

            if not mgrs:
                self.sig.log_signal.emit("✗ 未检测到包管理器")
                self.sig.log_signal.emit("  请手动安装 MinGW-w64:")
                self.sig.log_signal.emit("  • https://www.mingw-w64.org/")
                self.sig.log_signal.emit("  • https://www.msys2.org/  → pacman -S mingw-w64-x86_64-gcc")
                self.sig.log_signal.emit("  • https://winlibs.com/")
                self.sig.progress_signal.emit(0, "失败")
                self.sig.enable_ok_signal.emit()
                self.sig.install_finished.emit(False, "未找到包管理器，请手动安装")
                return

            self.sig.log_signal.emit(f"✓ 可用: {', '.join(m[0] for m in mgrs)}")

            # 安装编译器
            self.sig.progress_signal.emit(25, "安装 g++ 编译器...")
            self.sig.log_signal.emit("\n>>> 安装 MinGW-w64...")
            gcc_ok = False
            for name, cg, cu in mgrs:
                self.sig.log_signal.emit(f"  [{name}] {' '.join(cg)}")
                if self._run_install(cg):
                    self.sig.log_signal.emit(f"✓ {name} 安装编译器成功")
                    gcc_ok = True
                    break
                self.sig.log_signal.emit(f"  {name} 失败，尝试下一个...")
            if not gcc_ok:
                self.sig.log_signal.emit("✗ 编译器安装失败，请手动安装")

            # 安装 UPX
            self.sig.progress_signal.emit(65, "安装 UPX...")
            self.sig.log_signal.emit("\n>>> 安装 UPX...")
            upx_ok = False
            for name, cg, cu in mgrs:
                self.sig.log_signal.emit(f"  [{name}] {' '.join(cu)}")
                if self._run_install(cu):
                    self.sig.log_signal.emit(f"✓ {name} 安装 UPX 成功")
                    upx_ok = True
                    break
                self.sig.log_signal.emit(f"  {name} 失败，尝试下一个...")
            if not upx_ok:
                self.sig.log_signal.emit("⚠ UPX 安装失败（可选）")

            # 刷新 PATH
            self.sig.progress_signal.emit(90, "验证...")
            self._refresh_path()
            c, _ = EnvChecker.check_compiler()
            if c:
                self.sig.log_signal.emit(f"✓ {c} 验证通过")
                self.sig.install_finished.emit(True, "安装成功")
            else:
                self.sig.log_signal.emit("⚠ 验证未通过，请重启工具后重试")
                self.sig.install_finished.emit(False, "请重启工具后再试")

            self.sig.progress_signal.emit(100, "完成")
            self.sig.enable_ok_signal.emit()

        except Exception as e:
            self.sig.log_signal.emit(f"✗ 出错: {e}")
            self.sig.progress_signal.emit(0, "失败")
            self.sig.enable_ok_signal.emit()
            self.sig.install_finished.emit(False, str(e))

    def _run_install(self, cmd):
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding='utf-8', errors='replace',
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            while True:
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                if line and line.strip():
                    self.sig.log_signal.emit(f"    {line.strip()}")
                    self.sig.dialog_log_signal.emit(line.strip())
            return p.returncode == 0
        except Exception:
            return False

    def _refresh_path(self):
        try:
            import winreg
            for hive, sub in [
                (winreg.HKEY_CURRENT_USER, "Environment"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ]:
                try:
                    k = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
                    val, _ = winreg.QueryValueEx(k, "Path")
                    winreg.CloseKey(k)
                    cur = os.environ.get("PATH", "").lower()
                    for p in val.split(";"):
                        if p and p.lower() not in cur:
                            os.environ["PATH"] = p + ";" + os.environ["PATH"]
                except Exception:
                    pass
        except Exception:
            pass

    def _on_install_done(self, ok, msg):
        if ok:
            QMessageBox.information(self, "成功", f"环境安装完成！\n{msg}")
        else:
            QMessageBox.warning(self, "警告", f"安装遇到问题：\n{msg}")
        self._refresh_env_label()

    # ── 编译流程 ──
    def _start(self):
        if not self.src_path:
            QMessageBox.warning(self, "警告", "请先选择 C++ 源文件！")
            return
        if not os.path.exists(self.src_path):
            QMessageBox.warning(self, "警告", "文件不存在！")
            return
        if self.icon_path and not os.path.exists(self.icon_path):
            QMessageBox.warning(self, "警告", "图标文件不存在！")
            return
        if self.out_dir and not os.path.isdir(self.out_dir):
            QMessageBox.warning(self, "警告", "输出目录不存在！")
            return

        mr = EnvChecker.get_missing_required()
        if mr:
            if QMessageBox.question(self, "环境检查",
                                    f"{'，'.join(mr)}\n\n是否立即安装？",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self._do_install()
            return

        if self.mode_protect.isChecked() and not EnvChecker.check_upx()[0]:
            if QMessageBox.question(self, "UPX 未安装",
                                    "加固模式推荐 UPX 加壳。\n未检测到 UPX，将仅使用 -O3 -s 编译。\n\n继续？",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                return

        self._set_btns(False)
        self.log_box.clear()
        self.log("=" * 50)
        self.log("开始编译...")
        threading.Thread(target=self._compile_thread, daemon=True).start()

    def _set_btns(self, on):
        self.btn_go.setEnabled(on)

    def _compile_thread(self):
        temps = []  # 临时文件列表
        try:
            src = Path(self.src_path)
            src_dir = src.parent
            name = src.stem
            out_dir = Path(self.out_dir) if self.out_dir and os.path.isdir(self.out_dir) else src_dir
            exe = out_dir / f"{name}.exe"

            std_map = {"C++11": "-std=c++11", "C++14": "-std=c++14",
                       "C++17": "-std=c++17", "C++20": "-std=c++20", "C++23": "-std=c++23"}
            std_flag = std_map.get(self.std_cb.currentText(), "-std=c++17")
            protect = self.mode_protect.isChecked()
            static = self.chk_static.isChecked()

            compiler, ver = EnvChecker.check_compiler()
            if not compiler:
                raise RuntimeError("未找到 C++ 编译器")
            self.log(f"编译器: {compiler}")
            self.log(f"  {ver}")
            self.log(f"标准: {self.std_cb.currentText()}  |  静态链接: {'是' if static else '否'}")
            self.log(f"源文件: {src.name}")
            self.log(f"输出: {exe}")

            cmd = [compiler, std_flag]

            # ── 图标 ──
            if self.icon_path and EnvChecker.check_windres():
                self.log("\n>>> 处理图标资源...")
                rc = src_dir / f"{name}_icon.rc"
                obj = src_dir / f"{name}_icon.o"
                try:
                    rc.write_text(f'IDI_ICON1 ICON "{Path(self.icon_path).resolve()}"\n', encoding='utf-8')
                    temps.append(rc)
                    wcmd = ['windres', str(rc), '-o', str(obj)]
                    self.log(f"  {' '.join(wcmd)}")
                    r = subprocess.run(wcmd, capture_output=True, text=True, cwd=str(src_dir),
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    if r.returncode == 0 and obj.exists():
                        self.log("  ✓ 图标编译成功")
                        cmd.append(str(obj))
                        temps.append(obj)
                    else:
                        self.log(f"  ✗ 失败: {(r.stderr or '').strip()}")
                        if obj.exists():
                            obj.unlink()
                except Exception as e:
                    self.log(f"  ✗ 异常: {e}")
                    for f in (rc, obj):
                        if f.exists():
                            f.unlink()
            elif self.icon_path:
                self.log("\n⚠ 跳过图标：windres 不可用")

            # ── 编译参数 ──
            if protect:
                self.log("\n>>> 加固编译 (-O3 -s ...)")
                self.sig.status_signal.emit("加固编译中...")
                cmd.extend(['-O3', '-s', '-ffunction-sections', '-fdata-sections'])
            else:
                self.log("\n>>> 普通编译 (-O2)")
                self.sig.status_signal.emit("编译中...")
                cmd.extend(['-O2'])

            if static:
                cmd.append('-static')
            if protect:
                cmd.extend(['-Wl,--gc-sections'])

            cmd.extend(['-o', str(exe), str(src)])

            self.log(f"\n{' '.join(str(c) for c in cmd)}")
            self._run_cmd(cmd, src_dir)

            # ── UPX ──
            if protect:
                upx_ok, _ = EnvChecker.check_upx()
                if upx_ok and exe.exists():
                    self.log("\n>>> UPX 加壳...")
                    ucmd = ['upx', '--best', '--lzma', str(exe)]
                    self.log(f"  {' '.join(ucmd)}")
                    r = subprocess.run(ucmd, capture_output=True, text=True, cwd=str(out_dir),
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    if r.returncode == 0:
                        self.log("  ✓ 加壳成功")
                        for ln in (r.stdout + r.stderr).strip().split('\n'):
                            if ln.strip():
                                self.log(f"    {ln.strip()}")
                    else:
                        self.log(f"  ✗ 加壳失败: {(r.stderr or '').strip()}")
                elif not upx_ok:
                    self.log("\n⚠ UPX 不可用，跳过加壳")

            # ── 清理 ──
            if self.chk_clean.isChecked() and temps:
                self.log("\n>>> 清理临时文件...")
                for f in temps:
                    if f.exists():
                        try:
                            f.unlink()
                            self.log(f"  已删除: {f.name}")
                        except Exception as e:
                            self.log(f"  删除失败: {f.name} — {e}")

            # ── 结果 ──
            self.log("\n" + "=" * 50)
            if exe.exists():
                sz = exe.stat().st_size
                ss = f"{sz / 1048576:.2f} MB" if sz >= 1048576 else f"{sz / 1024:.1f} KB"
                self.log(f"✓ 编译完成！")
                self.log(f"  文件: {exe}")
                self.log(f"  大小: {ss}")
                self.sig.status_signal.emit("编译完成")
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self, "成功", f"编译完成！\n\n{exe}\n大小: {ss}"))
            else:
                raise RuntimeError("编译命令执行完毕但未生成 EXE")

        except subprocess.CalledProcessError as e:
            self.log(f"\n✗ 编译失败（返回码 {e.returncode}）")
            self.sig.status_signal.emit("编译失败")
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                self, "编译失败",
                f"返回码 {e.returncode}，请检查源代码。\n\n{' '.join(str(c) for c in e.cmd)}"))
        except Exception as e:
            self.log(f"\n✗ 失败: {e}")
            self.sig.status_signal.emit("失败")
            QTimer.singleShot(0, lambda err=str(e): QMessageBox.critical(self, "错误", str(err)))
        finally:
            QTimer.singleShot(0, lambda: self._set_btns(True))

    def _run_cmd(self, cmd, cwd):
        p = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace',
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        while True:
            line = p.stdout.readline()
            if not line and p.poll() is not None:
                break
            if line and line.strip():
                self.log(line.strip())
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
