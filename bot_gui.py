"""
FSBot 可视化控制台 (bot_gui.py)
用法：直接运行此文件：python bot_gui.py
它会在独立线程中启动 main.py 里的 bot，同时显示 Tkinter 控制窗口。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
import shutil
import json
import subprocess
import queue
import time
import urllib.request
import urllib.error

# ───── 路径配置 ─────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODS_DIR = os.path.join(BASE_DIR, 'mods')
os.makedirs(MODS_DIR, exist_ok=True)

# ───── 全局状态 ─────
bot_process = None       # subprocess.Popen 对象
log_queue = queue.Queue()  # 日志行队列（子进程 stdout）


def get_mod_list():
    """返回 mods/ 目录下所有 .fsbods 文件信息列表"""
    result = []
    for fname in os.listdir(MODS_DIR):
        if fname.endswith('.fsbods'):
            path = os.path.join(MODS_DIR, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get('name', fname)
                ver = data.get('version', '?')
                desc = data.get('description', '')
                result.append({'filename': fname, 'name': name, 'version': ver, 'desc': desc, 'path': path})
            except Exception:
                result.append({'filename': fname, 'name': fname, 'version': '?', 'desc': '(解析失败)', 'path': path})
    return result


class FSBotGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FSBot 控制台')
        self.geometry('820x600')
        self.resizable(True, True)
        self.configure(bg='#1e1e2e')
        self._build_ui()
        self._refresh_mod_list()
        self._poll_log()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────
    def _build_ui(self):
        # ── 顶部标题栏 ──
        header = tk.Frame(self, bg='#313244', pady=8)
        header.pack(fill='x')
        tk.Label(header, text='🤖  FSBot 控制台', font=('Microsoft YaHei', 16, 'bold'),
                 bg='#313244', fg='#cdd6f4').pack(side='left', padx=16)

        # Bot 状态指示
        self.status_label = tk.Label(header, text='● 未运行', font=('Microsoft YaHei', 11),
                                     bg='#313244', fg='#f38ba8')
        self.status_label.pack(side='right', padx=16)

        # ── 主体左右分栏 ──
        main_frame = tk.Frame(self, bg='#1e1e2e')
        main_frame.pack(fill='both', expand=True, padx=10, pady=8)

        # 左栏：Bot 控制 + 模组管理
        left = tk.Frame(main_frame, bg='#1e1e2e', width=300)
        left.pack(side='left', fill='y', padx=(0, 6))
        left.pack_propagate(False)

        # 右栏：日志
        right = tk.Frame(main_frame, bg='#1e1e2e')
        right.pack(side='left', fill='both', expand=True)

        self._build_bot_control(left)
        self._build_mod_panel(left)
        self._build_dashboard_panel(left)
        self._build_log_panel(right)

    def _build_bot_control(self, parent):
        frame = tk.LabelFrame(parent, text='  机器人控制  ', font=('Microsoft YaHei', 10, 'bold'),
                              bg='#1e1e2e', fg='#89b4fa', padx=10, pady=8,
                              labelanchor='n', bd=1, relief='groove')
        frame.pack(fill='x', pady=(0, 8))

        self.btn_start = tk.Button(
            frame, text='▶  启动机器人', font=('Microsoft YaHei', 11, 'bold'),
            bg='#a6e3a1', fg='#1e1e2e', activebackground='#94e2d5',
            bd=0, padx=10, pady=6, cursor='hand2',
            command=self._start_bot
        )
        self.btn_start.pack(fill='x', pady=(0, 6))

        self.btn_stop = tk.Button(
            frame, text='■  停止机器人', font=('Microsoft YaHei', 11, 'bold'),
            bg='#f38ba8', fg='#1e1e2e', activebackground='#eba0ac',
            bd=0, padx=10, pady=6, cursor='hand2',
            state='disabled',
            command=self._stop_bot
        )
        self.btn_stop.pack(fill='x')

    def _build_mod_panel(self, parent):
        frame = tk.LabelFrame(parent, text='  模组管理  ', font=('Microsoft YaHei', 10, 'bold'),
                              bg='#1e1e2e', fg='#89b4fa', padx=10, pady=8,
                              labelanchor='n', bd=1, relief='groove')
        frame.pack(fill='both', expand=True)

        # 模组列表
        list_frame = tk.Frame(frame, bg='#1e1e2e')
        list_frame.pack(fill='both', expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical')
        self.mod_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            bg='#313244', fg='#cdd6f4', selectbackground='#89b4fa',
            selectforeground='#1e1e2e', font=('Microsoft YaHei', 10),
            bd=0, highlightthickness=0, activestyle='none'
        )
        scrollbar.config(command=self.mod_listbox.yview)
        self.mod_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 模组信息
        self.mod_info_label = tk.Label(frame, text='← 选择一个模组查看信息',
                                       font=('Microsoft YaHei', 9), bg='#1e1e2e',
                                       fg='#6c7086', wraplength=260, justify='left')
        self.mod_info_label.pack(fill='x', pady=(4, 6))

        self.mod_listbox.bind('<<ListboxSelect>>', self._on_mod_select)

        # 按钮行
        btn_row = tk.Frame(frame, bg='#1e1e2e')
        btn_row.pack(fill='x')

        tk.Button(
            btn_row, text='📂 加载模组', font=('Microsoft YaHei', 9, 'bold'),
            bg='#89b4fa', fg='#1e1e2e', activebackground='#74c7ec',
            bd=0, padx=6, pady=4, cursor='hand2',
            command=self._load_mod
        ).pack(side='left', fill='x', expand=True, padx=(0, 4))

        tk.Button(
            btn_row, text='🗑 删除模组', font=('Microsoft YaHei', 9, 'bold'),
            bg='#f38ba8', fg='#1e1e2e', activebackground='#eba0ac',
            bd=0, padx=6, pady=4, cursor='hand2',
            command=self._delete_mod
        ).pack(side='left', fill='x', expand=True)

        tk.Button(
            frame, text='🔄 刷新列表', font=('Microsoft YaHei', 9),
            bg='#45475a', fg='#cdd6f4', activebackground='#585b70',
            bd=0, padx=6, pady=3, cursor='hand2',
            command=self._refresh_mod_list
        ).pack(fill='x', pady=(4, 0))

    def _build_log_panel(self, parent):
        frame = tk.LabelFrame(parent, text='  运行日志  ', font=('Microsoft YaHei', 10, 'bold'),
                              bg='#1e1e2e', fg='#89b4fa', padx=8, pady=8,
                              labelanchor='n', bd=1, relief='groove')
        frame.pack(fill='both', expand=True)

        self.log_text = scrolledtext.ScrolledText(
            frame, state='disabled', bg='#181825', fg='#cdd6f4',
            font=('Consolas', 10), bd=0, wrap='word',
            insertbackground='#cdd6f4'
        )
        self.log_text.pack(fill='both', expand=True)
        self.log_text.tag_config('warn', foreground='#f9e2af')
        self.log_text.tag_config('error', foreground='#f38ba8')
        self.log_text.tag_config('ok', foreground='#a6e3a1')
        self.log_text.tag_config('mod', foreground='#89b4fa')

        tk.Button(
            frame, text='清空日志', font=('Microsoft YaHei', 9),
            bg='#45475a', fg='#cdd6f4', activebackground='#585b70',
            bd=0, padx=6, pady=3, cursor='hand2',
            command=self._clear_log
        ).pack(anchor='e', pady=(4, 0))

    # ─────────────────────────────────────────
    # Dashboard & 手柄面板
    # ─────────────────────────────────────────
    def _build_dashboard_panel(self, parent):
        frame = tk.LabelFrame(parent, text='  🌐 Web Dashboard  ', font=('Microsoft YaHei', 10, 'bold'),
                              bg='#1e1e2e', fg='#89b4fa', padx=10, pady=8,
                              labelanchor='n', bd=1, relief='groove')
        frame.pack(fill='x', pady=(8, 0))

        # Dashboard 状态
        status_row = tk.Frame(frame, bg='#1e1e2e')
        status_row.pack(fill='x', pady=(0, 6))
        self.dash_status_dot = tk.Label(status_row, text='●', font=('Microsoft YaHei', 11),
                                         bg='#1e1e2e', fg='#6c7086')
        self.dash_status_dot.pack(side='left')
        self.dash_status_label = tk.Label(status_row, text='检测中...', font=('Microsoft YaHei', 9),
                                           bg='#1e1e2e', fg='#6c7086')
        self.dash_status_label.pack(side='left', padx=(4, 0))

        # 快捷按钮
        btn_frame = tk.Frame(frame, bg='#1e1e2e')
        btn_frame.pack(fill='x', pady=(0, 6))

        tk.Button(
            btn_frame, text='🎮 手柄设置', font=('Microsoft YaHei', 9, 'bold'),
            bg='#313244', fg='#89b4fa', activebackground='#45475a',
            bd=1, relief='groove', padx=6, pady=4, cursor='hand2',
            command=lambda: self._open_browser('http://localhost:8080/gamepad-settings')
        ).pack(side='left', fill='x', expand=True, padx=(0, 3))

        tk.Button(
            btn_frame, text='📝 模组编辑器', font=('Microsoft YaHei', 9, 'bold'),
            bg='#313244', fg='#89b4fa', activebackground='#45475a',
            bd=1, relief='groove', padx=6, pady=4, cursor='hand2',
            command=lambda: self._open_browser('http://localhost:8080/mod-editor')
        ).pack(side='left', fill='x', expand=True, padx=(3, 0))

        tk.Button(
            frame, text='🏠 打开 Dashboard', font=('Microsoft YaHei', 9),
            bg='#313244', fg='#cdd6f4', activebackground='#45475a',
            bd=1, relief='groove', padx=6, pady=4, cursor='hand2',
            command=lambda: self._open_browser('http://localhost:8080/')
        ).pack(fill='x', pady=(0, 6))

        # 手柄状态（如果 pygame 可用）
        self._gamepad_status_label = tk.Label(frame, text='🎮 本地手柄：未检测',
                                              font=('Microsoft YaHei', 9), bg='#1e1e2e',
                                              fg='#6c7086')
        self._gamepad_status_label.pack(fill='x')

        # 启动检测（延迟到 UI 构建完再执行，避免 log_text 未初始化）
        self._dash_url = 'http://localhost:8080'
        self.after(500, self._check_dashboard_status)
        self.after(500, self._start_gamepad_detection)

    def _open_browser(self, url: str):
        import webbrowser
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        self._log(f'🌐 已在浏览器打开：{url}', 'ok')

    def _check_dashboard_status(self):
        """每隔 3 秒在后台线程检测 Dashboard 是否可访问，避免阻塞 UI"""
        def check():
            try:
                req = urllib.request.urlopen(self._dash_url, timeout=2)
                alive = True
            except Exception:
                alive = False
            # 用 after 切回主线程更新 UI
            self.after(0, lambda: self._update_dash_ui(alive))

        threading.Thread(target=check, daemon=True).start()
        self.after(3000, self._check_dashboard_status)

    def _update_dash_ui(self, alive):
        if alive:
            self.dash_status_dot.config(fg='#a6e3a1')
            self.dash_status_label.config(text='Dashboard 在线', fg='#a6e3a1')
        else:
            self.dash_status_dot.config(fg='#f38ba8')
            self.dash_status_label.config(text='Dashboard 离线', fg='#f38ba8')

    def _start_gamepad_detection(self):
        """尝试用 pygame 检测本地手柄（可选依赖）"""
        try:
            import pygame
            self._pygame_available = True
            pygame.init()
            pygame.joystick.init()
        except ImportError:
            self._pygame_available = False
            self._gamepad_status_label.config(text='🎮 本地手柄：pygame 未安装')
            return

        def poll_gamepads():
            if not getattr(self, '_pygame_available', False):
                return
            try:
                import pygame
                pygame.joystick.quit()
                pygame.joystick.init()
                count = pygame.joystick.get_count()
                if count > 0:
                    names = []
                    for i in range(count):
                        j = pygame.joystick.Joystick(i)
                        # pygame 2.4+ 不需要显式调用 init()
                        names.append(f'{j.get_name()} ({j.get_numaxes()}轴 {j.get_numbuttons()}键)')
                    self._gamepad_status_label.config(
                        text='🎮 已连接：' + ' | '.join(names), fg='#a6e3a1'
                    )
                else:
                    self._gamepad_status_label.config(
                        text='🎮 本地手柄：未连接', fg='#6c7086'
                    )
            except Exception as e:
                self._gamepad_status_label.config(
                    text=f'🎮 检测出错：{e}', fg='#f9e2af'
                )
            self.after(2000, poll_gamepads)

        poll_gamepads()

    # ─────────────────────────────────────────
    # Bot 控制
    # ─────────────────────────────────────────
    def _start_bot(self):
        global bot_process
        if bot_process and bot_process.poll() is None:
            self._log('⚠️ 机器人已在运行中', 'warn')
            return

        main_py = os.path.join(BASE_DIR, 'main.py')
        if not os.path.exists(main_py):
            messagebox.showerror('错误', f'找不到 main.py：{main_py}')
            return

        python_exe = sys.executable
        # 设置 PYTHONIOENCODING=utf-8 强制子进程用 UTF-8 输出
        # 否则 Windows 中文系统默认 GBK 编码会导致日志乱码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        try:
            bot_process = subprocess.Popen(
                [python_exe, '-u', main_py],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                cwd=BASE_DIR, bufsize=1, env=env
            )
            self._log(f'✅ 机器人已启动（PID {bot_process.pid}）', 'ok')
            self.btn_start.config(state='disabled')
            self.btn_stop.config(state='normal')
            self.status_label.config(text='● 运行中', fg='#a6e3a1')

            # 启动日志读取线程
            t = threading.Thread(target=self._read_bot_output, daemon=True)
            t.start()

            # 启动进程监控
            threading.Thread(target=self._watch_bot_process, daemon=True).start()
        except Exception as e:
            messagebox.showerror('启动失败', str(e))

    def _stop_bot(self):
        global bot_process
        if bot_process and bot_process.poll() is None:
            bot_process.terminate()
            self._log('■ 正在停止机器人...', 'warn')
        else:
            self._log('⚠️ 机器人未在运行', 'warn')

    def _read_bot_output(self):
        global bot_process
        try:
            for line in bot_process.stdout:
                log_queue.put(line.rstrip())
        except Exception:
            pass

    def _watch_bot_process(self):
        global bot_process
        bot_process.wait()
        code = bot_process.returncode
        log_queue.put(f'[PROCESS] 机器人已退出（返回码 {code}）')
        self.after(0, self._on_bot_stopped)

    def _on_bot_stopped(self):
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.status_label.config(text='● 未运行', fg='#f38ba8')

    # ─────────────────────────────────────────
    # 模组管理
    # ─────────────────────────────────────────
    def _refresh_mod_list(self):
        self.mod_listbox.delete(0, 'end')
        self._mod_data = get_mod_list()
        if self._mod_data:
            for m in self._mod_data:
                self.mod_listbox.insert('end', f'  📦 {m["name"]}  v{m["version"]}')
        else:
            self.mod_listbox.insert('end', '  （暂无模组）')
        self.mod_info_label.config(text='← 选择一个模组查看信息')

    def _on_mod_select(self, event):
        sel = self.mod_listbox.curselection()
        if not sel or not hasattr(self, '_mod_data') or not self._mod_data:
            return
        idx = sel[0]
        if idx >= len(self._mod_data):
            return
        m = self._mod_data[idx]
        info = f'📄 {m["filename"]}\n名称：{m["name"]}\n版本：{m["version"]}'
        if m['desc']:
            info += f'\n说明：{m["desc"]}'
        self.mod_info_label.config(text=info)

    def _load_mod(self):
        """选择 .fsbods 文件并复制到 mods/ 目录"""
        path = filedialog.askopenfilename(
            title='选择模组文件',
            filetypes=[('FSBot 模组', '*.fsbods'), ('所有文件', '*.*')]
        )
        if not path:
            return
        fname = os.path.basename(path)
        dest = os.path.join(MODS_DIR, fname)
        if os.path.exists(dest):
            if not messagebox.askyesno('确认覆盖', f'模组 "{fname}" 已存在，是否覆盖？'):
                return
        try:
            # 先校验格式
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if 'name' not in data:
                messagebox.showerror('格式错误', '模组文件缺少必填字段 "name"')
                return
            shutil.copy2(path, dest)
            self._log(f'📦 模组 "{fname}" 已加载到 mods/ 目录', 'mod')
            if bot_process and bot_process.poll() is None:
                self._log('💡 机器人正在运行中，新模组将在下次重启时生效\n   （或使用 /uploadmods 命令热加载）', 'warn')
            self._refresh_mod_list()
        except json.JSONDecodeError as e:
            messagebox.showerror('解析失败', f'文件不是有效的 JSON 格式：\n{e}')
        except Exception as e:
            messagebox.showerror('加载失败', str(e))

    def _delete_mod(self):
        """从 mods/ 目录删除选中的模组文件"""
        sel = self.mod_listbox.curselection()
        if not sel or not hasattr(self, '_mod_data') or not self._mod_data:
            messagebox.showwarning('提示', '请先选择一个模组')
            return
        idx = sel[0]
        if idx >= len(self._mod_data):
            return
        m = self._mod_data[idx]
        if not messagebox.askyesno('确认删除', f'确定要删除模组 "{m["name"]}" ({m["filename"]}) 吗？\n\n此操作会从 mods/ 目录中删除文件，不可恢复。'):
            return
        try:
            os.remove(m['path'])
            self._log(f'🗑 模组 "{m["name"]}" 已从 mods/ 目录删除', 'warn')
            if bot_process and bot_process.poll() is None:
                self._log('💡 机器人正在运行中，已删除的模组将在下次重启时移除\n   （或使用 Discord 命令卸载）', 'warn')
            self._refresh_mod_list()
        except Exception as e:
            messagebox.showerror('删除失败', str(e))

    # ─────────────────────────────────────────
    # 日志
    # ─────────────────────────────────────────
    def _log(self, text: str, tag: str = ''):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {text}\n'
        self.log_text.config(state='normal')
        self.log_text.insert('end', line, tag)
        self.log_text.see('end')
        self.log_text.config(state='disabled')

    def _clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')

    def _poll_log(self):
        """每 200ms 从队列取日志行更新 UI，每次最多处理 20 行"""
        try:
            for _ in range(20):
                line = log_queue.get_nowait()
                # 简单着色
                if '错误' in line or 'ERROR' in line or 'Error' in line or 'error' in line:
                    tag = 'error'
                elif '⚠️' in line or 'WARN' in line or 'warn' in line:
                    tag = 'warn'
                elif '成功' in line or 'OK' in line or '✅' in line or '已启动' in line:
                    tag = 'ok'
                elif '[MOD]' in line:
                    tag = 'mod'
                else:
                    tag = ''
                self._log(line, tag)
        except queue.Empty:
            pass
        self.after(200, self._poll_log)

    def on_close(self):
        global bot_process
        if bot_process and bot_process.poll() is None:
            if messagebox.askyesno('退出确认', '机器人正在运行，关闭窗口会停止机器人。\n确定要退出吗？'):
                bot_process.terminate()
                self.destroy()
        else:
            self.destroy()


if __name__ == '__main__':
    app = FSBotGUI()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()
