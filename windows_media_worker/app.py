import base64
import json
import os
import queue
import secrets
import shutil
import subprocess
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
from PIL import Image, ImageTk

from douyin_adapter import _dpapi, capture_login, has_login, open_keyword_search, self_test
from mumu_adapter import MumuBridge, check_mumu, install_selector_apk
from selection_store import SelectionStore
from selector_bridge import SelectorBridge
from speech import windows_voices
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
        self.worker = None
        self.pending_selections = {}
        self.selection_store = SelectionStore(app_dir() / "selections.db")
        self.selector_token = secrets.token_urlsafe(24)
        self.selector_bridge = SelectorBridge(
            self.selection_store, self.selector_token,
            lambda task_id, added: self.events.put((
                "selector_submission", {"task_id": task_id, "added": added},
            )),
        )
        self.selector_bridge.start()
        self.selection_task_id = None
        self.selection_busy = False
        self.last_clipboard = ""
        self.vars = {}
        self._build()
        self._load()
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self.after(200, self._drain_events)
        self.after(800, self._poll_clipboard)

    def _build(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        config_tab, tasks_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        selection_tab, log_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(config_tab, text="连接与配置")
        notebook.add(tasks_tab, text="任务列表")
        notebook.add(selection_tab, text="抖音选片与混剪")
        notebook.add(log_tab, text="运行日志")
        self.notebook = notebook
        self.selection_tab = selection_tab

        fields = [
            ("odoo_url", "Odoo地址", "https://lightlink029-max-dongcheng.odoo.com"),
            ("worker_token", "工作节点令牌", ""),
            ("worker_id", "工作节点名称", os.environ.get("COMPUTERNAME", "media-pc-01")),
            ("work_dir", "工作目录", str(app_dir() / "jobs")),
            ("poll_seconds", "轮询间隔（秒）", "10"),
            ("download_proxy", "下载代理（可选）", ""),
            ("ollama_url", "Ollama地址", "http://127.0.0.1:11434"),
            ("translation_model", "本地翻译模型", "qwen3:8b"),
            ("whisper_command", "语音识别程序（可选）", ""),
            ("whisper_model", "Whisper模型", "small"),
            ("ai_edit_command", "AI剪辑程序（可选）", ""),
            ("sherpa_command", "sherpa-onnx程序（可选）", ""),
            ("sherpa_model", "sherpa音色模型", ""),
            ("sherpa_tokens", "sherpa Tokens", ""),
            ("sherpa_data_dir", "sherpa数据目录", ""),
            ("volc_app_id", "火山引擎 App ID", ""),
            ("volc_token", "火山引擎 Access Token", ""),
            ("volc_cluster", "火山引擎 Cluster", "volcano_tts"),
            ("font_file", "字幕字体", "C:/Windows/Fonts/msyh.ttc"),
            ("mumu_adb", "MuMu ADB（可自动检测）", ""),
            ("mumu_player", "MuMu 主程序（可自动检测）", ""),
            ("mumu_serial", "MuMu ADB 地址（留空自动检测）", ""),
        ]
        form = ttk.Frame(config_tab, padding=20)
        form.pack(fill="x")
        half = (len(fields) + 1) // 2
        for index, (key, label, default) in enumerate(fields):
            row, base_column = index % half, (index // half) * 3
            ttk.Label(form, text=label, width=20).grid(row=row, column=base_column, sticky="w", pady=7)
            var = tk.StringVar(value=default); self.vars[key] = var
            show = "*" if key in ("worker_token", "volc_token") else ""
            ttk.Entry(form, textvariable=var, show=show).grid(row=row, column=base_column + 1, sticky="ew", pady=7)
            if key == "work_dir":
                ttk.Button(form, text="选择", command=self._choose_dir).grid(row=row, column=base_column + 2, padx=8)
            elif key in ("mumu_adb", "mumu_player"):
                ttk.Button(form, text="选择", command=lambda name=key: self._choose_exe(name)).grid(row=row, column=base_column + 2, padx=8)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(4, weight=1)
        self.autostart = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="登录Windows后自动启动并开始工作", variable=self.autostart).grid(
            row=half, column=1, columnspan=4, sticky="w", pady=8)
        login_row = half + 1
        ttk.Label(form, text="抖音登录", width=20).grid(row=login_row, column=0, sticky="w", pady=7)
        self.douyin_status = tk.StringVar(value="未登录")
        ttk.Label(form, textvariable=self.douyin_status).grid(row=login_row, column=1, columnspan=4, sticky="w", pady=7)
        self.douyin_login_button = ttk.Button(
            form, text="登录/更新抖音登录", command=self.login_douyin,
        )
        self.douyin_login_button.grid(row=login_row, column=2, padx=8)
        controls = ttk.Frame(config_tab, padding=(20, 5))
        controls.pack(fill="x")
        ttk.Button(controls, text="保存配置", command=self.save).pack(side="left", padx=4)
        ttk.Button(controls, text="测试Odoo连接", command=self.test_connection).pack(side="left", padx=4)
        ttk.Button(controls, text="检测MuMu", command=self.test_mumu).pack(side="left", padx=4)
        ttk.Button(controls, text="安装/更新选片APK", command=self.install_selector).pack(side="left", padx=4)
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
        self.task_tree.bind("<<TreeviewSelect>>", self._on_task_selected)
        task_controls = ttk.Frame(tasks_tab, padding=(10, 0, 10, 10))
        task_controls.pack(fill="x")
        ttk.Button(task_controls, text="打开选片管理", command=self.open_selection_manager).pack(side="left")
        ttk.Label(task_controls, text="选片明细和处理状态仅保存在本机，Odoo只接收最终成片。", foreground="#666").pack(side="left", padx=12)

        selection_header = ttk.Frame(selection_tab, padding=10)
        selection_header.pack(fill="x")
        self.selection_title = tk.StringVar(value="请先启动工作节点并领取抖音选片任务")
        ttk.Label(selection_header, textvariable=self.selection_title, font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        ttk.Button(selection_header, text="新建本地项目", command=self.create_local_project).pack(side="left", padx=(15, 3))
        ttk.Button(selection_header, text="编辑处理设置", command=self.edit_active_project).pack(side="left", padx=3)
        self.selection_task_choice = ttk.Combobox(selection_header, state="readonly", width=34)
        self.selection_task_choice.pack(side="left", padx=8)
        self.selection_task_choice.bind("<<ComboboxSelected>>", self._on_selection_task_choice)
        self.clipboard_listening = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            selection_header, text="自动收集剪贴板中的抖音链接", variable=self.clipboard_listening,
        ).pack(side="right")
        ttk.Label(
            selection_tab,
            text="可独立新建项目，也可领取 Odoo 任务。先下载并预览素材，再生成审核稿；确认满意后才回传 Odoo。",
        ).pack(fill="x", padx=10, pady=(0, 8))

        selection_columns = ("video_id", "selected_at", "status", "trim", "copyright", "url", "error")
        self.selection_tree = ttk.Treeview(
            selection_tab, columns=selection_columns, show="headings", selectmode="extended",
        )
        titles = ("视频ID", "选择时间", "处理状态", "入点-出点", "版权", "分享链接", "错误")
        widths = (140, 160, 100, 110, 100, 360, 220)
        for column, title, width in zip(selection_columns, titles, widths):
            self.selection_tree.heading(column, text=title)
            self.selection_tree.column(column, width=width, anchor="w")
        self.selection_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.selection_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_selection_summary())
        self.selection_tree.bind("<Double-1>", lambda _event: self.preview_selected_video())

        selection_controls = ttk.Frame(selection_tab, padding=(10, 0, 10, 10))
        selection_controls.pack(fill="x")
        ttk.Button(selection_controls, text="全选", command=self.select_all_videos).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="从剪贴板添加", command=self.add_selection_from_clipboard).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="手工添加链接", command=self.add_selection_manually).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="添加本地视频", command=self.add_local_videos).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="时间轴/版权", command=self.edit_selected_clip).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="删除所选", command=self.delete_selected_videos).pack(side="left", padx=3)
        ttk.Button(selection_controls, text="重新下载", command=self.redownload_selected_videos).pack(side="left", padx=3)
        self.selection_summary = tk.StringVar(value="0 条")
        ttk.Label(selection_controls, textvariable=self.selection_summary).pack(side="right")
        review_controls = ttk.Frame(selection_tab, padding=(10, 0, 10, 10))
        review_controls.pack(fill="x")
        ttk.Button(review_controls, text="① 预览所选素材", command=self.preview_selected_video).pack(side="left", padx=3)
        ttk.Button(review_controls, text="② 生成审核稿", command=self.mix_selected_videos).pack(side="left", padx=3)
        ttk.Button(review_controls, text="③ 预览成片", command=self.preview_result).pack(side="left", padx=3)
        ttk.Button(review_controls, text="历史版本", command=self.show_versions).pack(side="left", padx=3)
        ttk.Button(review_controls, text="④ 确认回传 Odoo", command=self.upload_result).pack(side="left", padx=3)
        ttk.Button(review_controls, text="打开项目目录", command=self.open_project_folder).pack(side="left", padx=3)
        ttk.Button(review_controls, text="删除本地项目", command=self.delete_local_project).pack(side="left", padx=3)
        ttk.Label(review_controls, text="独立本地项目停在第③步，成片不会自动上传。", foreground="#666").pack(side="right")

        self.log = tk.Text(log_tab, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def _choose_dir(self):
        value = filedialog.askdirectory(initialdir=self.vars["work_dir"].get())
        if value: self.vars["work_dir"].set(value)

    def _choose_exe(self, key):
        value = filedialog.askopenfilename(filetypes=[("Windows 程序", "*.exe"), ("所有文件", "*.*")])
        if value: self.vars[key].set(value)

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
            "mumu_adb": self.vars["mumu_adb"].get().strip(),
            "mumu_player": self.vars["mumu_player"].get().strip(),
            "mumu_serial": self.vars["mumu_serial"].get().strip(),
            "selector_port": self.selector_bridge.port,
            "selector_token": self.selector_token,
            "local_ai": {"ollama_url": self.vars["ollama_url"].get().strip(),
                         "translation_model": self.vars["translation_model"].get().strip(),
                         "whisper_command": self.vars["whisper_command"].get().strip(),
                         "whisper_model": self.vars["whisper_model"].get().strip(),
                         "ai_edit_command": self.vars["ai_edit_command"].get().strip()},
            "speech": {
                "sherpa_command": self.vars["sherpa_command"].get().strip(),
                "sherpa_model": self.vars["sherpa_model"].get().strip(),
                "sherpa_tokens": self.vars["sherpa_tokens"].get().strip(),
                "sherpa_data_dir": self.vars["sherpa_data_dir"].get().strip(),
                "volc_app_id": self.vars["volc_app_id"].get().strip(),
                "volc_token": self.vars["volc_token"].get().strip(),
                "volc_cluster": self.vars["volc_cluster"].get().strip(),
            },
        }

    def save(self, quiet=False):
        try:
            data = self.config()
            if not data["odoo_url"].startswith("https://"):
                raise ValueError("Odoo地址必须使用 https://")
            persisted = dict(data)
            persisted.pop("selector_port", None)
            persisted.pop("selector_token", None)
            speech = dict(persisted.get("speech", {}))
            token = speech.pop("volc_token", "")
            if token:
                speech["volc_token_dpapi"] = base64.b64encode(
                    _dpapi(token.encode("utf-8"), True)
                ).decode("ascii")
            persisted["speech"] = speech
            CONFIG_PATH.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")
            self._set_autostart(self.autostart.get())
            if not quiet: messagebox.showinfo(APP_TITLE, "配置已保存")
            return True
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return False

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
                speech = dict(data.get("speech", {}))
                encrypted = speech.get("volc_token_dpapi")
                if encrypted:
                    speech["volc_token"] = _dpapi(base64.b64decode(encrypted), False).decode("utf-8")
                flat = dict(data); flat.update(data.get("local_ai", {})); flat.update(speech)
                for key, var in self.vars.items():
                    if key in flat: var.set(str(flat[key]))
            except Exception as exc: self.write_log("配置读取失败：" + str(exc))
        self.autostart.set(self._autostart_enabled())
        self._refresh_douyin_status()
        self._refresh_selection_tasks()
        self._refresh_selection_tree()
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

    def test_mumu(self):
        if not self.save(quiet=True): return
        def run():
            try:
                result = check_mumu(self.config())
                self.events.put(("mumu", {"ok": True, "result": result}))
            except Exception as exc:
                self.events.put(("mumu", {"ok": False, "error": str(exc)}))
        threading.Thread(target=run, daemon=True).start()

    def install_selector(self):
        if not self.save(quiet=True): return
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        apk = base / "LightLinkSelector.apk" if getattr(sys, "frozen", False) else base / "android_selector" / "release" / "LightLinkSelector.apk"
        def run():
            try:
                result = install_selector_apk(self.config(), apk)
                self.events.put(("selector_installed", {"ok": True, "result": result}))
            except Exception as exc:
                self.events.put(("selector_installed", {"ok": False, "error": str(exc)}))
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
        self.worker = worker
        delay = max(3, int(self.config().get("poll_seconds", 10)))
        self.events.put(("log", {"message": "工作节点已启动"}))
        while not self.stop_event.is_set():
            try:
                for task_id in list(self.pending_selections):
                    try:
                        worker.heartbeat(task_id)
                    except Exception as exc:
                        self.pending_selections.pop(task_id, None)
                        self.events.put(("log", {"message": f"选片任务 {task_id} 已失效：{exc}"}))
                if self.pending_selections:
                    self.stop_event.wait(delay)
                    continue
                task = worker.claim()
                if task and task["type"] == "douyin_select":
                    try:
                        worker.prepare_douyin_selection(task)
                        self.pending_selections[task["id"]] = task
                    except Exception as exc:
                        worker.fail_task(task, exc)
                elif task: worker.process(task)
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
                elif event == "mumu":
                    if data["ok"]:
                        result = data["result"]
                        messagebox.showinfo(APP_TITLE, "MuMu连接成功\nADB：%s\n设备：%s" % (result["adb"], result["serial"]))
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "MuMu连接失败")
                elif event == "selector_installed":
                    if data["ok"]:
                        messagebox.showinfo(APP_TITLE, "LightLink 选片 APK 已安装/更新到 MuMu")
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "选片 APK 安装失败")
                elif event == "selection_complete":
                    task = data["task"]
                    self.pending_selections.pop(task["id"], None)
                    self._task_event("task_done", {"task": task, "output": "已同步 %s 条视频链接" % data["saved"]})
                elif event == "selection_changed":
                    self._refresh_selection_tree()
                elif event == "selector_submission":
                    self.selection_task_id = data["task_id"]
                    self._refresh_selection_tasks()
                    self._refresh_selection_tree()
                    self.write_log(
                        "任务 %s：APK 提交选片，新增 %s 条" %
                        (data["task_id"], data["added"])
                    )
                elif event == "selection_mix_ready":
                    task = data["task"]
                    self.selection_busy = False
                    self._refresh_selection_tasks()
                    self._refresh_selection_tree()
                    messagebox.showinfo(APP_TITLE, "审核稿已生成。请先预览成片，确认满意后再回传 Odoo。")
                elif event == "selection_upload_done":
                    task = data["task"]
                    self.pending_selections.pop(task["id"], None)
                    self.selection_store.set_task_status(task["id"], "done")
                    self.selection_busy = False
                    self._refresh_selection_tasks()
                    self._refresh_selection_tree()
                    self._task_event("task_done", {"task": task, "output": "成片已回传 Odoo：%s" % data["output"]})
                    messagebox.showinfo(APP_TITLE, "成片已确认并回传 Odoo")
                elif event == "selection_operation_done":
                    self.selection_busy = False
                    self._refresh_selection_tree()
                elif event == "selection_operation_error":
                    self.selection_busy = False
                    self._refresh_selection_tree()
                    messagebox.showerror(APP_TITLE, data.get("error") or "选片处理失败")
                elif event == "selection_submit_error":
                    messagebox.showerror(APP_TITLE, data.get("error") or "选片链接同步失败")
                elif event.startswith("task_"): self._task_event(event, data)
                elif event == "selection_pending": self._task_event(event, data)
                elif event == "stopped":
                    self.status.set("已停止"); self.start_button.config(state="normal"); self.stop_button.config(state="disabled")
        except queue.Empty: pass
        self.after(200, self._drain_events)

    def _task_event(self, event, data):
        task = data["task"]; iid = str(task["id"])
        status = {"task_started": "处理中", "task_done": "已完成", "task_failed": "失败", "selection_pending": "等待人工选片"}[event]
        result = data.get("output") or data.get("error") or ""
        values = (task["id"], task["type"], task["target_language"], status, result)
        if self.task_tree.exists(iid): self.task_tree.item(iid, values=values)
        else: self.task_tree.insert("", 0, iid=iid, values=values)
        if event == "selection_pending":
            self.selection_task_id = task["id"]
            self.selection_store.save_task(task)
            self._refresh_selection_tasks()
            self._refresh_selection_tree()
        self.write_log(f"任务 {task['id']}：{status} {result}")

    def _on_task_selected(self, _event=None):
        selected = self.task_tree.selection()
        if len(selected) == 1 and int(selected[0]) in self.pending_selections:
            self.selection_task_id = int(selected[0])
            self._refresh_selection_tree()

    def _on_selection_task_choice(self, _event=None):
        value = self.selection_task_choice.get().split(" · ", 1)[0]
        try:
            self.selection_task_id = int(value)
            self._refresh_selection_tree()
        except ValueError:
            pass

    def _refresh_selection_tasks(self):
        tasks = self.selection_store.list_tasks()
        labels = ["%s · %s · %s" % (
            task["id"], task.get("local_status", "processing"),
            (task.get("name") or task.get("keywords") or task.get("target_language") or "抖音选片").replace("\n", " ")[:18],
        ) for task in tasks]
        self.selection_task_choice["values"] = labels
        if tasks and self.selection_task_id is None:
            self.selection_task_id = tasks[0]["id"]
        for index, task in enumerate(tasks):
            if task["id"] == self.selection_task_id:
                self.selection_task_choice.current(index)
                break

    def open_selection_manager(self):
        self._on_task_selected()
        if not self.selection_task_id:
            messagebox.showerror(APP_TITLE, "请先领取一个抖音选片任务")
            return
        self.notebook.select(self.selection_tab)

    def _project_dialog(self, task=None):
        existing = task or {}
        edit_choices = {
            "sequence": "顺序拼接", "reverse": "倒序拼接",
            "random": "随机排序", "ai": "本地 AI 剪辑程序",
        }
        subtitle_choices = {
            "none": "不添加字幕", "script": "使用项目脚本",
            "transcribe": "识别原视频语音",
        }
        audio_choices = {"original": "保留原声", "mute": "静音"}
        tts_choices = {
            "none": "不生成配音", "windows": "Windows 本地音色",
            "sherpa": "sherpa-onnx 本地音色", "volcengine": "火山引擎音色",
        }
        preset_choices = {
            "douyin": "抖音 / TikTok 9:16", "reels": "Instagram Reels 9:16",
            "feed": "Instagram Feed 4:5", "square": "网站 / 社媒方图 1:1",
        }
        dialog = tk.Toplevel(self)
        dialog.title("编辑视频项目" if task else "新建本地视频项目")
        dialog.geometry("820x900")
        dialog.transient(self)
        form = ttk.Frame(dialog, padding=15)
        form.pack(fill="both", expand=True)

        values = {
            "name": tk.StringVar(value=existing.get("name") or "本地视频项目"),
            "keywords": tk.StringVar(value=existing.get("keywords") or ""),
            "source_language": tk.StringVar(value=existing.get("source_language") or "Chinese"),
            "target_language": tk.StringVar(value=existing.get("target_language") or "English"),
            "duration_seconds": tk.StringVar(value=str(existing.get("duration_seconds") or 15)),
            "aspect_ratio": tk.StringVar(value=existing.get("aspect_ratio") or "9:16"),
            "edit_mode": tk.StringVar(value=edit_choices.get(existing.get("edit_mode") or "sequence")),
            "subtitle_mode": tk.StringVar(value=subtitle_choices.get(existing.get("subtitle_mode") or "script")),
            "audio_mode": tk.StringVar(value=audio_choices.get(existing.get("audio_mode") or "original")),
            "export_preset": tk.StringVar(value=preset_choices.get(existing.get("export_preset") or "douyin")),
            "transition": tk.StringVar(value="淡入淡出" if existing.get("transition") == "fade" else "无转场"),
            "tts_provider": tk.StringVar(value=tts_choices.get(existing.get("tts_provider") or "none")),
            "tts_voice": tk.StringVar(value=existing.get("tts_voice") or ""),
            "tts_speed": tk.StringVar(value=str(existing.get("tts_speed") or 1.0)),
            "tts_volume": tk.StringVar(value=str(existing.get("tts_volume") or 1.0)),
            "background_music": tk.StringVar(value=existing.get("background_music") or ""),
            "music_volume": tk.StringVar(value=str(existing.get("music_volume") or 0.2)),
            "source_image_path": tk.StringVar(value=existing.get("source_image_path") or ""),
        }
        translate = tk.BooleanVar(value=bool(existing.get("translate_subtitles", False)))
        local_files = list(existing.get("local_files") or [])

        rows = (
            ("项目名称", "name", None), ("搜索关键词", "keywords", None),
            ("原视频语言", "source_language", None),
            ("目标语言", "target_language", None),
            ("成片时长（秒）", "duration_seconds", None),
            ("画面比例", "aspect_ratio", ("9:16", "4:5", "1:1")),
            ("剪辑方式", "edit_mode", tuple(edit_choices.values())),
            ("字幕来源", "subtitle_mode", tuple(subtitle_choices.values())),
            ("原视频声音", "audio_mode", tuple(audio_choices.values())),
            ("导出预设", "export_preset", tuple(preset_choices.values())),
            ("转场", "transition", ("无转场", "淡入淡出")),
            ("配音服务", "tts_provider", tuple(tts_choices.values())),
            ("音色名称/ID", "tts_voice", None),
            ("配音语速", "tts_speed", None),
            ("配音音量", "tts_volume", None),
            ("背景音乐音量", "music_volume", None),
        )
        for row, (label, key, choices) in enumerate(rows):
            ttk.Label(form, text=label, width=18).grid(row=row, column=0, sticky="w", pady=5)
            if key == "tts_voice":
                widget = ttk.Combobox(form, textvariable=values[key], values=windows_voices())
            else:
                widget = ttk.Combobox(form, textvariable=values[key], values=choices, state="readonly") if choices else ttk.Entry(form, textvariable=values[key])
            widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)

        music_row = len(rows)
        ttk.Label(form, text="背景音乐", width=18).grid(row=music_row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=values["background_music"]).grid(row=music_row, column=1, sticky="ew", pady=5)
        ttk.Button(
            form, text="选择音频",
            command=lambda: values["background_music"].set(filedialog.askopenfilename(
                parent=dialog, filetypes=[("音频", "*.mp3 *.wav *.m4a *.aac"), ("所有文件", "*.*")],
            ) or values["background_music"].get()),
        ).grid(row=music_row, column=2, padx=(8, 0))

        image_row = music_row + 1
        ttk.Label(form, text="搜索参考图片", width=18).grid(row=image_row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=values["source_image_path"]).grid(row=image_row, column=1, sticky="ew", pady=5)
        ttk.Button(
            form, text="选择图片",
            command=lambda: values["source_image_path"].set(filedialog.askopenfilename(
                parent=dialog, filetypes=[("图片", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")],
            ) or values["source_image_path"].get()),
        ).grid(row=image_row, column=2, padx=(8, 0))

        video_row = image_row + 1
        ttk.Label(form, text="本地视频", width=18).grid(row=video_row, column=0, sticky="nw", pady=5)
        local_label = tk.StringVar(value="已选择 %s 个文件" % len(local_files))
        ttk.Label(form, textvariable=local_label).grid(row=video_row, column=1, sticky="w", pady=5)
        def choose_videos():
            selected = filedialog.askopenfilenames(
                parent=dialog, filetypes=[("视频", "*.mp4 *.mov *.mkv *.webm *.avi"), ("所有文件", "*.*")],
            )
            for path in selected:
                if path not in local_files:
                    local_files.append(path)
            local_label.set("已选择 %s 个文件" % len(local_files))
        ttk.Button(form, text="添加视频", command=choose_videos).grid(row=video_row, column=2, padx=(8, 0))

        url_row = video_row + 1
        ttk.Label(form, text="抖音链接", width=18).grid(row=url_row, column=0, sticky="nw", pady=5)
        urls = tk.Text(form, height=4, wrap="word")
        urls.grid(row=url_row, column=1, columnspan=2, sticky="nsew", pady=5)
        urls.insert("1.0", "\n".join(existing.get("source_urls") or []))
        script_row = url_row + 1
        ttk.Label(form, text="字幕/项目脚本", width=18).grid(row=script_row, column=0, sticky="nw", pady=5)
        script = tk.Text(form, height=8, wrap="word")
        script.grid(row=script_row, column=1, columnspan=2, sticky="nsew", pady=5)
        script.insert("1.0", existing.get("video_script") or "")
        ttk.Checkbutton(
            form, text="将字幕翻译为目标语言（需要本地翻译模型）", variable=translate,
        ).grid(row=script_row + 1, column=1, columnspan=2, sticky="w", pady=5)
        ttk.Label(
            form,
            text="语音识别与 AI 剪辑均为可选本地程序；未配置时仍可使用脚本字幕和三种基础剪辑方式。",
            foreground="#666",
        ).grid(row=script_row + 2, column=0, columnspan=3, sticky="w", pady=5)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(script_row, weight=1)

        def save_project(open_search=False):
            try:
                duration = max(3, int(values["duration_seconds"].get()))
                preset_key = next(key for key, label in preset_choices.items() if label == values["export_preset"].get())
                preset_ratio = {"douyin": "9:16", "reels": "9:16", "feed": "4:5", "square": "1:1"}[preset_key]
                task_id = int(existing.get("id") or self.selection_store.next_local_task_id())
                image_path = values["source_image_path"].get().strip()
                if image_path:
                    source = Path(image_path).expanduser().resolve()
                    if not source.is_file():
                        raise FileNotFoundError("搜索参考图片不存在")
                    target_dir = Path(self.vars["work_dir"].get()).resolve() / "local-projects" / str(abs(task_id))
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target = target_dir / ("reference" + (source.suffix or ".jpg"))
                    if source != target:
                        shutil.copy2(source, target)
                    image_path = str(target)
                project = dict(existing)
                project.update({
                    "id": task_id, "type": existing.get("type") or "local_project",
                    "local_only": bool(existing.get("local_only", task is None)),
                    "name": values["name"].get().strip() or "本地视频项目",
                    "keywords": values["keywords"].get().strip(),
                    "source_language": values["source_language"].get().strip() or "Chinese",
                    "target_language": values["target_language"].get().strip() or "English",
                    "duration_seconds": duration, "aspect_ratio": preset_ratio,
                    "edit_mode": next(key for key, label in edit_choices.items() if label == values["edit_mode"].get()),
                    "subtitle_mode": next(key for key, label in subtitle_choices.items() if label == values["subtitle_mode"].get()),
                    "audio_mode": next(key for key, label in audio_choices.items() if label == values["audio_mode"].get()),
                    "export_preset": preset_key,
                    "transition": "fade" if values["transition"].get() == "淡入淡出" else "none",
                    "tts_provider": next(key for key, label in tts_choices.items() if label == values["tts_provider"].get()),
                    "tts_voice": values["tts_voice"].get().strip(),
                    "tts_speed": max(0.5, min(2.0, float(values["tts_speed"].get()))),
                    "tts_volume": max(0.0, min(2.0, float(values["tts_volume"].get()))),
                    "background_music": values["background_music"].get().strip(),
                    "music_volume": max(0.0, min(1.0, float(values["music_volume"].get()))),
                    "translate_subtitles": translate.get(), "video_script": script.get("1.0", "end").strip(),
                    "source_mode": "project_script", "source_image_path": image_path,
                    "source_urls": [line.strip() for line in urls.get("1.0", "end").splitlines() if line.strip()],
                    "local_files": local_files,
                })
                self.selection_store.update_task(project, status=existing.get("local_status") or "draft")
                self.selection_store.add_text(task_id, "\n".join(project["source_urls"]))
                self.selection_store.add_local_files(task_id, local_files)
                if task_id in self.pending_selections:
                    self.pending_selections[task_id] = project
                self.selection_task_id = task_id
                dialog.destroy()
                self._refresh_selection_tasks()
                self._refresh_selection_tree()
                self.notebook.select(self.selection_tab)
                if open_search:
                    self._open_project_search(project)
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        actions = ttk.Frame(form)
        actions.grid(row=script_row + 3, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="保存", command=save_project).pack(side="left", padx=4)
        ttk.Button(actions, text="保存并打开抖音搜索", command=lambda: save_project(True)).pack(side="left", padx=4)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="left", padx=4)

    def create_local_project(self):
        self._project_dialog()

    def edit_active_project(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个项目")
            return
        self._project_dialog(task)

    def _open_project_search(self, task):
        image_path = task.get("source_image_path")
        if image_path:
            def run_image_search():
                try:
                    bridge = MumuBridge(
                        self.vars["mumu_adb"].get(), self.vars["mumu_serial"].get(),
                        self.vars["mumu_player"].get(), self.selector_bridge.port, self.selector_token,
                    )
                    remote = bridge.prepare_image_search(image_path, task["id"])
                    self.events.put(("log", {"message": "本地项目 %s：图片已输入 MuMu（%s）" % (task["id"], remote)}))
                except Exception as exc:
                    self.events.put(("selection_operation_error", {"error": str(exc)}))
            threading.Thread(target=run_image_search, daemon=True).start()
            return
        keyword = (task.get("keywords") or "").strip()
        if not keyword:
            messagebox.showerror(APP_TITLE, "请先填写关键词或选择参考图片")
            return
        threading.Thread(
            target=open_keyword_search,
            args=(app_dir() / "secrets.json", keyword, self.vars["download_proxy"].get().strip()),
            daemon=True,
        ).start()

    def _active_selection_task(self):
        if self.selection_task_id in self.pending_selections:
            active = dict(self.pending_selections[self.selection_task_id])
            stored = self.selection_store.get_task(self.selection_task_id)
            if stored:
                active.update(stored)
            return active
        stored = self.selection_store.get_task(self.selection_task_id) if self.selection_task_id else None
        if stored:
            return stored
        if self.pending_selections:
            self.selection_task_id = next(iter(self.pending_selections))
            return self.pending_selections[self.selection_task_id]
        return None

    def _refresh_selection_tree(self):
        task = self._active_selection_task()
        for item in self.selection_tree.get_children():
            self.selection_tree.delete(item)
        if not task:
            self.selection_title.set("当前没有等待处理的抖音选片任务")
            self.selection_summary.set("0 条")
            return
        rows = self.selection_store.list(task["id"])
        labels = {
            "selected": "已选择", "downloading": "下载中", "downloaded": "已下载",
            "mixing": "混剪中", "ready_review": "待审核", "done": "已完成", "failed": "失败",
        }
        for row in rows:
            self.selection_tree.insert("", "end", iid=str(row["id"]), values=(
                row["video_id"] or "待下载解析", row["selected_at"].replace("T", " ")[:19],
                labels.get(row["status"], row["status"]),
                "%s-%s" % (row.get("trim_start") or 0, row.get("trim_end") or "结束"),
                row.get("copyright_status") or "unreviewed", row["url"], row["error"],
            ))
        kind = "本地项目" if task.get("local_only") else "Odoo任务"
        self.selection_title.set("%s %s · %s · %s" % (
            kind, task["id"], task.get("name") or task.get("keywords") or task.get("target_language") or "抖音选片",
            task.get("local_status") or "处理中",
        ))
        self._refresh_selection_summary()

    def _refresh_selection_summary(self):
        self.selection_summary.set("%s 条，选中 %s 条" % (
            len(self.selection_tree.get_children()), len(self.selection_tree.selection()),
        ))

    def _selection_ids(self, default_all=False):
        selected = [int(value) for value in self.selection_tree.selection()]
        if selected or not default_all:
            return selected
        return [int(value) for value in self.selection_tree.get_children()]

    def select_all_videos(self):
        items = self.selection_tree.get_children()
        if items:
            self.selection_tree.selection_set(items)
        self._refresh_selection_summary()

    def _clipboard_text(self):
        try:
            return self.clipboard_get()
        except tk.TclError:
            return ""

    def _poll_clipboard(self):
        try:
            task = self._active_selection_task()
            if task and self.clipboard_listening.get() and not self.selection_busy:
                value = self._clipboard_text()
                if value and value != self.last_clipboard:
                    self.last_clipboard = value
                    added = self.selection_store.add_text(task["id"], value)
                    if added:
                        self._refresh_selection_tree()
                        self.write_log("任务 %s：自动加入 %s 条抖音视频" % (task["id"], added))
        finally:
            self.after(800, self._poll_clipboard)

    def add_selection_from_clipboard(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "当前没有等待处理的抖音选片任务")
            return
        added = self.selection_store.add_text(task["id"], self._clipboard_text())
        self._refresh_selection_tree()
        if not added:
            messagebox.showinfo(APP_TITLE, "剪贴板中没有新的有效抖音链接")

    def add_selection_manually(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "当前没有等待处理的抖音选片任务")
            return
        dialog = tk.Toplevel(self)
        dialog.title("添加抖音分享链接")
        dialog.geometry("700x360")
        ttk.Label(dialog, text="每行一个链接，也可直接粘贴抖音分享文字：").pack(anchor="w", padx=15, pady=(15, 5))
        editor = tk.Text(dialog, wrap="word")
        editor.pack(fill="both", expand=True, padx=15, pady=5)

        def save_links():
            added = self.selection_store.add_text(task["id"], editor.get("1.0", "end"))
            if not added:
                messagebox.showerror(APP_TITLE, "没有识别到新的有效抖音链接", parent=dialog)
                return
            dialog.destroy()
            self._refresh_selection_tree()

        ttk.Button(dialog, text="加入选片库", command=save_links).pack(pady=(5, 15))
        editor.focus_set()

    def add_local_videos(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择或新建一个项目")
            return
        paths = filedialog.askopenfilenames(
            filetypes=[("视频", "*.mp4 *.mov *.mkv *.webm *.avi"), ("所有文件", "*.*")],
        )
        if paths:
            self.selection_store.add_local_files(task["id"], paths)
            self._refresh_selection_tree()

    @staticmethod
    def _open_local_path(path):
        target = Path(path or "")
        if not target.is_file():
            raise FileNotFoundError("本地文件不存在，请先下载或重新生成")
        os.startfile(str(target))

    def preview_selected_video(self):
        ids = self._selection_ids()
        if len(ids) != 1:
            messagebox.showerror(APP_TITLE, "请选择一条已经下载的视频")
            return
        row = self.selection_store.get_many(ids)[0]
        try:
            self._open_local_path(row["local_path"])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def edit_selected_clip(self):
        ids = self._selection_ids()
        if len(ids) != 1:
            messagebox.showerror(APP_TITLE, "请选择一条已经下载的视频")
            return
        row = self.selection_store.get_many(ids)[0]
        path = Path(row.get("local_path") or "")
        if not path.is_file():
            messagebox.showerror(APP_TITLE, "请先下载该视频")
            return
        worker = self.worker or Worker(self.config())
        duration = max(0.1, worker.probe_duration(path))
        dialog = tk.Toplevel(self)
        dialog.title("内嵌预览、时间轴与版权")
        dialog.geometry("760x700")
        dialog.transient(self)
        preview = ttk.Label(dialog, text="正在读取预览…", anchor="center")
        preview.pack(fill="both", expand=True, padx=15, pady=15)
        position = tk.DoubleVar(value=float(row.get("trim_start") or 0))
        timeline = ttk.Scale(dialog, from_=0, to=duration, variable=position)
        timeline.pack(fill="x", padx=20)
        position_label = tk.StringVar()
        ttk.Label(dialog, textvariable=position_label).pack(pady=(3, 8))
        fields = ttk.Frame(dialog, padding=(20, 0))
        fields.pack(fill="x")
        trim_start = tk.StringVar(value=str(row.get("trim_start") or 0))
        trim_end = tk.StringVar(value=str(row.get("trim_end") or round(duration, 3)))
        copyright_status = tk.StringVar(value=row.get("copyright_status") or "unreviewed")
        copyright_note = tk.StringVar(value=row.get("copyright_note") or "")
        for index, (label, variable) in enumerate((("入点（秒）", trim_start), ("出点（秒）", trim_end))):
            ttk.Label(fields, text=label).grid(row=0, column=index * 2, sticky="w", padx=(0, 6))
            ttk.Entry(fields, textvariable=variable, width=12).grid(row=0, column=index * 2 + 1, padx=(0, 18))
        ttk.Label(fields, text="版权状态").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Combobox(
            fields, textvariable=copyright_status, state="readonly",
            values=("unreviewed", "authorized", "self_owned", "restricted"), width=18,
        ).grid(row=1, column=1, sticky="w")
        ttk.Label(fields, text="版权备注").grid(row=2, column=0, sticky="w")
        ttk.Entry(fields, textvariable=copyright_note).grid(row=2, column=1, columnspan=3, sticky="ew")
        fields.columnconfigure(3, weight=1)

        frame_path = app_dir() / ("preview-%s.jpg" % row["id"])
        def render_frame(_event=None):
            current = max(0, min(duration, float(position.get())))
            position_label.set("%.2f / %.2f 秒" % (current, duration))
            try:
                subprocess.run([
                    worker.ffmpeg(), "-y", "-ss", str(current), "-i", str(path),
                    "-frames:v", "1", "-vf", "scale=700:-2", str(frame_path),
                ], check=True, capture_output=True)
                image = Image.open(frame_path)
                photo = ImageTk.PhotoImage(image)
                preview.configure(image=photo, text="")
                preview.image = photo
            except Exception as exc:
                preview.configure(text="预览读取失败：" + str(exc), image="")
        timeline.bind("<ButtonRelease-1>", render_frame)

        def set_point(variable):
            variable.set("%.3f" % float(position.get()))

        point_controls = ttk.Frame(dialog)
        point_controls.pack(pady=8)
        ttk.Button(point_controls, text="当前位置设为入点", command=lambda: set_point(trim_start)).pack(side="left", padx=4)
        ttk.Button(point_controls, text="当前位置设为出点", command=lambda: set_point(trim_end)).pack(side="left", padx=4)
        ttk.Button(point_controls, text="用系统播放器播放", command=lambda: os.startfile(str(path))).pack(side="left", padx=4)

        def save_clip():
            start, end = float(trim_start.get()), float(trim_end.get())
            if start < 0 or end <= start or end > duration + 0.1:
                messagebox.showerror(APP_TITLE, "入点和出点超出视频有效时长", parent=dialog)
                return
            self.selection_store.update(
                row["id"], trim_start=start, trim_end=end,
                copyright_status=copyright_status.get(), copyright_note=copyright_note.get().strip(),
            )
            dialog.destroy()
            self._refresh_selection_tree()

        buttons = ttk.Frame(dialog)
        buttons.pack(pady=10)
        ttk.Button(buttons, text="保存", command=save_clip).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)
        render_frame()

    def show_versions(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个项目")
            return
        versions = self.selection_store.list_versions(task["id"])
        if not versions:
            messagebox.showinfo(APP_TITLE, "该项目还没有生成过审核稿")
            return
        dialog = tk.Toplevel(self)
        dialog.title("成片版本历史")
        dialog.geometry("760x420")
        tree = ttk.Treeview(dialog, columns=("version", "time", "path"), show="headings")
        for name, title, width in (("version", "版本", 80), ("time", "生成时间", 180), ("path", "成片文件", 460)):
            tree.heading(name, text=title); tree.column(name, width=width, anchor="w")
        for version in versions:
            tree.insert("", "end", iid=str(version["id"]), values=(
                "V%s" % version["version_no"], version["created_at"].replace("T", " ")[:19], version["result_path"],
            ))
        tree.pack(fill="both", expand=True, padx=12, pady=12)
        def preview_version():
            selected = tree.selection()
            if selected:
                target = next(item for item in versions if item["id"] == int(selected[0]))
                self._open_local_path(target["result_path"])
        ttk.Button(dialog, text="预览所选版本", command=preview_version).pack(pady=(0, 12))

    def preview_result(self):
        task = self._active_selection_task()
        try:
            self._open_local_path((task or {}).get("result_path"))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def open_project_folder(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个项目")
            return
        result = Path(task.get("result_path") or "")
        folder = result.parent if result.is_file() else Path(self.vars["work_dir"].get()).resolve() / str(task["id"])
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def delete_local_project(self):
        task = self._active_selection_task()
        if not task or not task.get("local_only"):
            messagebox.showinfo(APP_TITLE, "只能在本工具中删除独立本地项目；Odoo任务请在 Odoo 中管理。")
            return
        if not messagebox.askyesno(APP_TITLE, "删除该本地项目记录？已下载和生成的媒体文件会保留。"):
            return
        self.selection_store.delete_task(task["id"])
        self.selection_task_id = None
        self._refresh_selection_tasks()
        self._refresh_selection_tree()

    def delete_selected_videos(self):
        ids = self._selection_ids()
        if not ids:
            messagebox.showerror(APP_TITLE, "请先选择要删除的记录")
            return
        if not messagebox.askyesno(APP_TITLE, "确定删除所选 %s 条选片记录？" % len(ids)):
            return
        for row in self.selection_store.get_many(ids):
            path = Path(row["local_path"]) if row["local_path"] else None
            if path and path.is_file() and not row["url"].startswith("file:"):
                path.unlink()
        self.selection_store.delete(ids)
        self._refresh_selection_tree()

    def _run_downloads(self, task, rows, mix_after=False):
        worker = self.worker or Worker(self.config())
        heartbeat_stop = threading.Event()
        heartbeat = None
        if task["id"] in self.pending_selections:
            heartbeat = threading.Thread(
                target=worker.heartbeat_loop, args=(task["id"], heartbeat_stop), daemon=True,
            )
            heartbeat.start()
        try:
            clips_dir = worker.root / str(task["id"]) / "selected-videos"
            clips_dir.mkdir(parents=True, exist_ok=True)
            clips = []
            for index, row in enumerate(rows, 1):
                if row.get("copyright_status") == "restricted":
                    raise RuntimeError("视频 %s 已标记为限制使用，不能加入成片" % (row.get("video_id") or row["id"]))
                existing = Path(row["local_path"]) if row["local_path"] else None
                if existing and existing.is_file() and row["status"] in ("downloaded", "ready_review", "done"):
                    clips.append({
                        "path": existing, "trim_start": row.get("trim_start") or 0,
                        "trim_end": row.get("trim_end") or 0,
                    })
                    continue
                self.selection_store.update(row["id"], status="downloading", error="")
                self.events.put(("selection_changed", {}))
                target = clips_dir / ("video-%s.mp4" % row["id"])
                try:
                    path, video_id = worker.download_selection_video(row["url"], target)
                    self.selection_store.update(
                        row["id"], video_id=video_id or row["video_id"],
                        status="downloaded", local_path=str(path), error="",
                    )
                    clips.append({
                        "path": path, "trim_start": row.get("trim_start") or 0,
                        "trim_end": row.get("trim_end") or 0,
                    })
                except Exception as exc:
                    self.selection_store.update(row["id"], status="failed", error=str(exc))
                    raise
            if mix_after:
                for row in rows:
                    self.selection_store.update(row["id"], status="mixing", error="")
                self.events.put(("selection_changed", {}))
                version_no = len(self.selection_store.list_versions(task["id"])) + 1
                mix_dir = worker.root / str(task["id"]) / ("mix-output-v%s" % version_no)
                mix_dir.mkdir(parents=True)
                output, subtitle = worker.compose_video(task, clips, mix_dir)
                self.selection_store.set_task_result(
                    task["id"], output, subtitle or "", status="ready_review",
                )
                for row in rows:
                    self.selection_store.update(row["id"], status="ready_review", error="")
                self.events.put(("selection_mix_ready", {"task": task, "output": str(output)}))
            else:
                self.events.put(("selection_operation_done", {}))
        except Exception as exc:
            self.events.put(("log", {"message": "选片处理失败：" + str(exc)}))
            self.events.put(("selection_operation_error", {"error": str(exc)}))
        finally:
            heartbeat_stop.set()
            if heartbeat:
                heartbeat.join(timeout=2)

    def redownload_selected_videos(self):
        task = self._active_selection_task()
        ids = self._selection_ids()
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先选择要重新下载的视频")
            return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有选片处理正在运行")
            return
        self.selection_store.reset_download(ids)
        rows = self.selection_store.get_many(ids)
        self.selection_busy = True
        threading.Thread(target=self._run_downloads, args=(task, rows, False), daemon=True).start()

    def mix_selected_videos(self):
        task = self._active_selection_task()
        ids = self._selection_ids(default_all=True)
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先加入至少一个抖音视频")
            return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有选片处理正在运行")
            return
        rows = self.selection_store.get_many(ids)
        self.selection_busy = True
        threading.Thread(target=self._run_downloads, args=(task, rows, True), daemon=True).start()

    def upload_result(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个项目")
            return
        if task.get("local_only"):
            messagebox.showinfo(APP_TITLE, "这是独立本地项目，成片会保留在本机；从 Odoo 下发的项目才支持回传。")
            return
        if task["id"] not in self.pending_selections:
            messagebox.showerror(APP_TITLE, "该 Odoo 任务当前未被本工具持有，请启动工作节点重新领取后再回传")
            return
        result = Path(task.get("result_path") or "")
        subtitle = Path(task.get("subtitle_path") or "") if task.get("subtitle_path") else None
        if not result.is_file():
            messagebox.showerror(APP_TITLE, "尚未生成可回传的审核稿")
            return
        if not messagebox.askyesno(APP_TITLE, "已确认预览结果满意，并将成片回传 Odoo？"):
            return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有选片处理正在运行")
            return
        self.selection_busy = True

        def run_upload():
            worker = self.worker or Worker(self.config())
            try:
                worker.complete(task, result, subtitle if subtitle and subtitle.is_file() else None)
                for row in self.selection_store.list(task["id"]):
                    self.selection_store.update(row["id"], status="done", error="")
                self.events.put(("selection_upload_done", {"task": task, "output": str(result)}))
            except Exception as exc:
                self.events.put(("selection_operation_error", {"error": str(exc)}))

        threading.Thread(target=run_upload, daemon=True).start()

    def write_log(self, message):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n"
        self.log.config(state="normal"); self.log.insert("end", line); self.log.see("end"); self.log.config(state="disabled")
        with (app_dir() / "worker.log").open("a", encoding="utf-8") as stream: stream.write(line)

    def _close_app(self):
        self.stop_event.set()
        self.selector_bridge.close()
        self.destroy()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    MediaWorkerApp().mainloop()
