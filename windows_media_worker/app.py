import base64
import hashlib
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
from speech import synthesize, transcribe
from voice_library import default_voice_profiles, load_voice_profiles, save_voice_profiles
from worker import Worker, create_version_directory


APP_NAME = "LightLinkMediaWorker"
APP_TITLE = "LightLink 本地媒体生产工具"


def app_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


CONFIG_PATH = app_dir() / "config.json"
VOICE_LIBRARY_PATH = app_dir() / "voice_profiles.json"


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
        self.selection_cover_images = {}
        self.selection_metadata_pending = set()
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

        config_groups = [
            ("Odoo工作节点", [
                ("odoo_url", "Odoo地址", "https://lightlink029-max-dongcheng.odoo.com"),
                ("worker_token", "工作节点令牌", ""),
                ("worker_id", "工作节点名称", os.environ.get("COMPUTERNAME", "media-pc-01")),
                ("work_dir", "工作目录", str(app_dir() / "jobs")),
                ("poll_seconds", "轮询间隔（秒）", "10"),
                ("font_file", "字幕字体", "C:/Windows/Fonts/msyh.ttc"),
            ]),
            ("抖音下载", [
                ("download_proxy", "下载代理（可选）", ""),
            ]),
            ("本地AI", [
                ("ollama_url", "Ollama地址", "http://127.0.0.1:11434"),
                ("translation_model", "本地翻译模型", "qwen3:8b"),
                ("whisper_command", "语音识别程序（可选）", ""),
                ("whisper_model", "Whisper模型", "small"),
                ("ai_edit_command", "AI剪辑程序（可选）", ""),
            ]),
            ("语音合成", [
                ("sherpa_command", "sherpa-onnx程序（可选）", ""),
                ("sherpa_model", "sherpa音色模型", ""),
                ("sherpa_tokens", "sherpa Tokens", ""),
                ("sherpa_data_dir", "sherpa数据目录", ""),
                ("volc_api_key", "火山引擎 API Key", ""),
                ("volc_resource_id", "火山 Resource ID", "seed-tts-2.0"),
            ]),
            ("MuMu选片", [
                ("mumu_adb", "MuMu ADB（可自动检测）", ""),
                ("mumu_player", "MuMu 主程序（可自动检测）", ""),
                ("mumu_serial", "MuMu ADB 地址（留空自动检测）", ""),
            ]),
        ]
        config_notebook = ttk.Notebook(config_tab)
        config_notebook.pack(fill="both", expand=True, padx=20, pady=(20, 5))
        config_frames = {}
        for group_name, fields in config_groups:
            form = ttk.Frame(config_notebook, padding=20)
            config_notebook.add(form, text=group_name)
            config_frames[group_name] = form
            for row, (key, label, default) in enumerate(fields):
                ttk.Label(form, text=label, width=24).grid(row=row, column=0, sticky="w", pady=8)
                var = tk.StringVar(value=default)
                self.vars[key] = var
                show = "*" if key in ("worker_token", "volc_api_key") else ""
                ttk.Entry(form, textvariable=var, show=show).grid(row=row, column=1, sticky="ew", pady=8)
                if key == "work_dir":
                    ttk.Button(form, text="选择", command=self._choose_dir).grid(row=row, column=2, padx=8)
                elif key in ("mumu_adb", "mumu_player"):
                    ttk.Button(form, text="选择", command=lambda name=key: self._choose_exe(name)).grid(row=row, column=2, padx=8)
            form.columnconfigure(1, weight=1)

        odoo_form = config_frames["Odoo工作节点"]
        self.autostart = tk.BooleanVar(value=False)
        ttk.Checkbutton(odoo_form, text="登录Windows后自动启动并开始工作", variable=self.autostart).grid(
            row=6, column=1, sticky="w", pady=8)
        douyin_form = config_frames["抖音下载"]
        ttk.Label(douyin_form, text="抖音登录", width=24).grid(row=1, column=0, sticky="w", pady=8)
        self.douyin_status = tk.StringVar(value="未登录")
        ttk.Label(douyin_form, textvariable=self.douyin_status).grid(row=1, column=1, sticky="w", pady=8)
        self.douyin_login_button = ttk.Button(
            douyin_form, text="登录/更新抖音登录", command=self.login_douyin,
        )
        self.douyin_login_button.grid(row=1, column=2, padx=8)
        ttk.Button(odoo_form, text="测试Odoo连接", command=self.test_connection).grid(
            row=7, column=1, sticky="w", pady=8,
        )
        mumu_form = config_frames["MuMu选片"]
        mumu_actions = ttk.Frame(mumu_form)
        mumu_actions.grid(row=3, column=1, sticky="w", pady=8)
        ttk.Button(mumu_actions, text="检测MuMu", command=self.test_mumu).pack(side="left", padx=(0, 8))
        ttk.Button(mumu_actions, text="安装/更新选片APK", command=self.install_selector).pack(side="left")
        controls = ttk.Frame(config_tab, padding=(20, 5))
        controls.pack(fill="x")
        ttk.Button(controls, text="保存配置", command=self.save).pack(side="left", padx=4)
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
        self.selection_task_choice = ttk.Combobox(selection_header, state="readonly", width=34)
        self.selection_task_choice.pack(side="left", padx=8)
        self.selection_task_choice.bind("<<ComboboxSelected>>", self._on_selection_task_choice)

        selection_workflow = ttk.Notebook(selection_tab)
        selection_workflow.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        source_page = ttk.Frame(selection_workflow, padding=10)
        review_page = ttk.Frame(selection_workflow, padding=10)
        selection_workflow.add(source_page, text="① 素材与生成")
        selection_workflow.add(review_page, text="② 成片审核与回传")
        self.selection_workflow = selection_workflow
        self.selection_review_page = review_page

        source_header = ttk.Frame(source_page)
        source_header.pack(fill="x", pady=(0, 8))
        self.clipboard_listening = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            source_header, text="自动收集剪贴板中的抖音链接", variable=self.clipboard_listening,
        ).pack(side="right")
        ttk.Label(
            source_header,
            text="添加视频后先下载；选中1条走单条原声翻译，Ctrl选择多条则按页面顺序拼接。",
        ).pack(side="left")

        ttk.Style(self).configure("Media.Treeview", rowheight=78)
        selection_columns = (
            "video_id", "caption", "duration", "selected_at", "status", "trim",
            "copyright", "url", "error",
        )
        self.selection_tree = ttk.Treeview(
            source_page, columns=selection_columns, show="tree headings",
            selectmode="extended", style="Media.Treeview", height=5,
        )
        self.selection_tree.heading("#0", text="封面")
        self.selection_tree.column("#0", width=100, minwidth=100, stretch=False, anchor="center")
        titles = (
            "视频ID", "原视频文案", "时长", "选择时间", "处理状态", "入点-出点",
            "版权", "分享链接", "错误",
        )
        widths = (145, 300, 75, 145, 90, 100, 90, 280, 180)
        for column, title, width in zip(selection_columns, titles, widths):
            self.selection_tree.heading(column, text=title)
            self.selection_tree.column(column, width=width, anchor="w")
        selection_scroll = ttk.Scrollbar(
            source_page, orient="horizontal", command=self.selection_tree.xview,
        )
        self.selection_tree.configure(xscrollcommand=selection_scroll.set)
        self.selection_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_selection_summary())
        self.selection_tree.bind("<Double-1>", lambda _event: self.preview_selected_video())

        selection_controls = ttk.LabelFrame(source_page, text="视频素材管理", padding=10)
        selection_controls.pack(fill="x", pady=(0, 8))
        add_controls = ttk.Frame(selection_controls)
        add_controls.pack(fill="x", pady=(0, 6))
        edit_controls = ttk.Frame(selection_controls)
        edit_controls.pack(fill="x")
        ttk.Button(add_controls, text="全选", command=self.select_all_videos).pack(side="left", padx=3)
        ttk.Button(add_controls, text="从剪贴板添加", command=self.add_selection_from_clipboard).pack(side="left", padx=3)
        ttk.Button(add_controls, text="手工添加链接", command=self.add_selection_manually).pack(side="left", padx=3)
        ttk.Button(add_controls, text="添加本地视频", command=self.add_local_videos).pack(side="left", padx=3)
        ttk.Button(
            edit_controls, text="上移", command=lambda: self.move_selected_videos(-1),
        ).pack(side="left", padx=3)
        ttk.Button(
            edit_controls, text="下移", command=lambda: self.move_selected_videos(1),
        ).pack(side="left", padx=3)
        ttk.Button(edit_controls, text="时间轴/版权", command=self.edit_selected_clip).pack(side="left", padx=3)
        ttk.Button(edit_controls, text="删除所选", command=self.delete_selected_videos).pack(side="left", padx=3)
        ttk.Button(edit_controls, text="下载/重新下载", command=self.redownload_selected_videos).pack(side="left", padx=3)
        ttk.Button(edit_controls, text="预览所选素材", command=self.preview_selected_video).pack(side="left", padx=3)
        self.selection_summary = tk.StringVar(value="0 条")
        ttk.Label(add_controls, textvariable=self.selection_summary).pack(side="right")

        content_actions = ttk.LabelFrame(source_page, text="文案与生成", padding=10)
        content_actions.pack(side="bottom", fill="x")
        ttk.Button(
            content_actions, text="文案校验并生成混剪", command=self.edit_active_project,
        ).pack(side="left", padx=5)
        ttk.Button(content_actions, text="管理和试听音色", command=self.open_voice_manager).pack(side="left", padx=5)
        ttk.Label(
            content_actions,
            text="单条可识别原声；多条固定按列表顺序拼接，文案确认后生成审核稿。",
            foreground="#666",
        ).pack(side="left", padx=18)
        selection_scroll.pack(side="bottom", fill="x", pady=(0, 8))
        self.selection_tree.pack(fill="both", expand=True, pady=(0, 10))

        project_actions = ttk.LabelFrame(review_page, text="项目文件管理", padding=8)
        project_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(project_actions, text="打开项目目录", command=self.open_project_folder).pack(side="left", padx=5)
        ttk.Button(project_actions, text="删除本地项目", command=self.delete_local_project).pack(side="left", padx=5)
        ttk.Label(project_actions, text="独立本地项目只保存在本机，不会自动上传。", foreground="#666").pack(side="left", padx=18)

        review_sources = ttk.LabelFrame(review_page, text="当前项目使用的视频素材", padding=8)
        review_sources.pack(fill="both", expand=True)
        self.review_source_tree = ttk.Treeview(
            review_sources, columns=("video_id", "status", "url"), show="headings", height=6,
        )
        for name, title, width in (
            ("video_id", "视频ID", 190), ("status", "处理状态", 120), ("url", "来源链接/本地文件", 700),
        ):
            self.review_source_tree.heading(name, text=title)
            self.review_source_tree.column(name, width=width, anchor="w")
        self.review_source_tree.pack(fill="both", expand=True)
        self.review_source_tree.bind("<Double-1>", lambda _event: self.preview_review_source())
        ttk.Button(
            review_sources, text="预览所选源视频", command=self.preview_review_source,
        ).pack(anchor="w", pady=(8, 0))

        review_versions = ttk.LabelFrame(review_page, text="审核稿与历史版本", padding=8)
        review_versions.pack(fill="both", expand=True, pady=(10, 0))
        review_actions = ttk.Frame(review_versions)
        review_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(review_actions, text="预览所选版本", command=self.preview_selected_version).pack(side="left", padx=5)
        ttk.Button(
            review_actions, text="全选审核稿",
            command=lambda: self.render_tree.selection_set(self.render_tree.get_children()),
        ).pack(side="left", padx=5)
        ttk.Button(review_actions, text="批量删除所选审核稿", command=self.delete_selected_version).pack(side="left", padx=5)
        ttk.Button(review_actions, text="确认回传最新审核稿", command=self.upload_result).pack(side="left", padx=5)
        self.render_tree = ttk.Treeview(
            review_versions, columns=("version", "time", "path"), show="headings",
            selectmode="extended", height=5,
        )
        for name, title, width in (
            ("version", "版本", 90), ("time", "生成时间", 180), ("path", "成片文件", 740),
        ):
            self.render_tree.heading(name, text=title)
            self.render_tree.column(name, width=width, anchor="w")
        self.render_tree.pack(fill="both", expand=True)
        self.render_tree.bind("<Double-1>", lambda _event: self.preview_selected_version())
        self.render_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_review_sources())

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
                "volc_api_key": self.vars["volc_api_key"].get().strip(),
                "volc_resource_id": self.vars["volc_resource_id"].get().strip(),
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
            api_key = speech.pop("volc_api_key", "")
            if api_key:
                speech["volc_api_key_dpapi"] = base64.b64encode(
                    _dpapi(api_key.encode("utf-8"), True)
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
                legacy_keys = {"volc_app_id", "volc_token", "volc_token_dpapi", "volc_cluster"}
                if legacy_keys.intersection(speech):
                    for key in legacy_keys:
                        speech.pop(key, None)
                    data["speech"] = speech
                    CONFIG_PATH.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
                    )
                encrypted = speech.get("volc_api_key_dpapi")
                if encrypted:
                    speech["volc_api_key"] = _dpapi(base64.b64decode(encrypted), False).decode("utf-8")
                flat = dict(data); flat.update(data.get("local_ai", {})); flat.update(speech)
                for key, var in self.vars.items():
                    if key in flat: var.set(str(flat[key]))
            except Exception as exc: self.write_log("配置读取失败：" + str(exc))
        saved_voices = load_voice_profiles(VOICE_LIBRARY_PATH)
        supported_voices = [
            profile for profile in saved_voices
            if profile.get("provider") in ("sherpa", "volcengine")
        ]
        if len(supported_voices) != len(saved_voices):
            save_voice_profiles(VOICE_LIBRARY_PATH, supported_voices)
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
                elif event == "project_translation":
                    button = data["button"]
                    try:
                        if button.winfo_exists():
                            button.config(state="normal")
                        editor = data["editor"]
                        if editor.winfo_exists() and not data.get("error"):
                            editor.delete("1.0", "end")
                            editor.insert("1.0", data["text"])
                            if data.get("source_var") and data.get("source_value"):
                                data["source_var"].set(data["source_value"])
                    except tk.TclError:
                        pass
                    if data.get("error"):
                        messagebox.showerror(APP_TITLE, data["error"])
                elif event == "project_transcript":
                    button = data["button"]
                    try:
                        if button.winfo_exists():
                            button.config(state="normal")
                        editor = data["editor"]
                        if editor.winfo_exists() and not data.get("error"):
                            editor.delete("1.0", "end")
                            editor.insert("1.0", data["text"])
                    except tk.TclError:
                        pass
                    if data.get("error"):
                        messagebox.showerror(APP_TITLE, data["error"])
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
                    self.selection_workflow.select(self.selection_review_page)
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
                elif event == "voice_preview":
                    button = data.get("button")
                    status = data.get("status")
                    try:
                        if button and button.winfo_exists():
                            button.config(state="normal")
                        if status:
                            status.set(
                                "试听失败" if data.get("error") else
                                ("已播放本地缓存" if data.get("cached") else "已生成并缓存到本地")
                            )
                    except tk.TclError:
                        pass
                    if data.get("error"):
                        messagebox.showerror(APP_TITLE, data["error"])
                    else:
                        try:
                            os.startfile(data["path"])
                        except OSError as exc:
                            messagebox.showerror(APP_TITLE, "试听音频无法播放：" + str(exc))
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
        if existing.get("id") and existing.get("id") == self.selection_task_id:
            task_rows = self.selection_store.get_many(self._selection_ids(default_all=True))
        else:
            task_rows = self.selection_store.list(existing["id"]) if existing.get("id") else []
        content_choices = {
            "original_translation": "使用原视频译文",
            "odoo_translation": "使用 Odoo 文案译文",
            "custom_translation": "使用自写文案译文",
        }
        tts_choices = {
            "none": "不生成配音", "sherpa": "sherpa-onnx 本地音色",
            "volcengine": "火山引擎音色",
        }
        preset_choices = {
            "douyin": "抖音 / TikTok 9:16", "reels": "Instagram Reels 9:16",
            "feed": "Instagram Feed 4:5", "square": "网站 / 社媒方图 1:1",
        }
        dialog = tk.Toplevel(self)
        dialog.title("编辑视频项目" if task else "新建本地视频项目")
        dialog.geometry("1180x820")
        dialog.minsize(980, 700)
        dialog.transient(self)
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)
        project_notebook = ttk.Notebook(body)
        project_notebook.pack(fill="both", expand=True, padx=12, pady=12)
        source_form = ttk.Frame(project_notebook, padding=16)
        content_form = ttk.Frame(project_notebook, padding=16)
        output_form = ttk.Frame(project_notebook, padding=16)
        project_notebook.add(content_form, text="文案翻译与校验")
        project_notebook.add(source_form, text="基础与素材")
        project_notebook.add(output_form, text="剪辑、配音与导出")
        for page in (source_form, content_form, output_form):
            page.columnconfigure(1, weight=1)

        values = {
            "name": tk.StringVar(value=existing.get("name") or "本地视频项目"),
            "keywords": tk.StringVar(value=existing.get("keywords") or ""),
            "source_language": tk.StringVar(value=existing.get("source_language") or "Chinese"),
            "target_language": tk.StringVar(value=existing.get("target_language") or "English"),
            "duration_seconds": tk.StringVar(value=str(existing.get("duration_seconds") or 15)),
            "aspect_ratio": tk.StringVar(value=existing.get("aspect_ratio") or "9:16"),
            "content_source": tk.StringVar(value=(
                existing.get("content_source")
                if existing.get("content_source") in content_choices
                else ("original_translation" if len(task_rows) == 1 else "odoo_translation")
            )),
            "export_preset": tk.StringVar(value=preset_choices.get(existing.get("export_preset") or "douyin")),
            "transition": tk.StringVar(value="淡入淡出" if existing.get("transition") == "fade" else "无转场"),
            "tts_provider": tk.StringVar(value=tts_choices.get(
                existing.get("tts_provider") or "none", tts_choices["none"],
            )),
            "tts_voice": tk.StringVar(value=existing.get("tts_voice") or ""),
            "tts_speed": tk.StringVar(value=str(existing.get("tts_speed") or 1.0)),
            "tts_volume": tk.StringVar(value=str(existing.get("tts_volume") or 1.0)),
            "background_music": tk.StringVar(value=existing.get("background_music") or ""),
            "music_volume": tk.StringVar(value=str(existing.get("music_volume") or 0.2)),
            "source_image_path": tk.StringVar(value=existing.get("source_image_path") or ""),
        }
        local_files = list(existing.get("local_files") or [])

        source_rows = (
            ("项目名称", "name", None), ("搜索关键词", "keywords", None),
            ("原视频语言", "source_language", None),
            ("目标语言", "target_language", None),
            ("成片时长（秒）", "duration_seconds", None),
        )
        output_rows = (
            ("画面比例", "aspect_ratio", ("9:16", "4:5", "1:1")),
            ("导出预设", "export_preset", tuple(preset_choices.values())),
            ("转场", "transition", ("无转场", "淡入淡出")),
            ("配音服务", "tts_provider", tuple(tts_choices.values())),
            ("音色名称/ID", "tts_voice", None),
            ("配音语速", "tts_speed", None),
            ("配音音量", "tts_volume", None),
            ("背景音乐音量", "music_volume", None),
        )
        widgets = {}
        for page, rows in ((source_form, source_rows), (output_form, output_rows)):
            for row, (label, key, choices) in enumerate(rows):
                ttk.Label(page, text=label, width=20).grid(row=row, column=0, sticky="w", pady=7)
                if key == "tts_voice":
                    widget = ttk.Combobox(
                        page, textvariable=values[key],
                        values=[profile["voice_id"] for profile in self._voice_profiles()],
                    )
                else:
                    widget = ttk.Combobox(
                        page, textvariable=values[key], values=choices, state="readonly",
                    ) if choices else ttk.Entry(page, textvariable=values[key])
                widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=7)
                widgets[key] = widget

        voice_widgets = [widgets["tts_voice"]]

        def load_provider_voices(_event=None):
            provider_label = values["tts_provider"].get()
            provider_key = next(
                (key for key, label in tts_choices.items() if label == provider_label), "none",
            )
            profiles = [
                profile for profile in self._voice_profiles()
                if profile["provider"] == provider_key
            ]
            for voice_widget in voice_widgets:
                voice_widget["values"] = [profile["voice_id"] for profile in profiles]
            available_ids = {profile["voice_id"] for profile in profiles}
            if profiles and values["tts_voice"].get().strip() not in available_ids:
                values["tts_voice"].set(profiles[0]["voice_id"])
            elif not profiles:
                values["tts_voice"].set("")

        widgets["tts_provider"].bind("<<ComboboxSelected>>", load_provider_voices)
        load_provider_voices()

        music_row = len(output_rows)
        ttk.Label(output_form, text="背景音乐", width=20).grid(row=music_row, column=0, sticky="w", pady=7)
        ttk.Entry(output_form, textvariable=values["background_music"]).grid(row=music_row, column=1, sticky="ew", pady=7)
        ttk.Button(
            output_form, text="选择音频",
            command=lambda: values["background_music"].set(filedialog.askopenfilename(
                parent=dialog, filetypes=[("音频", "*.mp3 *.wav *.m4a *.aac"), ("所有文件", "*.*")],
            ) or values["background_music"].get()),
        ).grid(row=music_row, column=2, padx=(8, 0))

        image_row = len(source_rows)
        ttk.Label(source_form, text="搜索参考图片", width=20).grid(row=image_row, column=0, sticky="w", pady=7)
        ttk.Entry(source_form, textvariable=values["source_image_path"]).grid(row=image_row, column=1, sticky="ew", pady=7)
        ttk.Button(
            source_form, text="选择图片",
            command=lambda: values["source_image_path"].set(filedialog.askopenfilename(
                parent=dialog, filetypes=[("图片", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")],
            ) or values["source_image_path"].get()),
        ).grid(row=image_row, column=2, padx=(8, 0))

        video_row = image_row + 1
        ttk.Label(source_form, text="本地视频", width=20).grid(row=video_row, column=0, sticky="nw", pady=7)
        local_label = tk.StringVar(value="已选择 %s 个文件" % len(local_files))
        ttk.Label(source_form, textvariable=local_label).grid(row=video_row, column=1, sticky="w", pady=7)
        def choose_videos():
            selected = filedialog.askopenfilenames(
                parent=dialog, filetypes=[("视频", "*.mp4 *.mov *.mkv *.webm *.avi"), ("所有文件", "*.*")],
            )
            for path in selected:
                if path not in local_files:
                    local_files.append(path)
            local_label.set("已选择 %s 个文件" % len(local_files))
        ttk.Button(source_form, text="添加视频", command=choose_videos).grid(row=video_row, column=2, padx=(8, 0))

        url_row = video_row + 1
        ttk.Label(source_form, text="抖音链接", width=20).grid(row=url_row, column=0, sticky="nw", pady=7)
        urls = tk.Text(source_form, height=8, wrap="word")
        urls.grid(row=url_row, column=1, columnspan=2, sticky="nsew", pady=5)
        urls.insert("1.0", "\n".join(existing.get("source_urls") or []))
        source_form.rowconfigure(url_row, weight=1)

        workflow_label = (
            "单条视频 · 原声识别/翻译" if len(task_rows) == 1 else
            "多条视频 · 按下列顺序拼接" if len(task_rows) > 1 else "尚未选择视频"
        )
        ttk.Label(content_form, text=workflow_label, font=("Microsoft YaHei UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 5),
        )
        selected_tree = ttk.Treeview(
            content_form, columns=("order", "video_id", "source"), show="headings", height=3,
        )
        for name, title, width in (
            ("order", "顺序", 55), ("video_id", "视频ID", 190), ("source", "视频来源", 700),
        ):
            selected_tree.heading(name, text=title)
            selected_tree.column(name, width=width, anchor="w")
        selected_tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 8))
        for index, item in enumerate(task_rows, 1):
            selected_tree.insert("", "end", values=(
                index, item.get("video_id") or "待解析", item.get("url") or item.get("local_path") or "",
            ))

        ttk.Label(content_form, text="中文文案（可编辑）", anchor="center").grid(row=2, column=0, sticky="ew")
        ttk.Label(content_form, text="操作 / 最终使用", anchor="center").grid(row=2, column=1, sticky="ew")
        ttk.Label(
            content_form, text="目标语言译文（可人工校验）", anchor="center",
        ).grid(row=2, column=2, sticky="ew")
        content_form.columnconfigure(0, weight=1)
        content_form.columnconfigure(1, weight=0, minsize=175)
        content_form.columnconfigure(2, weight=1)

        editors = (
            ("原视频中文", existing.get("original_transcript") or "",
             existing.get("original_translation") or "", "original_translation"),
            ("Odoo 传入文案", existing.get("video_script") or existing.get("prompt") or "",
             existing.get("odoo_translation") or "", "odoo_translation"),
            ("自写文案", existing.get("custom_script") or "",
             existing.get("custom_translation") or "", "custom_translation"),
        )
        action_frames = {}
        editor_widgets = {}
        for row_index, (label, source_text, target_text, source_key) in enumerate(editors, 3):
            source_box = ttk.LabelFrame(content_form, text=label, padding=5)
            source_box.grid(row=row_index, column=0, sticky="nsew", padx=(0, 6), pady=4)
            source_editor = tk.Text(source_box, height=7, wrap="word")
            source_editor.pack(fill="both", expand=True)
            source_editor.insert("1.0", source_text)
            action = ttk.Frame(content_form, padding=5)
            action.grid(row=row_index, column=1, sticky="nsew", pady=4)
            ttk.Radiobutton(
                action, text="使用此译文", variable=values["content_source"], value=source_key,
            ).pack(pady=(8, 5))
            target_box = ttk.LabelFrame(content_form, text="目标语言", padding=5)
            target_box.grid(row=row_index, column=2, sticky="nsew", padx=(6, 0), pady=4)
            target_editor = tk.Text(target_box, height=7, wrap="word")
            target_editor.pack(fill="both", expand=True)
            target_editor.insert("1.0", target_text)
            action_frames[source_key] = action
            editor_widgets[source_key] = (source_editor, target_editor)
            content_form.rowconfigure(row_index, weight=1)

        original_transcript, original_translation = editor_widgets["original_translation"]
        script, odoo_translation = editor_widgets["odoo_translation"]
        custom_script, custom_translation = editor_widgets["custom_translation"]

        transcript_button = ttk.Button(action_frames["original_translation"], text="① 识别原声")
        transcript_button.pack(fill="x", pady=3)
        if len(task_rows) != 1:
            transcript_button.config(state="disabled")
            for child in action_frames["original_translation"].winfo_children():
                if isinstance(child, ttk.Radiobutton):
                    child.config(state="disabled")
            if values["content_source"].get() == "original_translation":
                values["content_source"].set("odoo_translation")

        def recognize_single_video():
            rows = task_rows
            if len(rows) != 1:
                messagebox.showerror(APP_TITLE, "原声识别仅用于单条视频模式", parent=dialog)
                return
            transcript_button.config(state="disabled")
            current = dict(existing)
            current["source_language"] = values["source_language"].get().strip() or "Chinese"

            def run_recognition():
                try:
                    updated, _count = self._recognize_task_rows(
                        self.worker or Worker(self.config()), current, rows,
                    )
                    self.events.put(("project_transcript", {
                        "button": transcript_button, "editor": original_transcript,
                        "text": updated.get("original_transcript") or "",
                    }))
                except Exception as exc:
                    self.events.put(("project_transcript", {
                        "button": transcript_button, "editor": original_transcript,
                        "error": str(exc),
                    }))

            threading.Thread(target=run_recognition, daemon=True).start()

        transcript_button.config(command=recognize_single_video)

        def translate_text(source_editor, target_editor, source_key, button):
            text = source_editor.get("1.0", "end").strip()
            if not text:
                messagebox.showerror(APP_TITLE, "左侧文案为空，请先填写或识别", parent=dialog)
                return
            button.config(state="disabled")

            def run_translation():
                try:
                    result = Worker(self.config()).translate(
                        text, values["target_language"].get().strip() or "English",
                    )
                    self.events.put(("project_translation", {
                        "button": button, "editor": target_editor, "text": result,
                        "source_var": values["content_source"], "source_value": source_key,
                    }))
                except Exception as exc:
                    self.events.put(("project_translation", {
                        "button": button, "editor": target_editor,
                        "error": str(exc),
                    }))

            threading.Thread(target=run_translation, daemon=True).start()

        for source_editor, target_editor, source_key in (
            (original_transcript, original_translation, "original_translation"),
            (script, odoo_translation, "odoo_translation"),
            (custom_script, custom_translation, "custom_translation"),
        ):
            button = ttk.Button(action_frames[source_key], text="② 翻译 →")
            button.pack(fill="x", pady=3)
            if source_key == "original_translation" and len(task_rows) != 1:
                button.config(state="disabled")
            button.config(command=lambda s=source_editor, t=target_editor, k=source_key, b=button:
                          translate_text(s, t, k, b))

        voice_bar = ttk.LabelFrame(content_form, text="本次生成音色", padding=8)
        voice_bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(voice_bar, text="服务商").pack(side="left")
        quick_provider = ttk.Combobox(
            voice_bar, textvariable=values["tts_provider"],
            values=tuple(tts_choices.values()), state="readonly", width=24,
        )
        quick_provider.pack(side="left", padx=(6, 16))
        ttk.Label(voice_bar, text="音色").pack(side="left")
        quick_voice = ttk.Combobox(voice_bar, textvariable=values["tts_voice"], width=36)
        quick_voice.pack(side="left", padx=6)
        voice_widgets.append(quick_voice)
        quick_provider.bind("<<ComboboxSelected>>", load_provider_voices)
        voice_hint = tk.StringVar()
        ttk.Label(voice_bar, textvariable=voice_hint, foreground="#666").pack(side="left", padx=6)

        def update_voice_hint(*_args):
            selected_id = values["tts_voice"].get().strip()
            provider_key = next(
                (key for key, label in tts_choices.items() if label == values["tts_provider"].get()),
                "none",
            )
            profile = next(
                (item for item in self._voice_profiles()
                 if item["provider"] == provider_key and item["voice_id"] == selected_id),
                None,
            )
            voice_hint.set(
                "%s · %s" % (profile["name"], profile.get("description") or profile.get("language") or "")
                if profile else ""
            )

        quick_voice.bind("<<ComboboxSelected>>", update_voice_hint)
        widgets["tts_voice"].bind("<<ComboboxSelected>>", update_voice_hint)
        values["tts_voice"].trace_add("write", update_voice_hint)
        ttk.Button(voice_bar, text="管理/试听音色", command=self.open_voice_manager).pack(side="left", padx=12)
        load_provider_voices()
        update_voice_hint()

        def save_project(open_search=False, generate_review=False):
            try:
                generation_ids = []
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
                    "edit_mode": "sequence",
                    "subtitle_mode": "script",
                    "content_source": values["content_source"].get(),
                    "audio_mode": "mute",
                    "export_preset": preset_key,
                    "transition": "fade" if values["transition"].get() == "淡入淡出" else "none",
                    "tts_provider": next(key for key, label in tts_choices.items() if label == values["tts_provider"].get()),
                    "tts_voice": values["tts_voice"].get().strip(),
                    "tts_model_id": next((
                        profile.get("model_id", "") for profile in self._voice_profiles()
                        if profile["provider"] == next(
                            key for key, label in tts_choices.items()
                            if label == values["tts_provider"].get()
                        ) and profile["voice_id"] == values["tts_voice"].get().strip()
                    ), existing.get("tts_model_id") or ""),
                    "tts_speed": max(0.5, min(2.0, float(values["tts_speed"].get()))),
                    "tts_volume": max(0.0, min(2.0, float(values["tts_volume"].get()))),
                    "background_music": values["background_music"].get().strip(),
                    "music_volume": max(0.0, min(1.0, float(values["music_volume"].get()))),
                    "translate_subtitles": False,
                    "original_transcript": original_transcript.get("1.0", "end").strip(),
                    "original_translation": original_translation.get("1.0", "end").strip(),
                    "video_script": script.get("1.0", "end").strip(),
                    "odoo_translation": odoo_translation.get("1.0", "end").strip(),
                    "custom_script": custom_script.get("1.0", "end").strip(),
                    "custom_translation": custom_translation.get("1.0", "end").strip(),
                    "source_image_path": image_path,
                    "source_urls": [line.strip() for line in urls.get("1.0", "end").splitlines() if line.strip()],
                    "local_files": local_files,
                })
                if generate_review:
                    if existing.get("id"):
                        generation_ids = [row["id"] for row in task_rows]
                        clip_count = len(generation_ids)
                    else:
                        clip_count = len(set(project["source_urls"])) + len(set(local_files))
                    project = Worker.prepare_edit_workflow(project, clip_count)
                self.selection_store.update_task(project, status=existing.get("local_status") or "draft")
                self.selection_store.add_text(task_id, "\n".join(project["source_urls"]))
                self.selection_store.add_local_files(task_id, local_files)
                if generate_review and not generation_ids:
                    generation_ids = [row["id"] for row in self.selection_store.list(task_id)]
                if task_id in self.pending_selections:
                    self.pending_selections[task_id] = project
                self.selection_task_id = task_id
                dialog.destroy()
                self._refresh_selection_tasks()
                self._refresh_selection_tree()
                self.notebook.select(self.selection_tab)
                if open_search:
                    self._open_project_search(project)
                elif generate_review:
                    self.after(100, lambda ids=generation_ids: self.mix_selected_videos(ids))
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        actions = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        actions.pack(side="bottom", fill="x")
        ttk.Button(actions, text="保存", command=save_project).pack(side="left", padx=4)
        ttk.Button(actions, text="保存并打开抖音搜索", command=lambda: save_project(True)).pack(side="left", padx=4)
        ttk.Button(
            actions, text="确认文案并生成审核稿",
            command=lambda: save_project(False, True),
        ).pack(side="right", padx=4)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="right", padx=4)

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
        self.selection_cover_images.clear()
        for item in self.selection_tree.get_children():
            self.selection_tree.delete(item)
        self._refresh_review_lists(task)
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
            cover = self._selection_cover(row)
            caption = row.get("caption") or (
                "暂无文案" if row.get("caption_checked") else "待获取"
            )
            self.selection_tree.insert("", "end", iid=str(row["id"]), image=cover, values=(
                row["video_id"] or "待下载解析", caption.replace("\n", " "),
                self._format_duration(row.get("duration") or 0),
                row["selected_at"].replace("T", " ")[:19],
                labels.get(row["status"], row["status"]),
                "%s-%s" % (row.get("trim_start") or 0, row.get("trim_end") or "结束"),
                row.get("copyright_status") or "unreviewed", row["url"], row["error"],
            ))
        self._schedule_selection_metadata(task, rows)
        kind = "本地项目" if task.get("local_only") else "Odoo任务"
        self.selection_title.set("%s %s · %s · %s" % (
            kind, task["id"], task.get("name") or task.get("keywords") or task.get("target_language") or "抖音选片",
            task.get("local_status") or "处理中",
        ))
        self._refresh_selection_summary()

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(round(float(seconds or 0))))
        if not seconds:
            return "待获取"
        minutes, seconds = divmod(seconds, 60)
        return "%d:%02d" % (minutes, seconds)

    def _selection_cover(self, row):
        path = Path(row.get("cover_path") or "")
        if not path.is_file():
            return ""
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((82, 68), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (82, 68), "#eeeeee")
            canvas.paste(image, ((82 - image.width) // 2, (68 - image.height) // 2))
            photo = ImageTk.PhotoImage(canvas)
            self.selection_cover_images[row["id"]] = photo
            return photo
        except (OSError, ValueError):
            return ""

    def _schedule_selection_metadata(self, task, rows):
        missing = []
        for row in rows:
            local_path = Path(row.get("local_path") or "")
            needs_local = local_path.is_file() and not row.get("media_checked")
            needs_caption = (
                local_path.is_file() and not row.get("caption_checked")
                and row["url"].startswith("http")
            )
            if (needs_local or needs_caption) and row["id"] not in self.selection_metadata_pending:
                self.selection_metadata_pending.add(row["id"])
                missing.append(row)
        if missing:
            config = None if self.worker else self.config()
            threading.Thread(
                target=self._backfill_selection_metadata,
                args=(task["id"], missing, config), daemon=True,
            ).start()

    def _backfill_selection_metadata(self, task_id, rows, config):
        worker = self.worker or Worker(config)
        for row in rows:
            try:
                path = Path(row["local_path"])
                cover_path = worker.root / str(task_id) / "selected-videos" / ("cover-%s.jpg" % row["id"])
                duration, cover = worker.create_video_cover(path, cover_path)
                values = {"duration": duration, "media_checked": 1}
                if cover:
                    values["cover_path"] = str(cover)
                self.selection_store.update(row["id"], **values)
                if not row.get("caption_checked") and row["url"].startswith("http"):
                    try:
                        metadata = worker.douyin_video_metadata(row["url"])
                        self.selection_store.update(
                            row["id"], **metadata, caption_checked=1,
                        )
                    except Exception as exc:
                        self.selection_store.update(row["id"], caption_checked=1)
                        self.events.put(("log", {
                            "message": "视频 %s 原文案获取失败：%s" % (row["id"], exc),
                        }))
            except Exception as exc:
                self.events.put(("log", {"message": "视频 %s 信息补全失败：%s" % (row["id"], exc)}))
            finally:
                self.selection_metadata_pending.discard(row["id"])
        self.events.put(("selection_changed", {}))

    def _refresh_review_lists(self, task):
        for tree in (self.review_source_tree, self.render_tree):
            for item in tree.get_children():
                tree.delete(item)
        if not task:
            return
        versions = self.selection_store.list_versions(task["id"])
        for version in versions:
            self.render_tree.insert("", "end", iid=str(version["id"]), values=(
                "V%s" % version["version_no"],
                version["created_at"].replace("T", " ")[:19],
                version["result_path"],
            ))
        if versions:
            self.render_tree.selection_set(str(versions[0]["id"]))
        self._refresh_review_sources()

    def _refresh_review_sources(self):
        for item in self.review_source_tree.get_children():
            self.review_source_tree.delete(item)
        task = self._active_selection_task()
        if not task:
            return
        rows = self.selection_store.list(task["id"])
        selected = self.render_tree.selection()
        versions = self.selection_store.list_versions(task["id"])
        version = next(
            (item for item in versions if selected and item["id"] == int(selected[0])),
            versions[0] if versions else None,
        )
        source_ids = set(version.get("source_video_ids") or []) if version else set()
        if not source_ids:
            source_ids = {row["id"] for row in rows}
        labels = {
            "selected": "已选择", "downloading": "下载中", "downloaded": "已下载",
            "mixing": "混剪中", "ready_review": "待审核", "done": "已完成", "failed": "失败",
        }
        for row in rows:
            if row["id"] in source_ids:
                self.review_source_tree.insert("", "end", iid=str(row["id"]), values=(
                    row["video_id"] or "待下载解析",
                    labels.get(row["status"], row["status"]),
                    row["url"],
                ))

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
        dialog.geometry("900x720")
        dialog.minsize(760, 620)
        dialog.transient(self)
        control_panel = ttk.Frame(dialog, padding=(15, 8, 15, 12))
        control_panel.pack(side="bottom", fill="x")
        preview = ttk.Label(dialog, text="正在读取预览…", anchor="center")
        preview.pack(fill="both", expand=True, padx=15, pady=(15, 5))
        position = tk.DoubleVar(value=float(row.get("trim_start") or 0))
        timeline = ttk.Scale(control_panel, from_=0, to=duration, variable=position)
        timeline.pack(fill="x", padx=5)
        position_label = tk.StringVar()
        ttk.Label(control_panel, textvariable=position_label).pack(pady=(3, 8))
        fields = ttk.Frame(control_panel)
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
                    "-frames:v", "1", "-vf",
                    "scale=700:380:force_original_aspect_ratio=decrease", str(frame_path),
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

        point_controls = ttk.Frame(control_panel)
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

        buttons = ttk.Frame(control_panel)
        buttons.pack(pady=10)
        ttk.Button(buttons, text="保存", command=save_clip).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)
        render_frame()

    def preview_review_source(self):
        selected = self.review_source_tree.selection()
        if not selected:
            messagebox.showerror(APP_TITLE, "请先选择要预览的源视频")
            return
        row = self.selection_store.get_many([int(selected[0])])[0]
        try:
            self._open_local_path(row.get("local_path"))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, "源视频尚未下载或文件不可用：%s" % exc)

    def preview_selected_version(self):
        task = self._active_selection_task()
        selected = self.render_tree.selection()
        if not task or not selected:
            self.preview_result()
            return
        version = next(
            (item for item in self.selection_store.list_versions(task["id"])
             if item["id"] == int(selected[0])),
            None,
        )
        if version:
            try:
                self._open_local_path(version["result_path"])
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc))

    def delete_selected_version(self):
        task = self._active_selection_task()
        selected = self.render_tree.selection()
        if not task or not selected:
            messagebox.showerror(APP_TITLE, "请先选择要删除的审核稿；可按 Ctrl 或 Shift 多选")
            return
        selected_ids = {int(value) for value in selected}
        versions = [
            item for item in self.selection_store.list_versions(task["id"])
            if item["id"] in selected_ids
        ]
        if not versions:
            messagebox.showerror(APP_TITLE, "所选审核稿记录已不存在")
            return
        version_names = "、".join("V%s" % item["version_no"] for item in versions)
        if not messagebox.askyesno(
            APP_TITLE,
            "确定永久删除以下 %s 份审核稿及其生成文件？\n%s" %
            (len(versions), version_names),
        ):
            return
        try:
            task_dirs = {
                Path(self.vars["work_dir"].get()).expanduser().resolve()
                / str(int(task["id"])),
                (app_dir() / "jobs" / str(int(task["id"]))).resolve(),
            }
            version_dirs = set()
            for version in versions:
                result = Path(version["result_path"]).expanduser().resolve()
                version_dir = result.parent
                if result.exists() and (
                    version_dir.parent not in task_dirs
                    or not version_dir.name.startswith("mix-output")
                ):
                    raise RuntimeError("审核稿目录不在当前项目范围内，已中止删除")
                if result.exists():
                    version_dirs.add(version_dir)
            for version_dir in version_dirs:
                shutil.rmtree(version_dir)
            self.selection_store.delete_versions(task["id"], selected_ids)
            self._refresh_selection_tree()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, "删除审核稿失败：%s" % exc)

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

    def move_selected_videos(self, direction):
        task = self._active_selection_task()
        ids = self._selection_ids()
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先选择要移动的视频")
            return
        self.selection_store.move(task["id"], ids, direction)
        self._refresh_selection_tree()
        available = set(self.selection_tree.get_children())
        self.selection_tree.selection_set([str(value) for value in ids if str(value) in available])
        first = next((str(value) for value in ids if str(value) in available), None)
        if first:
            self.selection_tree.see(first)

    def _recognize_task_rows(self, worker, task, rows):
        sources = [
            (row, Path(row["local_path"])) for row in rows
            if row.get("local_path") and Path(row["local_path"]).is_file()
        ]
        if not sources:
            raise RuntimeError("没有可用于语音识别的已下载视频")
        output_dir = worker.root / str(task["id"]) / "source-transcripts"
        output_dir.mkdir(parents=True, exist_ok=True)
        texts = []
        for row, source in sources:
            try:
                srt = transcribe(
                    worker.config.get("local_ai", {}), source,
                    output_dir / ("video-%s.srt" % row["id"]),
                    task.get("source_language") or "Chinese",
                )
            except RuntimeError as exc:
                if "没有从原视频中识别到可用语音" not in str(exc):
                    raise
                worker.emit("log", message="视频 %s 没有可识别语音，已跳过" % row["id"])
                continue
            if not srt:
                raise RuntimeError("本地语音识别尚未安装或配置，无法提取原视频中文")
            text = Worker.subtitle_text(srt).strip()
            if text:
                texts.append(text)
        if not texts:
            raise RuntimeError("没有从已下载视频中识别到可用中文")
        updated = dict(task)
        updated["original_transcript"] = "\n".join(texts)
        self.selection_store.update_task(updated)
        return updated, len(texts)

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
                    fallback = existing if existing and existing.is_file() else target
                    if fallback.is_file() and worker.probe_duration(fallback) > 0:
                        self.selection_store.update(
                            row["id"], status="downloaded", local_path=str(fallback),
                            error="重新下载暂时失败，已保留并复用原有完整视频：%s" % exc,
                        )
                        clips.append({
                            "path": fallback, "trim_start": row.get("trim_start") or 0,
                            "trim_end": row.get("trim_end") or 0,
                        })
                        self.events.put(("log", {"message": "视频 %s 重新下载失败，已复用原有完整文件" % row["id"]}))
                        continue
                    self.selection_store.update(row["id"], status="failed", error=str(exc))
                    raise
            if mix_after:
                task = Worker.prepare_edit_workflow(task, len(rows))
                self.selection_store.update_task(task)
                for row in rows:
                    self.selection_store.update(row["id"], status="mixing", error="")
                self.events.put(("selection_changed", {}))
                version_no, mix_dir = create_version_directory(
                    worker.root / str(task["id"]),
                    self.selection_store.next_render_version(task["id"]),
                )
                output, subtitle = worker.compose_video(task, clips, mix_dir)
                self.selection_store.set_task_result(
                    task["id"], output, subtitle or "", status="ready_review",
                    version_no=version_no,
                    source_video_ids=[row["id"] for row in rows],
                )
                for row in rows:
                    self.selection_store.update(row["id"], status="ready_review", error="")
                self.events.put(("selection_mix_ready", {"task": task, "output": str(output)}))
            else:
                self.events.put(("selection_operation_done", {}))
                self.events.put(("log", {
                    "message": "视频下载完成；单条视频可在文案页面点击原声识别",
                }))
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

    def mix_selected_videos(self, selected_ids=None):
        task = self._active_selection_task()
        ids = selected_ids if selected_ids is not None else self._selection_ids(default_all=True)
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先加入至少一个抖音视频")
            return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有选片处理正在运行")
            return
        rows = self.selection_store.list_selected(task["id"], ids)
        if not rows:
            messagebox.showerror(APP_TITLE, "选中的视频已不存在，请重新选择")
            return
        self.selection_busy = True
        threading.Thread(target=self._run_downloads, args=(task, rows, True), daemon=True).start()

    def _voice_profiles(self):
        profiles = default_voice_profiles(
            self.vars["sherpa_model"].get().strip(),
            self.vars["volc_resource_id"].get().strip(),
        )
        profiles.extend(
            dict(profile, editable=True)
            for profile in load_voice_profiles(VOICE_LIBRARY_PATH)
            if profile.get("provider") in ("sherpa", "volcengine")
        )
        return profiles

    def open_voice_manager(self):
        providers = {
            "sherpa": "sherpa-onnx 本地音色", "volcengine": "火山引擎音色",
        }
        dialog = tk.Toplevel(self)
        dialog.title("音色管理")
        dialog.geometry("1080x680")
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=15)
        body.pack(fill="both", expand=True)
        filter_row = ttk.Frame(body)
        filter_row.pack(fill="x", pady=(0, 10))
        ttk.Label(filter_row, text="服务商").pack(side="left")
        provider_filter = tk.StringVar(value="全部")
        provider_box = ttk.Combobox(
            filter_row, textvariable=provider_filter,
            values=("全部", *providers.values()), state="readonly", width=24,
        )
        provider_box.pack(side="left", padx=8)
        ttk.Label(filter_row, text="选择服务商后仅加载对应模型和音色", foreground="#666").pack(side="left")

        columns = (
            "name", "provider", "model_id", "language", "description",
            "voice_id", "source", "kind",
        )
        tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        headings = {
            "name": "音色名称", "provider": "配音服务", "voice_id": "音色 ID",
            "model_id": "模型 / Resource ID", "language": "语种",
            "description": "音色类型",
            "source": "音色来源", "kind": "类型",
        }
        widths = {
            "name": 135, "provider": 120, "model_id": 135, "language": 95,
            "description": 90, "voice_id": 240, "source": 145, "kind": 55,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="w")
        tree.pack(fill="both", expand=True)
        help_text = tk.StringVar(value="选择音色后可打开官方来源，查看或添加可用音色。")
        ttk.Label(body, textvariable=help_text, foreground="#666", wraplength=820).pack(
            fill="x", pady=(8, 0),
        )
        profile_map = {}

        def refresh(select_id=None):
            tree.delete(*tree.get_children())
            profile_map.clear()
            for profile in self._voice_profiles():
                selected_provider = provider_filter.get()
                if selected_provider != "全部" and providers.get(profile["provider"]) != selected_provider:
                    continue
                iid = profile["id"]
                if tree.exists(iid):
                    iid += ":duplicate"
                profile_map[iid] = profile
                tree.insert("", "end", iid=iid, values=(
                    profile["name"], providers.get(profile["provider"], profile["provider"]),
                    profile.get("model_id", ""), profile.get("language", ""),
                    profile.get("description", ""),
                    profile["voice_id"], profile["source"],
                    "自定义" if profile.get("editable") else "系统",
                ))
                if profile["id"] == select_id:
                    tree.selection_set(iid)
                    tree.focus(iid)
            if not tree.selection() and tree.get_children():
                first = tree.get_children()[0]
                tree.selection_set(first)
                tree.focus(first)

        def selected_profile():
            selected = tree.selection()
            return profile_map.get(selected[0]) if selected else None

        def update_help(_event=None):
            selected = selected_profile()
            if not selected:
                return
            instructions = {
                "sherpa": "Sherpa 音色 ID 是当前 TTS 模型的 speaker ID 整数；单音色模型用 0，多音色模型按官方模型说明选择。",
                "volcengine": "新版火山引擎音色 ID 是已开通模型支持的 speaker；API Key 与 Resource ID 在连接与配置中填写。",
            }
            help_text.set(instructions.get(selected["provider"], "请从该音色的来源页面获取音色 ID。"))
            language = selected.get("language", "")
            preview_text.set(
                "Hello, welcome to the LightLink voice preview. This is an English voice test."
                if "英语" in language or "English" in language
                else "你好，欢迎使用 LightLink 音色试听。这是一段中文音色测试。"
            )

        provider_box.bind("<<ComboboxSelected>>", lambda _event: (refresh(), update_help()))

        def open_source():
            selected = selected_profile()
            source_url = (selected or {}).get("source_url", "").strip()
            if not source_url:
                messagebox.showinfo(APP_TITLE, "该音色未填写来源网址，请先编辑音色。", parent=dialog)
                return
            try:
                os.startfile(source_url)
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"无法打开音色来源：{exc}", parent=dialog)

        def edit_profile(create=False):
            selected = selected_profile()
            if not create and not selected:
                messagebox.showinfo(APP_TITLE, "请先选择要编辑的音色。", parent=dialog)
                return
            if not create and not selected.get("editable"):
                messagebox.showinfo(APP_TITLE, "系统默认音色不能编辑，可以新增自定义音色。", parent=dialog)
                return
            editor = tk.Toplevel(dialog)
            editor.title("新增音色" if create else "编辑音色")
            editor.geometry("520x390")
            editor.resizable(False, False)
            editor.transient(dialog)
            editor.grab_set()
            form = ttk.Frame(editor, padding=18)
            form.pack(fill="both", expand=True)
            name = tk.StringVar(value="" if create else selected["name"])
            provider = tk.StringVar(value=providers[
                next(iter(providers)) if create else selected["provider"]
            ])
            voice_id = tk.StringVar(value="" if create else selected["voice_id"])
            model_id = tk.StringVar(value=(
                self.vars["volc_resource_id"].get().strip() if create
                else selected.get("model_id", "")
            ))
            language = tk.StringVar(value="" if create else selected.get("language", ""))
            description = tk.StringVar(value="" if create else selected.get("description", ""))
            source = tk.StringVar(value="" if create else selected["source"])
            source_url = tk.StringVar(value="" if create else selected.get("source_url", ""))
            fields = (
                ("音色名称", name, None),
                ("配音服务", provider, tuple(providers.values())),
                ("模型/Resource ID", model_id, None),
                ("音色 ID", voice_id, None),
                ("语种", language, None),
                ("音色说明", description, None),
                ("音色来源", source, ("Sherpa 本地模型", "火山引擎", "自定义")),
                ("来源网址", source_url, None),
            )
            editor_widgets = {}
            for row, (label, variable, choices) in enumerate(fields):
                ttk.Label(form, text=label, width=14).grid(row=row, column=0, sticky="w", pady=7)
                widget = ttk.Combobox(form, textvariable=variable, values=choices) if choices else ttk.Entry(form, textvariable=variable)
                widget.grid(row=row, column=1, sticky="ew", pady=7)
                editor_widgets[label] = widget
            form.columnconfigure(1, weight=1)

            def load_provider_model(_event=None):
                provider_key = next(
                    key for key, label in providers.items() if label == provider.get()
                )
                model_id.set(
                    self.vars["volc_resource_id"].get().strip()
                    if provider_key == "volcengine"
                    else self.vars["sherpa_model"].get().strip()
                )

            editor_widgets["配音服务"].bind("<<ComboboxSelected>>", load_provider_model)
            if create:
                load_provider_model()

            def save_profile():
                try:
                    provider_key = next(key for key, label in providers.items() if label == provider.get())
                    values = {
                        "id": (selected or {}).get("id") or secrets.token_hex(8),
                        "name": name.get().strip(), "provider": provider_key,
                        "voice_id": voice_id.get().strip(), "source": source.get().strip(),
                        "source_url": source_url.get().strip(), "model_id": model_id.get().strip(),
                        "language": language.get().strip(), "description": description.get().strip(),
                    }
                    if not values["name"] or not values["voice_id"] or not values["source"]:
                        raise ValueError("音色名称、音色 ID 和音色来源不能为空")
                    profiles = [
                        item for item in load_voice_profiles(VOICE_LIBRARY_PATH)
                        if item["id"] != values["id"]
                    ]
                    profiles.append(values)
                    save_voice_profiles(VOICE_LIBRARY_PATH, profiles)
                    editor.destroy()
                    refresh(values["id"])
                except Exception as exc:
                    messagebox.showerror(APP_TITLE, str(exc), parent=editor)

            actions = ttk.Frame(form)
            actions.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
            ttk.Button(actions, text="保存", command=save_profile).pack(side="left", padx=4)
            ttk.Button(actions, text="取消", command=editor.destroy).pack(side="left", padx=4)

        def delete_profile():
            selected = selected_profile()
            if not selected or not selected.get("editable"):
                messagebox.showinfo(APP_TITLE, "请选择自定义音色；系统默认音色不能删除。", parent=dialog)
                return
            if not messagebox.askyesno(APP_TITLE, f"删除音色“{selected['name']}”？", parent=dialog):
                return
            save_voice_profiles(VOICE_LIBRARY_PATH, [
                item for item in load_voice_profiles(VOICE_LIBRARY_PATH)
                if item["id"] != selected["id"]
            ])
            refresh()

        def apply_to_project():
            selected = selected_profile()
            task = self._active_selection_task()
            if not selected or not task:
                messagebox.showerror(APP_TITLE, "请先选择音色和当前视频项目。", parent=dialog)
                return
            task.update({
                "tts_provider": selected["provider"], "tts_voice": selected["voice_id"],
                "tts_voice_source": selected["source"],
                "tts_model_id": selected.get("model_id", ""),
            })
            self.selection_store.update_task(task)
            messagebox.showinfo(APP_TITLE, f"已将“{selected['name']}”应用到当前项目。", parent=dialog)

        preview = ttk.LabelFrame(body, text="音色试听", padding=10)
        preview.pack(fill="x", pady=(10, 0))
        preview_text = tk.StringVar(value="你好，欢迎使用 LightLink 音色试听。这是一段中文音色测试。")
        preview_status = tk.StringVar(value="相同音色和文本将直接使用本地缓存")
        ttk.Entry(preview, textvariable=preview_text).pack(side="left", fill="x", expand=True)

        def preview_voice():
            selected = selected_profile()
            text = preview_text.get().strip()
            if not selected or not text:
                messagebox.showerror(APP_TITLE, "请选择音色并输入试听文本。", parent=dialog)
                return
            preview_button.config(state="disabled")
            speech_config = dict(self.config().get("speech", {}))
            if selected["provider"] == "volcengine" and selected.get("model_id"):
                speech_config["volc_resource_id"] = selected["model_id"]
            elif selected["provider"] == "sherpa" and selected.get("model_id"):
                speech_config["sherpa_model"] = selected["model_id"]
            output_dir = app_dir() / "voice-previews"
            output_dir.mkdir(parents=True, exist_ok=True)
            cache_key = hashlib.sha256(json.dumps([
                "v1", selected["provider"], selected.get("model_id", ""),
                selected["voice_id"], text,
            ], ensure_ascii=False).encode("utf-8")).hexdigest()
            suffix = ".mp3" if selected["provider"] == "volcengine" else ".wav"
            output = output_dir / ("preview-" + cache_key + suffix)
            if output.is_file() and output.stat().st_size:
                self.events.put(("voice_preview", {
                    "path": str(output), "button": preview_button,
                    "status": preview_status, "cached": True,
                }))
                return
            preview_status.set("正在调用服务生成试听音频…")

            def run_preview():
                try:
                    result = synthesize(
                        speech_config, selected["provider"], text, output,
                        selected["voice_id"], 1.0, 1.0,
                    )
                    self.events.put(("voice_preview", {
                        "path": str(result), "button": preview_button,
                        "status": preview_status, "cached": False,
                    }))
                except Exception as exc:
                    self.events.put(("voice_preview", {
                        "error": str(exc), "button": preview_button,
                        "status": preview_status,
                    }))

            threading.Thread(target=run_preview, daemon=True).start()

        preview_button = ttk.Button(preview, text="生成并试听", command=preview_voice)
        preview_button.pack(side="left", padx=(10, 0))
        ttk.Label(body, textvariable=preview_status, foreground="#666").pack(fill="x", pady=(4, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="打开音色来源", command=open_source).pack(side="left", padx=3)
        ttk.Button(actions, text="新增", command=lambda: edit_profile(True)).pack(side="left", padx=3)
        ttk.Button(actions, text="编辑", command=edit_profile).pack(side="left", padx=3)
        ttk.Button(actions, text="删除", command=delete_profile).pack(side="left", padx=3)
        ttk.Button(actions, text="应用到当前项目", command=apply_to_project).pack(side="left", padx=12)
        ttk.Button(actions, text="关闭", command=dialog.destroy).pack(side="right", padx=3)
        refresh()
        update_help()
        tree.bind("<<TreeviewSelect>>", update_help)
        tree.bind("<Double-1>", lambda _event: open_source())

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
