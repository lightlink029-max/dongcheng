import json
import os
import queue
import sys
import threading
import time
import winreg
from pathlib import Path

if getattr(sys, "frozen", False):
    runtime = Path(sys.executable).parent / "_internal"
    os.environ["TCL_LIBRARY"] = str(runtime / "_tcl_data")
    os.environ["TK_LIBRARY"] = str(runtime / "_tk_data")

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from douyin_adapter import capture_login, has_login, self_test
from worker import Worker


APP_NAME = "LightLinkMediaWorker"
APP_TITLE = "LightLink 本地媒体生产工具"


def app_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


CONFIG_PATH = app_dir() / "config.json"


class MediaWorkerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x700")
        self.minsize(860, 580)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.vars = {}
        self._build()
        self._load()
        self.after(200, self._drain_events)

    def _build(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        config_tab, tasks_tab, log_tab = ttk.Frame(notebook), ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(config_tab, text="连接与配置")
        notebook.add(tasks_tab, text="任务列表")
        notebook.add(log_tab, text="运行日志")

        fields = [
            ("odoo_url", "Odoo地址", "https://lightlink029-max-dongcheng.odoo.com"),
            ("worker_token", "工作节点令牌", ""),
            ("worker_id", "工作节点名称", os.environ.get("COMPUTERNAME", "media-pc-01")),
            ("work_dir", "工作目录", str(app_dir() / "jobs")),
            ("poll_seconds", "轮询间隔（秒）", "10"),
            ("download_proxy", "下载代理（可选）", ""),
            ("ollama_url", "Ollama地址", "http://127.0.0.1:11434"),
            ("translation_model", "本地翻译模型", "qwen3:8b"),
            ("font_file", "字幕字体", "C:/Windows/Fonts/msyh.ttc"),
        ]
        form = ttk.Frame(config_tab, padding=20)
        form.pack(fill="x")
        for row, (key, label, default) in enumerate(fields):
            ttk.Label(form, text=label, width=20).grid(row=row, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=default); self.vars[key] = var
            show = "*" if key == "worker_token" else ""
            ttk.Entry(form, textvariable=var, show=show).grid(row=row, column=1, sticky="ew", pady=7)
            if key == "work_dir":
                ttk.Button(form, text="选择", command=self._choose_dir).grid(row=row, column=2, padx=8)
        form.columnconfigure(1, weight=1)
        self.autostart = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="登录Windows后自动启动并开始工作", variable=self.autostart).grid(
            row=len(fields), column=1, sticky="w", pady=8)
        login_row = len(fields) + 1
        ttk.Label(form, text="抖音登录", width=20).grid(row=login_row, column=0, sticky="w", pady=7)
        self.douyin_status = tk.StringVar(value="未登录")
        ttk.Label(form, textvariable=self.douyin_status).grid(row=login_row, column=1, sticky="w", pady=7)
        self.douyin_login_button = ttk.Button(
            form, text="登录/更新抖音登录", command=self.login_douyin,
        )
        self.douyin_login_button.grid(row=login_row, column=2, padx=8)
        controls = ttk.Frame(config_tab, padding=(20, 5))
        controls.pack(fill="x")
        ttk.Button(controls, text="保存配置", command=self.save).pack(side="left", padx=4)
        ttk.Button(controls, text="测试Odoo连接", command=self.test_connection).pack(side="left", padx=4)
        self.start_button = ttk.Button(controls, text="启动工作节点", command=self.start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(controls, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        self.status = tk.StringVar(value="已停止")
        ttk.Label(controls, textvariable=self.status).pack(side="right")

        columns = ("id", "type", "language", "status", "result")
        self.task_tree = ttk.Treeview(tasks_tab, columns=columns, show="headings")
        for col, title, width in zip(columns, ("任务ID", "类型", "语种", "状态", "结果/错误"), (80, 130, 140, 120, 480)):
            self.task_tree.heading(col, text=title); self.task_tree.column(col, width=width, anchor="w")
        self.task_tree.pack(fill="both", expand=True, padx=10, pady=10)

        self.log = tk.Text(log_tab, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def _choose_dir(self):
        value = filedialog.askdirectory(initialdir=self.vars["work_dir"].get())
        if value: self.vars["work_dir"].set(value)

    def config(self):
        return {
            "odoo_url": self.vars["odoo_url"].get().strip(),
            "worker_token": self.vars["worker_token"].get().strip(),
            "worker_id": self.vars["worker_id"].get().strip(),
            "work_dir": self.vars["work_dir"].get().strip(),
            "poll_seconds": int(self.vars["poll_seconds"].get() or 10),
            "download_proxy": self.vars["download_proxy"].get().strip(),
            "douyin_cookie_store": str(app_dir() / "secrets.json"),
            "font_file": self.vars["font_file"].get().strip(),
            "local_ai": {"ollama_url": self.vars["ollama_url"].get().strip(),
                         "translation_model": self.vars["translation_model"].get().strip()},
        }

    def save(self, quiet=False):
        try:
            data = self.config()
            if not data["odoo_url"].startswith("https://"):
                raise ValueError("Odoo地址必须使用 https://")
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._set_autostart(self.autostart.get())
            if not quiet: messagebox.showinfo(APP_TITLE, "配置已保存")
            return True
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return False

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                flat = dict(data); flat.update(data.get("local_ai", {}))
                for key, var in self.vars.items():
                    if key in flat: var.set(str(flat[key]))
            except Exception as exc: self.write_log("配置读取失败：" + str(exc))
        self.autostart.set(self._autostart_enabled())
        self._refresh_douyin_status()
        if "--autostart" in sys.argv:
            self.after(1000, self.start)

    def _refresh_douyin_status(self):
        self.douyin_status.set("已登录" if has_login(app_dir() / "secrets.json") else "未登录")

    def login_douyin(self):
        self.douyin_login_button.config(state="disabled")
        self.douyin_status.set("等待登录…")

        def run():
            try:
                count = capture_login(
                    app_dir() / "secrets.json",
                    self.vars["download_proxy"].get().strip(),
                    status_callback=lambda message: self.events.put(("log", {"message": message})),
                )
                self.events.put(("douyin_login", {"ok": True, "count": count}))
            except Exception as exc:
                self.events.put(("douyin_login", {"ok": False, "error": str(exc)}))

        threading.Thread(target=run, daemon=True).start()

    def _command(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --autostart'
        return f'"{sys.executable}" "{Path(__file__).resolve()}" --autostart'

    def _set_autostart(self, enabled):
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            if enabled: winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, self._command())
            else:
                try: winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError: pass
        finally: winreg.CloseKey(key)

    def _autostart_enabled(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
            try: winreg.QueryValueEx(key, APP_NAME); return True
            finally: winreg.CloseKey(key)
        except FileNotFoundError: return False

    def test_connection(self):
        if not self.save(quiet=True): return
        def run():
            try:
                result = Worker(self.config()).health()
                self.events.put(("connection", {"ok": bool(result.get("ok"))}))
            except Exception as exc: self.events.put(("connection", {"ok": False, "error": str(exc)}))
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive(): return
        if not self.save(quiet=True): return
        if not self.vars["worker_token"].get().strip():
            messagebox.showerror(APP_TITLE, "请填写Odoo工作节点令牌"); return
        self.stop_event.clear(); self.status.set("运行中")
        self.start_button.config(state="disabled"); self.stop_button.config(state="normal")
        self.worker_thread = threading.Thread(target=self._work_loop, daemon=True); self.worker_thread.start()

    def stop(self):
        self.stop_event.set(); self.status.set("正在停止…")

    def _work_loop(self):
        worker = Worker(self.config(), lambda event, data: self.events.put((event, data)))
        delay = max(3, int(self.config().get("poll_seconds", 10)))
        self.events.put(("log", {"message": "工作节点已启动"}))
        while not self.stop_event.is_set():
            try:
                task = worker.claim()
                if task: worker.process(task)
                else: self.stop_event.wait(delay)
            except Exception as exc:
                self.events.put(("log", {"message": "任务错误：" + str(exc)})); self.stop_event.wait(delay)
        self.events.put(("stopped", {}))

    def _drain_events(self):
        try:
            while True:
                event, data = self.events.get_nowait()
                if event == "log": self.write_log(data["message"])
                elif event == "connection":
                    messagebox.showinfo(APP_TITLE, "Odoo连接成功") if data["ok"] else messagebox.showerror(APP_TITLE, data.get("error") or "Odoo连接失败")
                elif event == "douyin_login":
                    self.douyin_login_button.config(state="normal")
                    self._refresh_douyin_status()
                    if data["ok"]:
                        messagebox.showinfo(APP_TITLE, "抖音登录成功，登录信息已在本机加密保存")
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "抖音登录失败")
                elif event.startswith("task_"): self._task_event(event, data)
                elif event == "stopped":
                    self.status.set("已停止"); self.start_button.config(state="normal"); self.stop_button.config(state="disabled")
        except queue.Empty: pass
        self.after(200, self._drain_events)

    def _task_event(self, event, data):
        task = data["task"]; iid = str(task["id"])
        status = {"task_started": "处理中", "task_done": "已完成", "task_failed": "失败"}[event]
        result = data.get("output") or data.get("error") or ""
        values = (task["id"], task["type"], task["target_language"], status, result)
        if self.task_tree.exists(iid): self.task_tree.item(iid, values=values)
        else: self.task_tree.insert("", 0, iid=iid, values=values)
        self.write_log(f"任务 {task['id']}：{status} {result}")

    def write_log(self, message):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n"
        self.log.config(state="normal"); self.log.insert("end", line); self.log.see("end"); self.log.config(state="disabled")
        with (app_dir() / "worker.log").open("a", encoding="utf-8") as stream: stream.write(line)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    MediaWorkerApp().mainloop()
