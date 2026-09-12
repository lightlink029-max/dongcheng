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
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk

from bitbrowser_adapter import BitBrowserClient
from registration_assistant import EnvironmentMismatch, capture_current_page, prepare_registration
from douyin_adapter import _dpapi, capture_login, has_login, open_keyword_search, self_test
from mumu_adapter import MumuBridge, check_mumu, install_selector_apk
from planning_templates import build_video_plan, fallback_options
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
        self.selection_store = SelectionStore(app_dir() / "media-library-v2.db")
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
        self.registration_tasks = {}
        self.registration_results = {}
        self._build()
        self._load()
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self.after(200, self._drain_events)
        self.after(800, self._poll_clipboard)

    def _build(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        config_tab, tasks_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        registration_tab, selection_tab, log_tab = (
            ttk.Frame(notebook), ttk.Frame(notebook), ttk.Frame(notebook)
        )
        notebook.add(config_tab, text="连接与配置")
        notebook.add(tasks_tab, text="任务列表")
        notebook.add(registration_tab, text="社媒账号注册")
        notebook.add(selection_tab, text="视频生产工作台")
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
                ("ollama_command", "Ollama程序（留空自动检测）", ""),
                ("translation_model", "本地翻译模型", "qwen3:8b"),
                ("whisper_command", "语音识别程序（可选）", ""),
                ("whisper_model", "Whisper模型", "small"),
                ("ai_edit_command", "AI剪辑程序（可选）", ""),
                ("vsr_command", "VSR/STTN适配程序（可选）", ""),
            ]),
            ("语音合成", [
                ("sherpa_command", "sherpa-onnx程序（可选）", ""),
                ("sherpa_model", "sherpa音色模型", ""),
                ("sherpa_tokens", "sherpa Tokens", ""),
                ("sherpa_data_dir", "sherpa数据目录", ""),
                ("volc_api_key", "火山引擎 API Key", ""),
                ("volc_resource_id", "火山 Resource ID", "seed-tts-2.0"),
            ]),
            ("HeyGen口型同步", [
                ("heygen_api_key", "HeyGen API Key", ""),
                ("heygen_mode", "口型质量", "precision"),
            ]),
            ("MuMu选片", [
                ("mumu_adb", "MuMu ADB（可自动检测）", ""),
                ("mumu_player", "MuMu 主程序（可自动检测）", ""),
                ("mumu_serial", "MuMu ADB 地址（留空自动检测）", ""),
            ]),
            ("比特浏览器", [
                ("bitbrowser_url", "Local API 地址", "http://127.0.0.1:54345"),
                ("bitbrowser_token", "API Token（可选）", ""),
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
                show = "*" if key in (
                    "worker_token", "volc_api_key", "bitbrowser_token", "heygen_api_key",
                ) else ""
                ttk.Entry(form, textvariable=var, show=show).grid(row=row, column=1, sticky="ew", pady=8)
                if key == "work_dir":
                    ttk.Button(form, text="选择", command=self._choose_dir).grid(row=row, column=2, padx=8)
                elif key in ("mumu_adb", "mumu_player", "ollama_command"):
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
        bitbrowser_form = config_frames["比特浏览器"]
        bitbrowser_actions = ttk.Frame(bitbrowser_form)
        bitbrowser_actions.grid(row=2, column=1, sticky="w", pady=(8, 12))
        ttk.Button(bitbrowser_actions, text="测试连接", command=self.test_bitbrowser).pack(side="left", padx=(0, 8))
        ttk.Button(bitbrowser_actions, text="同步环境", command=self.sync_bitbrowser_environments).pack(side="left", padx=(0, 8))
        ttk.Button(bitbrowser_actions, text="启动所选环境", command=self.open_bitbrowser_environment).pack(side="left", padx=(0, 8))
        ttk.Button(bitbrowser_actions, text="关闭所选环境", command=self.close_bitbrowser_environment).pack(side="left")
        self.bitbrowser_tree = ttk.Treeview(
            bitbrowser_form, columns=("seq", "name", "platform", "username", "status", "id"),
            show="headings", height=10, selectmode="browse",
        )
        for name, title, width in (
            ("seq", "序号", 60), ("name", "环境名称", 170), ("platform", "平台", 170),
            ("username", "账号", 150), ("status", "状态", 80), ("id", "环境 ID", 260),
        ):
            self.bitbrowser_tree.heading(name, text=title)
            self.bitbrowser_tree.column(name, width=width, anchor="w")
        self.bitbrowser_tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(0, 8))
        bitbrowser_form.rowconfigure(3, weight=1)
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

        registration_header = ttk.Frame(registration_tab, padding=10)
        registration_header.pack(fill="x")
        ttk.Label(
            registration_header,
            text="先强制校验固定 IP、国家和时区；通过后只填写邮箱、名称等非敏感资料。验证码和协议由人工处理。",
        ).pack(side="left")
        ttk.Button(registration_header, text="刷新 Odoo 注册任务", command=self.refresh_registration_tasks).pack(side="right")
        registration_columns = (
            "id", "mode", "platform", "email", "environment", "expected_ip", "country", "timezone", "state", "status",
        )
        self.registration_tree = ttk.Treeview(
            registration_tab, columns=registration_columns, show="headings", selectmode="browse",
        )
        for column, title, width in zip(
            registration_columns,
            ("任务ID", "类型", "平台", "新邮箱", "比特环境", "预期IP", "国家", "时区", "状态", "说明"),
            (70, 80, 90, 190, 170, 130, 60, 150, 130, 260),
        ):
            self.registration_tree.heading(column, text=title)
            self.registration_tree.column(column, width=width, anchor="w")
        registration_scroll = ttk.Scrollbar(registration_tab, orient="horizontal", command=self.registration_tree.xview)
        self.registration_tree.configure(xscrollcommand=registration_scroll.set)
        self.registration_tree.pack(fill="both", expand=True, padx=10)
        registration_scroll.pack(fill="x", padx=10)
        registration_actions = ttk.Frame(registration_tab, padding=10)
        registration_actions.pack(fill="x")
        ttk.Button(registration_actions, text="① 校验环境并打开注册页", command=self.prepare_selected_registration).pack(side="left", padx=(0, 8))
        ttk.Button(registration_actions, text="② 人工验证完成，确认账号", command=self.complete_selected_registration).pack(side="left", padx=(0, 8))
        ttk.Button(registration_actions, text="标记失败", command=self.fail_selected_registration).pack(side="left")
        ttk.Label(
            registration_actions, text="本工具不会读取或上传邮箱密码、Cookie、手机号和 2FA 密钥。",
            foreground="#666",
        ).pack(side="right")

        selection_header = ttk.Frame(selection_tab, padding=10)
        selection_header.pack(fill="x")
        self.selection_title = tk.StringVar(value="请先启动工作节点并领取抖音选片任务")
        ttk.Label(selection_header, textvariable=self.selection_title, font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        ttk.Button(selection_header, text="新建本地项目", command=self.create_local_project).pack(side="left", padx=(15, 3))
        self.selection_task_choice = ttk.Combobox(selection_header, state="readonly", width=34)
        self.selection_task_choice.pack(side="left", padx=8)
        self.selection_task_choice.bind("<<ComboboxSelected>>", self._on_selection_task_choice)

        plan_panel = ttk.LabelFrame(
            selection_tab, text="视频整体方案（始终可见）", padding=(10, 6),
        )
        plan_panel.pack(fill="x", padx=10, pady=(0, 8))
        plan_summary_row = ttk.Frame(plan_panel)
        plan_summary_row.pack(fill="x")
        self.video_plan_summary = tk.StringVar(value="请选择项目；先确认整体视频方案，再逐个完成分镜。")
        ttk.Label(
            plan_summary_row, textvariable=self.video_plan_summary, wraplength=950,
            justify="left", foreground="#333",
        ).pack(side="left", fill="x", expand=True)
        self.storyboard_progress = tk.StringVar(value="分镜进度：0/0")
        ttk.Label(
            plan_summary_row, textvariable=self.storyboard_progress,
            font=("Microsoft YaHei UI", 10, "bold"), foreground="#6f3f64",
        ).pack(side="right", padx=(15, 0))

        plan_navigation = ttk.Frame(plan_panel)
        plan_navigation.pack(fill="x", pady=(6, 0))
        ttk.Label(plan_navigation, text="当前分镜").pack(side="left")
        self.storyboard_choice_var = tk.StringVar()
        self.storyboard_choice = ttk.Combobox(
            plan_navigation, textvariable=self.storyboard_choice_var,
            state="readonly", width=52,
        )
        self.storyboard_choice.pack(side="left", padx=8)
        self.storyboard_choice.bind("<<ComboboxSelected>>", self._on_storyboard_choice)
        self.storyboard_choice_map = {}
        self.current_storyboard_slot_key = ""
        self.plan_detail_button_text = tk.StringVar(value="查看完整方案")
        ttk.Button(
            plan_navigation, textvariable=self.plan_detail_button_text,
            command=self.show_plan_details,
        ).pack(side="right")
        ttk.Label(
            plan_navigation, text="先选分镜目标，再到下方制作或选片。",
            foreground="#666",
        ).pack(side="left", padx=12)

        self.plan_detail = ttk.LabelFrame(plan_panel, text="完整分镜清单", padding=8)
        self.storyboard_tree = ttk.Treeview(
            self.plan_detail,
            columns=("sequence", "name", "purpose", "visual", "narration", "duration", "state"),
            show="headings", selectmode="browse", height=4,
        )
        for name, title, width in (
            ("sequence", "顺序", 55), ("name", "分镜名称", 135),
            ("purpose", "叙事作用", 150), ("visual", "画面要求", 260),
            ("narration", "对应文案", 260), ("duration", "目标", 65),
            ("state", "状态", 85),
        ):
            self.storyboard_tree.heading(name, text=title)
            self.storyboard_tree.column(name, width=width, anchor="w")
        self.storyboard_tree.pack(fill="x")
        self.storyboard_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_target_shot_label())

        selection_workflow = ttk.Notebook(selection_tab)
        selection_workflow.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        source_page = ttk.Frame(selection_workflow, padding=10)
        library_page = ttk.Frame(selection_workflow, padding=10)
        assembly_page = ttk.Frame(selection_workflow, padding=10)
        review_page = ttk.Frame(selection_workflow, padding=10)
        selection_workflow.add(source_page, text="① 原始素材制作分镜")
        selection_workflow.add(library_page, text="② 从分镜库选成片")
        selection_workflow.add(assembly_page, text="③ 成片排序合成")
        selection_workflow.add(review_page, text="④ 审核回传")
        self.selection_workflow = selection_workflow
        self.selection_source_page = source_page
        self.selection_library_page = library_page
        self.selection_assembly_page = assembly_page
        self.selection_review_page = review_page

        source_header = ttk.Frame(source_page)
        source_header.pack(fill="x", pady=(0, 8))
        self.clipboard_listening = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            source_header, text="自动收集剪贴板中的抖音链接", variable=self.clipboard_listening,
        ).pack(side="right")
        ttk.Label(
            source_header,
            text=(
                "全局原始素材库：素材不属于当前项目，可跨视频重复制作分镜；"
                "完成后只存入全局分镜素材库，不会直接加入成片。"
            ),
        ).pack(side="left")
        self.production_shot_label = tk.StringVar(value="尚未选择本次要制作的分镜要求")
        source_target = ttk.LabelFrame(source_page, text="当前制作目标（来自视频方案）", padding=7)
        source_target.pack(fill="x", pady=(0, 8))
        ttk.Label(
            source_target, textvariable=self.production_shot_label,
            font=("Microsoft YaHei UI", 10, "bold"), foreground="#6f3f64",
        ).pack(side="left")
        ttk.Button(
            source_target, text="查看完整方案",
            command=self.show_plan_details,
        ).pack(side="right")

        ttk.Style(self).configure("Media.Treeview", rowheight=78)
        selection_columns = (
            "clip_name", "source_kind", "clip_type", "caption", "duration", "status", "trim",
            "subtitle_cleanup", "final_source", "copyright", "url", "error",
        )
        self.selection_tree = ttk.Treeview(
            source_page, columns=selection_columns, show="tree headings",
            selectmode="extended", style="Media.Treeview", height=5,
        )
        self.selection_tree.heading("#0", text="封面")
        self.selection_tree.column("#0", width=100, minwidth=100, stretch=False, anchor="center")
        titles = (
            "素材/片段名称", "来源", "片段类型", "原视频文案", "时长", "处理状态", "入点-出点",
            "原字幕处理", "最终使用", "版权", "分享链接", "错误",
        )
        widths = (180, 95, 110, 280, 75, 90, 100, 110, 125, 90, 260, 180)
        for column, title, width in zip(selection_columns, titles, widths):
            self.selection_tree.heading(column, text=title)
            self.selection_tree.column(column, width=width, anchor="w")
        selection_scroll = ttk.Scrollbar(
            source_page, orient="horizontal", command=self.selection_tree.xview,
        )
        self.selection_tree.configure(xscrollcommand=selection_scroll.set)
        self.selection_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_selection_summary())
        self.selection_tree.bind("<Double-1>", lambda _event: self.preview_selected_video())

        selection_controls = ttk.LabelFrame(source_page, text="视频素材操作（按流程）", padding=8)
        selection_controls.pack(fill="x", pady=(0, 8))
        control_groups = ttk.Frame(selection_controls)
        control_groups.pack(fill="x")
        for column in range(3):
            control_groups.columnconfigure(column, weight=1)

        add_controls = ttk.LabelFrame(control_groups, text="A. 素材导入", padding=(7, 5))
        add_controls.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=(0, 5))
        ttk.Button(
            add_controls, text="从剪贴板添加", command=self.add_selection_from_clipboard,
        ).pack(side="left", padx=3)
        ttk.Button(
            add_controls, text="手工添加链接", command=self.add_selection_manually,
        ).pack(side="left", padx=3)
        ttk.Button(
            add_controls, text="添加本地视频", command=self.add_local_videos,
        ).pack(side="left", padx=3)
        ttk.Button(
            add_controls, text="下载所选", command=self.redownload_selected_videos,
        ).pack(side="left", padx=3)

        clip_controls = ttk.LabelFrame(control_groups, text="B. 人工初剪与分类", padding=(7, 5))
        clip_controls.grid(row=0, column=1, sticky="ew", padx=5, pady=(0, 5))
        ttk.Button(
            clip_controls, text="打开初剪 / 分类 / 字幕", command=self.edit_selected_clip,
        ).pack(side="left", padx=3)
        ttk.Button(
            clip_controls, text="只选口播人脸", command=self.select_talking_face_clips,
        ).pack(side="left", padx=3)
        ttk.Button(clip_controls, text="全选", command=self.select_all_videos).pack(side="left", padx=3)

        copy_controls = ttk.LabelFrame(control_groups, text="C. 文案翻译、配音与口型", padding=(7, 5))
        copy_controls.grid(row=0, column=2, sticky="ew", padx=(5, 0), pady=(0, 5))
        ttk.Button(
            copy_controls, text="确认文案与项目音色", command=self.edit_active_project,
        ).pack(side="left", padx=3)
        ttk.Button(
            copy_controls, text="生成所选片段", command=self.process_selected_clip,
        ).pack(side="left", padx=3)

        self.selection_summary = tk.StringVar(value="0 条")
        summary_row = ttk.Frame(selection_controls)
        summary_row.pack(fill="x", pady=(6, 0))
        ttk.Label(
            summary_row, textvariable=self.selection_summary, foreground="#555",
        ).pack(side="left")
        ttk.Button(
            summary_row, text="打开素材文件夹", command=self.open_selection_folder,
        ).pack(side="right", padx=3)
        ttk.Button(
            summary_row, text="进入第②步：从分镜库选择成片素材 →",
            command=lambda: selection_workflow.select(library_page),
        ).pack(side="right", padx=8)
        selection_scroll.pack(side="bottom", fill="x", pady=(0, 8))
        self.selection_tree.pack(fill="both", expand=True, pady=(0, 10))

        assembly_header = ttk.Frame(assembly_page)
        assembly_header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            assembly_header, text="只排列已完成的分镜；这里不再翻译、去字幕或调用 HeyGen",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side="left")
        ttk.Button(
            assembly_header, text="进入第④步：审核回传 →",
            command=lambda: selection_workflow.select(review_page),
        ).pack(side="right")
        assembly_actions = ttk.LabelFrame(assembly_page, text="合成时间线", padding=8)
        assembly_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(assembly_actions, text="全选可合成分镜", command=self.select_all_assembly).pack(side="left", padx=3)
        ttk.Button(assembly_actions, text="上移", command=lambda: self.move_assembly_clips(-1)).pack(side="left", padx=3)
        ttk.Button(assembly_actions, text="下移", command=lambda: self.move_assembly_clips(1)).pack(side="left", padx=3)
        ttk.Button(assembly_actions, text="移出本次合成", command=self.remove_assembly_clips).pack(side="left", padx=3)
        ttk.Button(assembly_actions, text="预览分镜", command=self.preview_assembly_clip).pack(side="left", padx=12)
        ttk.Button(
            assembly_actions, text="生成最终审核稿", command=self.mix_assembly_clips,
        ).pack(side="right", padx=3)
        ttk.Button(
            assembly_actions, text="设置背景音乐 / 导出比例", command=self.edit_active_project,
        ).pack(side="right", padx=3)
        self.assembly_tree = ttk.Treeview(
            assembly_page,
            columns=("sequence", "shot", "name", "kind", "duration", "voice", "path"),
            show="headings", selectmode="extended", style="Media.Treeview",
        )
        for name, title, width in (
            ("sequence", "顺序", 55), ("shot", "对应分镜", 150),
            ("name", "成品片段", 180), ("kind", "处理方式", 135),
            ("duration", "时长", 70), ("voice", "项目音色", 150),
            ("path", "本地文件", 360),
        ):
            self.assembly_tree.heading(name, text=title)
            self.assembly_tree.column(name, width=width, anchor="w")
        self.assembly_tree.pack(fill="both", expand=True)
        self.assembly_tree.bind("<Double-1>", lambda _event: self.preview_assembly_clip())

        project_actions = ttk.LabelFrame(review_page, text="项目文件管理", padding=8)
        project_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(project_actions, text="打开项目目录", command=self.open_project_folder).pack(side="left", padx=5)
        ttk.Button(project_actions, text="删除本地项目", command=self.delete_local_project).pack(side="left", padx=5)
        ttk.Label(project_actions, text="独立本地项目只保存在本机，不会自动上传。", foreground="#666").pack(side="left", padx=18)

        review_sources = ttk.LabelFrame(review_page, text="当前项目使用的视频素材", padding=8)
        review_sources.pack(fill="both", expand=True)
        self.review_source_tree = ttk.Treeview(
            review_sources, columns=("video_id", "mix_source", "path"), show="headings", height=6,
        )
        for name, title, width in (
            ("video_id", "视频ID", 190), ("mix_source", "混剪实际使用", 140),
            ("path", "实际文件", 680),
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

        library_header = ttk.Frame(library_page)
        library_header.pack(fill="x")
        ttk.Label(
            library_header,
            text="按当前视频方案，从本地分镜素材库选择成片所需画面",
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side="left")
        ttk.Button(library_header, text="刷新素材库", command=self._refresh_media_library).pack(side="right", padx=4)
        ttk.Button(library_header, text="同步索引到 Odoo", command=self.sync_media_library).pack(side="right", padx=4)
        self.target_shot_label = tk.StringVar(value="尚未选择要填充的成片分镜")
        target_shot = ttk.LabelFrame(library_page, text="当前要填充的成片分镜", padding=8)
        target_shot.pack(fill="x", pady=(0, 8))
        ttk.Label(
            target_shot, textvariable=self.target_shot_label,
            font=("Microsoft YaHei UI", 10, "bold"), foreground="#6f3f64",
        ).pack(side="left")
        ttk.Button(
            target_shot, text="查看完整方案",
            command=self.show_plan_details,
        ).pack(side="right")
        library_actions = ttk.Frame(library_page, padding=(0, 0, 0, 8))
        library_actions.pack(fill="x")
        ttk.Button(
            library_actions, text="关联所选素材到当前分镜", command=self.add_library_asset_to_current_shot,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            library_actions, text="预览所选素材", command=self.preview_library_asset,
        ).pack(side="left")
        ttk.Button(
            library_actions, text="进入第③步：查看成片时间线 →",
            command=lambda: selection_workflow.select(assembly_page),
        ).pack(side="right")
        ttk.Label(
            library_actions,
            text="这里的选择才会进入成片；同一素材仍保留在库中，可供其他视频重复使用。",
            foreground="#666",
        ).pack(side="left", padx=18)
        self.library_tree = ttk.Treeview(
            library_page,
            columns=("name", "kind", "clip_type", "role", "track", "scope", "purpose",
                     "duration", "subtitle", "copyright", "path"),
            show="headings", selectmode="browse",
        )
        library_titles = (
            ("name", "素材名称", 190), ("kind", "素材类型", 110),
            ("clip_type", "画面类型", 95), ("role", "经营角色", 100),
            ("track", "项目赛道", 100), ("scope", "内容场景", 110),
            ("purpose", "分镜用途", 120), ("duration", "时长", 65),
            ("subtitle", "字幕", 80), ("copyright", "版权", 85), ("path", "本地文件", 320),
        )
        for name, title, width in library_titles:
            self.library_tree.heading(name, text=title)
            self.library_tree.column(name, width=width, anchor="w")
        library_scroll = ttk.Scrollbar(library_page, orient="horizontal", command=self.library_tree.xview)
        self.library_tree.configure(xscrollcommand=library_scroll.set)
        self.library_tree.pack(fill="both", expand=True, padx=10)
        library_scroll.pack(fill="x", padx=10, pady=(0, 10))
        self.library_tree.bind("<Double-1>", lambda _event: self.preview_library_asset())

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
            "bitbrowser": {
                "url": self.vars["bitbrowser_url"].get().strip(),
                "token": self.vars["bitbrowser_token"].get().strip(),
            },
            "selector_port": self.selector_bridge.port,
            "selector_token": self.selector_token,
            "local_ai": {"ollama_url": self.vars["ollama_url"].get().strip(),
                         "ollama_command": self.vars["ollama_command"].get().strip(),
                         "translation_model": self.vars["translation_model"].get().strip(),
                         "whisper_command": self.vars["whisper_command"].get().strip(),
                         "whisper_model": self.vars["whisper_model"].get().strip(),
                         "ai_edit_command": self.vars["ai_edit_command"].get().strip(),
                         "vsr_command": self.vars["vsr_command"].get().strip()},
            "speech": {
                "sherpa_command": self.vars["sherpa_command"].get().strip(),
                "sherpa_model": self.vars["sherpa_model"].get().strip(),
                "sherpa_tokens": self.vars["sherpa_tokens"].get().strip(),
                "sherpa_data_dir": self.vars["sherpa_data_dir"].get().strip(),
                "volc_api_key": self.vars["volc_api_key"].get().strip(),
                "volc_resource_id": self.vars["volc_resource_id"].get().strip(),
            },
            "heygen": {
                "api_key": self.vars["heygen_api_key"].get().strip(),
                "mode": self.vars["heygen_mode"].get().strip() or "precision",
                "poll_seconds": 10,
                "timeout_seconds": 3600,
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
            bitbrowser = dict(persisted.get("bitbrowser", {}))
            bitbrowser_token = bitbrowser.pop("token", "")
            if bitbrowser_token:
                bitbrowser["token_dpapi"] = base64.b64encode(
                    _dpapi(bitbrowser_token.encode("utf-8"), True)
                ).decode("ascii")
            persisted["bitbrowser"] = bitbrowser
            heygen = dict(persisted.get("heygen", {}))
            heygen_api_key = heygen.pop("api_key", "")
            if heygen_api_key:
                heygen["api_key_dpapi"] = base64.b64encode(
                    _dpapi(heygen_api_key.encode("utf-8"), True)
                ).decode("ascii")
            persisted["heygen"] = heygen
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
                bitbrowser = dict(data.get("bitbrowser", {}))
                bitbrowser_token = bitbrowser.get("token_dpapi")
                if bitbrowser_token:
                    bitbrowser["token"] = _dpapi(
                        base64.b64decode(bitbrowser_token), False,
                    ).decode("utf-8")
                heygen = dict(data.get("heygen", {}))
                heygen_api_key = heygen.get("api_key_dpapi")
                if heygen_api_key:
                    heygen["api_key"] = _dpapi(
                        base64.b64decode(heygen_api_key), False,
                    ).decode("utf-8")
                flat = dict(data); flat.update(data.get("local_ai", {})); flat.update(speech)
                flat.update({"bitbrowser_url": bitbrowser.get("url", ""),
                             "bitbrowser_token": bitbrowser.get("token", "")})
                flat.update({"heygen_api_key": heygen.get("api_key", ""),
                             "heygen_mode": heygen.get("mode", "precision")})
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

    def _bitbrowser_client(self):
        return BitBrowserClient(
            self.vars["bitbrowser_url"].get().strip(),
            self.vars["bitbrowser_token"].get().strip(),
        )

    def test_bitbrowser(self):
        if not self.save(quiet=True): return
        try:
            client = self._bitbrowser_client()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        def run():
            try:
                client.health()
                self.events.put(("bitbrowser_connection", {"ok": True}))
            except Exception as exc:
                self.events.put(("bitbrowser_connection", {"ok": False, "error": str(exc)}))
        threading.Thread(target=run, daemon=True).start()

    def sync_bitbrowser_environments(self, quiet=False):
        if not self.save(quiet=True): return
        try:
            client = self._bitbrowser_client()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        worker_config = self.config()
        worker = Worker(worker_config) if worker_config.get("worker_token") else None
        def run():
            try:
                environments = client.list_browsers()
                odoo_error = ""
                if worker:
                    try:
                        worker.sync_bitbrowser_environments(environments)
                    except Exception as exc:
                        odoo_error = str(exc)
                self.events.put(("bitbrowser_sync", {
                    "ok": True, "environments": environments, "quiet": quiet,
                    "odoo_error": odoo_error, "odoo_synced": bool(worker and not odoo_error),
                }))
            except Exception as exc:
                self.events.put(("bitbrowser_sync", {
                    "ok": False, "error": str(exc), "quiet": quiet,
                }))
        threading.Thread(target=run, daemon=True).start()

    def _selected_bitbrowser_id(self):
        selected = self.bitbrowser_tree.selection()
        if len(selected) != 1:
            raise ValueError("请先在列表中选择一个比特环境")
        return str(self.bitbrowser_tree.item(selected[0], "values")[-1])

    def _run_bitbrowser_environment_action(self, operation):
        try:
            browser_id = self._selected_bitbrowser_id()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not self.save(quiet=True): return
        try:
            client = self._bitbrowser_client()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        def run():
            try:
                result = (
                    client.open_browser(browser_id) if operation == "open"
                    else client.close_browser(browser_id)
                )
                self.events.put(("bitbrowser_action", {
                    "ok": True, "operation": operation, "id": browser_id, "result": result,
                }))
            except Exception as exc:
                self.events.put(("bitbrowser_action", {
                    "ok": False, "operation": operation, "id": browser_id, "error": str(exc),
                }))
        threading.Thread(target=run, daemon=True).start()

    def open_bitbrowser_environment(self):
        self._run_bitbrowser_environment_action("open")

    def close_bitbrowser_environment(self):
        self._run_bitbrowser_environment_action("close")

    def _render_bitbrowser_environments(self, environments):
        self.bitbrowser_tree.delete(*self.bitbrowser_tree.get_children())
        for browser in environments:
            raw_status = browser.get("isOpen", browser.get("opened", browser.get("status", "")))
            opened = raw_status is True or str(raw_status).lower() in (
                "1", "true", "open", "opened", "running",
            )
            self.bitbrowser_tree.insert("", "end", values=(
                browser.get("seq", ""), browser.get("name", ""),
                browser.get("platform", browser.get("platformName", "")),
                browser.get("userName", browser.get("username", "")),
                "已启动" if opened else "已关闭",
                browser.get("id", browser.get("browserId", "")),
            ))

    def _selected_registration_task(self):
        selected = self.registration_tree.selection()
        if len(selected) != 1:
            raise ValueError("请先选择一个社媒账号注册任务")
        task_id = int(self.registration_tree.item(selected[0], "values")[0])
        task = self.registration_tasks.get(task_id)
        if not task:
            raise ValueError("任务已刷新，请重新选择")
        return task

    def _render_registration_tasks(self, tasks):
        self.registration_tree.delete(*self.registration_tree.get_children())
        self.registration_tasks = {int(task["id"]): task for task in tasks}
        state_labels = {
            "ready": "待执行", "environment_check": "环境检查",
            "awaiting_verification": "等待人工验证",
        }
        for task in tasks:
            self.registration_tree.insert("", "end", values=(
                task.get("id"), "替换账号" if task.get("task_mode") == "replace" else "新注册",
                task.get("platform", ""), task.get("email", ""),
                task.get("environment_name", task.get("environment_id", "")),
                task.get("expected_ip", ""), task.get("expected_country_code", ""),
                task.get("expected_timezone", ""), state_labels.get(task.get("state"), task.get("state", "")),
                task.get("status_message", ""),
            ))

    def refresh_registration_tasks(self, quiet=False):
        if not self.save(quiet=True):
            return
        if not self.vars["worker_token"].get().strip():
            if not quiet:
                messagebox.showerror(APP_TITLE, "请先配置 Odoo 工作节点令牌")
            return
        def run():
            try:
                tasks = Worker(self.config()).registration_tasks()
                self.events.put(("registration_tasks", {"ok": True, "tasks": tasks, "quiet": quiet}))
            except Exception as exc:
                self.events.put(("registration_tasks", {"ok": False, "error": str(exc), "quiet": quiet}))
        threading.Thread(target=run, daemon=True).start()

    def prepare_selected_registration(self):
        try:
            task = self._selected_registration_task()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not self.save(quiet=True):
            return
        worker_config = self.config()
        bitbrowser_url = self.vars["bitbrowser_url"].get().strip()
        bitbrowser_token = self.vars["bitbrowser_token"].get().strip()
        def run():
            worker = Worker(worker_config)
            try:
                worker.start_registration(task["id"])
                screenshot = app_dir() / "registration" / ("task-%s-prepared.png" % task["id"])
                actual = prepare_registration(
                    BitBrowserClient(bitbrowser_url, bitbrowser_token), task, screenshot,
                )
                worker.report_registration_environment(task["id"], actual)
                self.events.put(("registration_prepared", {"ok": True, "task": task, "actual": actual}))
            except EnvironmentMismatch as exc:
                try:
                    worker.report_registration_environment(task["id"], exc.actual)
                except Exception:
                    pass
                self.events.put(("registration_prepared", {"ok": False, "error": str(exc)}))
            except Exception as exc:
                self.events.put(("registration_prepared", {"ok": False, "error": str(exc)}))
        threading.Thread(target=run, daemon=True).start()

    def complete_selected_registration(self):
        try:
            task = self._selected_registration_task()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if task.get("state") != "awaiting_verification" and task["id"] not in self.registration_results:
            messagebox.showerror(APP_TITLE, "请先完成环境校验并在浏览器中完成人工验证码、协议和身份验证")
            return
        username = simpledialog.askstring(APP_TITLE, "请输入注册成功后的平台用户名：", parent=self)
        if not username:
            return
        profile_url = simpledialog.askstring(APP_TITLE, "请输入账号主页链接：", parent=self)
        if not profile_url:
            return
        platform_account_id = simpledialog.askstring(APP_TITLE, "请输入平台账号 ID（可留空）：", parent=self) or ""
        worker_config = self.config()
        bitbrowser_url = self.vars["bitbrowser_url"].get().strip()
        bitbrowser_token = self.vars["bitbrowser_token"].get().strip()
        def run():
            try:
                screenshot = app_dir() / "registration" / ("task-%s-complete.png" % task["id"])
                capture_current_page(
                    BitBrowserClient(bitbrowser_url, bitbrowser_token), task["environment_id"], screenshot,
                )
                Worker(worker_config).complete_registration(
                    task["id"], username, profile_url, platform_account_id, screenshot,
                )
                self.events.put(("registration_completed", {"ok": True, "task": task}))
            except Exception as exc:
                self.events.put(("registration_completed", {"ok": False, "error": str(exc)}))
        threading.Thread(target=run, daemon=True).start()

    def fail_selected_registration(self):
        try:
            task = self._selected_registration_task()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        reason = simpledialog.askstring(APP_TITLE, "请输入失败原因：", parent=self)
        if not reason:
            return
        worker_config = self.config()
        def run():
            try:
                Worker(worker_config).fail_registration(task["id"], reason)
                self.events.put(("registration_failed", {"ok": True}))
            except Exception as exc:
                self.events.put(("registration_failed", {"ok": False, "error": str(exc)}))
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
        for task in self.selection_store.list_tasks():
            if int(task.get("id") or 0) > 0 and task.get("local_status") == "processing":
                self.pending_selections[int(task["id"])] = task
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
                task = worker.claim()
                if task and task["type"] == "douyin_select":
                    self.events.put(("log", {"message": "已领取 Odoo 选片任务 %s" % task["id"]}))
                    try:
                        worker.prepare_douyin_selection(task)
                        self.pending_selections[task["id"]] = task
                    except Exception as exc:
                        worker.fail_task(task, exc)
                elif task:
                    self.events.put(("log", {"message": "已领取 Odoo 生成任务 %s" % task["id"]}))
                    worker.process(task)
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
                elif event == "bitbrowser_connection":
                    if data["ok"]:
                        messagebox.showinfo(APP_TITLE, "比特 Local API 连接成功")
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "比特 Local API 连接失败")
                elif event == "bitbrowser_sync":
                    if data["ok"]:
                        self._render_bitbrowser_environments(data["environments"])
                        self.write_log("已同步 %s 个比特浏览器环境" % len(data["environments"]))
                        if data.get("odoo_synced"):
                            self.write_log("比特环境已同步到 Odoo")
                        elif data.get("odoo_error"):
                            self.write_log("比特环境同步到 Odoo 失败：" + data["odoo_error"])
                        if not data.get("quiet"):
                            suffix = "\n已同步到 Odoo" if data.get("odoo_synced") else (
                                "\n本地已同步，但 Odoo 同步失败：" + data["odoo_error"]
                                if data.get("odoo_error") else ""
                            )
                            messagebox.showinfo(APP_TITLE, "环境同步完成，共 %s 个%s" % (
                                len(data["environments"]), suffix,
                            ))
                    elif not data.get("quiet"):
                        messagebox.showerror(APP_TITLE, data.get("error") or "比特环境同步失败")
                    else:
                        self.write_log("比特环境同步失败：" + (data.get("error") or "未知错误"))
                elif event == "bitbrowser_action":
                    if data["ok"]:
                        action = "启动" if data["operation"] == "open" else "关闭"
                        result_data = data.get("result", {}).get("data", {})
                        endpoint = result_data.get("http") or result_data.get("ws") or ""
                        self.write_log("比特环境 %s 已%s%s" % (
                            data["id"], action, ("，调试地址：" + endpoint) if endpoint else "",
                        ))
                        messagebox.showinfo(APP_TITLE, "比特环境已%s" % action)
                        self.sync_bitbrowser_environments(quiet=True)
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "比特环境操作失败")
                elif event == "registration_tasks":
                    if data["ok"]:
                        self._render_registration_tasks(data["tasks"])
                        if not data.get("quiet"):
                            self.write_log("已读取 %s 个待处理社媒注册任务" % len(data["tasks"]))
                    elif not data.get("quiet"):
                        messagebox.showerror(APP_TITLE, data.get("error") or "读取注册任务失败")
                elif event == "registration_prepared":
                    if data["ok"]:
                        task = data["task"]
                        self.registration_results[task["id"]] = data["actual"]
                        actual = data["actual"]
                        messagebox.showinfo(
                            APP_TITLE,
                            "环境校验通过，注册页已打开并填写非敏感资料。\n"
                            "实际 IP：%s\n国家：%s\n时区：%s\n\n"
                            "请人工处理验证码、协议确认和身份验证。" % (
                                actual["ip"], actual["country"], actual["timezone"],
                            ),
                        )
                        self.refresh_registration_tasks(quiet=True)
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "注册页准备失败")
                        self.refresh_registration_tasks(quiet=True)
                elif event == "registration_completed":
                    if data["ok"]:
                        self.registration_results.pop(data["task"]["id"], None)
                        messagebox.showinfo(APP_TITLE, "注册结果已回传 Odoo，账号状态已设为“可发布”")
                        self.refresh_registration_tasks(quiet=True)
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "注册结果回传失败")
                elif event == "registration_failed":
                    if data["ok"]:
                        messagebox.showinfo(APP_TITLE, "任务已标记失败")
                        self.refresh_registration_tasks(quiet=True)
                    else:
                        messagebox.showerror(APP_TITLE, data.get("error") or "失败状态回传失败")
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
                elif event == "media_library_synced":
                    messagebox.showinfo(
                        APP_TITLE, "已将 %s 条本地素材索引同步到 Odoo。" % data.get("count", 0),
                    )
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
                elif event == "clip_process_done":
                    self.selection_busy = False
                    self._refresh_selection_tree()
                    messagebox.showinfo(
                        APP_TITLE,
                        "%s已生成并保存到本地分镜素材库。\n"
                        "请到第②步按当前视频方案选择；本次加工不会自动加入成片。" %
                        data.get("kind", "处理片段"),
                    )
                elif event == "clip_process_error":
                    self.selection_busy = False
                    self._refresh_selection_tree()
                    messagebox.showerror(APP_TITLE, data.get("error") or "片段生成失败")
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
                elif event == "subtitle_cleanup_warning":
                    messagebox.showwarning(APP_TITLE, data.get("message") or "去字幕失败，已保留原始素材")
                elif event == "subtitle_cleanup_preview":
                    button = data.get("button")
                    try:
                        if button and button.winfo_exists():
                            button.config(state="normal")
                    except tk.TclError:
                        pass
                    if data.get("error"):
                        messagebox.showerror(APP_TITLE, data["error"])
                    else:
                        try:
                            os.startfile(data["path"])
                        except OSError as exc:
                            messagebox.showerror(APP_TITLE, "5秒预览无法播放：" + str(exc))
                elif event == "subtitle_cleanup_batch_done":
                    self.selection_busy = False
                    button = data.get("button")
                    try:
                        if button and button.winfo_exists():
                            button.config(state="normal")
                    except tk.TclError:
                        pass
                    self._refresh_selection_tree()
                    if data.get("errors"):
                        messagebox.showwarning(
                            APP_TITLE,
                            "已处理 %s 条，失败 %s 条。原视频均已保留。\n%s" % (
                                len(data.get("paths") or []), len(data["errors"]),
                                "\n".join(data["errors"][:5]),
                            ),
                        )
                    elif data.get("paths"):
                        messagebox.showinfo(
                            APP_TITLE,
                            "完整清理素材已生成，可点击“查看清理后素材”再次打开。",
                        )
                        os.startfile(data["paths"][0] if len(data["paths"]) == 1 else data["folder"])
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
            self.current_storyboard_slot_key = ""
            self._refresh_selection_tree()
            self.selection_workflow.select(self.selection_source_page)
        except ValueError:
            pass

    def show_plan_details(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showinfo(APP_TITLE, "请先选择或新建一个视频项目")
            return
        dialog = tk.Toplevel(self)
        dialog.title("视频整体方案与分镜关联")
        dialog.transient(self)
        dialog.geometry("1160x560")
        dialog.minsize(900, 460)
        ttk.Label(
            dialog, text=task.get("video_plan_summary") or "当前项目尚未填写视频整体方案",
            wraplength=1080, justify="left", font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(fill="x", padx=15, pady=12)
        columns = ("sequence", "name", "purpose", "visual", "narration", "duration", "asset", "state")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", selectmode="browse")
        for name, title, width in (
            ("sequence", "顺序", 55), ("name", "分镜名称", 120),
            ("purpose", "叙事作用", 125), ("visual", "画面要求", 260),
            ("narration", "对应文案", 220), ("duration", "目标", 60),
            ("asset", "已关联素材", 150), ("state", "状态", 75),
        ):
            tree.heading(name, text=title)
            tree.column(name, width=width, anchor="w")
        assets = {item["asset_uuid"]: item for item in self.selection_store.list_assets()}
        state_labels = {
            "missing": "缺少素材", "producing": "制作中", "ready": "已有候选",
            "selected": "已关联",
        }
        for row in self.selection_store.list_storyboard(task["id"]):
            asset = assets.get(row.get("selected_asset_uuid") or "") or {}
            tree.insert("", "end", iid=row["slot_key"], values=(
                row["sequence"], row["name"], row.get("purpose") or "—",
                row.get("visual_requirement") or "—", row.get("narration") or "—",
                "%g秒" % float(row.get("target_duration") or 0),
                asset.get("name") or "尚未关联", state_labels.get(row["state"], row["state"]),
            ))
        tree.pack(fill="both", expand=True, padx=15)
        if self.current_storyboard_slot_key and tree.exists(self.current_storyboard_slot_key):
            tree.selection_set(self.current_storyboard_slot_key)
            tree.see(self.current_storyboard_slot_key)

        def choose_slot():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(APP_TITLE, "请选择一条分镜", parent=dialog)
                return
            self.current_storyboard_slot_key = selected[0]
            if self.storyboard_tree.exists(selected[0]):
                self.storyboard_tree.selection_set(selected[0])
            self._update_target_shot_label()
            dialog.destroy()

        actions = ttk.Frame(dialog, padding=15)
        actions.pack(fill="x")
        ttk.Label(
            actions, text="每个画面要求只关联一个分镜素材；更换关联不会删除素材库原件。",
            foreground="#666",
        ).pack(side="left")
        ttk.Button(actions, text="选择此分镜并关闭", command=choose_slot).pack(side="right", padx=5)
        ttk.Button(actions, text="关闭", command=dialog.destroy).pack(side="right", padx=5)
        tree.bind("<Double-1>", lambda _event: choose_slot())

    def _on_storyboard_choice(self, _event=None):
        slot_key = self.storyboard_choice_map.get(self.storyboard_choice_var.get(), "")
        if not slot_key:
            return
        self.current_storyboard_slot_key = slot_key
        if self.storyboard_tree.exists(slot_key):
            self.storyboard_tree.selection_set(slot_key)
            self.storyboard_tree.see(slot_key)
        self._update_target_shot_label()

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

    def _project_dialog(self, task=None, initial_tab=None):
        existing = task or {}
        if existing.get("id") and existing.get("id") == self.selection_task_id:
            task_rows = self.selection_store.get_many(self._selection_ids())
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
        cleanup_mode_choices = {
            "quick": "快速遮盖（无需AI）",
            "ai_auto": "AI无痕（自动识别）",
            "ai_manual": "AI无痕（手工框选）",
        }
        cleanup_engine_choices = {"sttn": "VSR + STTN（时序修复，推荐）"}
        cleanup_quality_choices = {"fast": "快速", "standard": "标准", "high": "高质量"}
        quick_method_choices = {"blur": "模糊", "crop": "裁切", "cover": "底色覆盖"}
        dialog = tk.Toplevel(self)
        dialog.title("编辑视频项目" if task else "新建本地视频项目")
        dialog.transient(self)
        dialog.update_idletasks()
        width = min(1180, max(900, dialog.winfo_screenwidth() - 100))
        height = min(820, max(650, dialog.winfo_screenheight() - 140))
        x = max(20, (dialog.winfo_screenwidth() - width) // 2)
        y = max(20, (dialog.winfo_screenheight() - height) // 2)
        dialog.geometry("%sx%s+%s+%s" % (width, height, x, y))
        dialog.minsize(min(980, width), min(700, height))
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True)
        project_notebook = ttk.Notebook(body)
        project_notebook.pack(fill="both", expand=True, padx=12, pady=12)
        source_form = ttk.Frame(project_notebook, padding=16)
        content_form = ttk.Frame(project_notebook, padding=16)
        output_form = ttk.Frame(project_notebook, padding=16)
        cleanup_form = ttk.Frame(project_notebook, padding=16)
        project_notebook.add(source_form, text="基础与素材")
        project_notebook.add(content_form, text="文案翻译与校验")
        project_notebook.add(output_form, text="剪辑、配音与导出")
        if task:
            project_notebook.select(content_form)
        else:
            project_notebook.select(source_form)
        for page in (source_form, content_form, output_form, cleanup_form):
            page.columnconfigure(1, weight=1)

        def voice_label(profile):
            details = []
            for value in (profile.get("language"), profile.get("description")):
                value = str(value or "").strip()
                if value and value not in details:
                    details.append(value)
            return " · ".join([profile["name"], *details])

        existing_voice_profile = next((
            profile for profile in self._voice_profiles()
            if profile["provider"] == (existing.get("tts_provider") or "none")
            and profile["voice_id"] == (existing.get("tts_voice") or "")
            and (not existing.get("tts_model_id") or profile.get("model_id") == existing.get("tts_model_id"))
        ), None)

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
            "tts_voice": tk.StringVar(value=voice_label(existing_voice_profile) if existing_voice_profile else ""),
            "tts_speed": tk.StringVar(value=str(existing.get("tts_speed") or 1.0)),
            "tts_volume": tk.StringVar(value=str(existing.get("tts_volume") or 1.0)),
            "background_music": tk.StringVar(value=existing.get("background_music") or ""),
            "music_volume": tk.StringVar(value=str(existing.get("music_volume") or 0.2)),
            "source_image_path": tk.StringVar(value=existing.get("source_image_path") or ""),
            "remove_hard_subtitles": tk.BooleanVar(value=bool(existing.get("remove_hard_subtitles"))),
            "subtitle_cleanup_mode": tk.StringVar(value=cleanup_mode_choices.get(
                existing.get("subtitle_cleanup_mode") or "quick", cleanup_mode_choices["quick"],
            )),
            "subtitle_cleanup_engine": tk.StringVar(value=cleanup_engine_choices.get(
                existing.get("subtitle_cleanup_engine") or "sttn", cleanup_engine_choices["sttn"],
            )),
            "subtitle_cleanup_quality": tk.StringVar(value=cleanup_quality_choices.get(
                existing.get("subtitle_cleanup_quality") or "standard", cleanup_quality_choices["standard"],
            )),
            "subtitle_quick_method": tk.StringVar(value=quick_method_choices.get(
                existing.get("subtitle_quick_method") or "blur", quick_method_choices["blur"],
            )),
            "subtitle_region": tk.StringVar(value=existing.get("subtitle_region") or "5,72,90,22"),
            "overlay_translation_in_cleanup_region": tk.BooleanVar(value=bool(
                existing.get("overlay_translation_in_cleanup_region", True)
            )),
        }
        local_files = list(existing.get("local_files") or [])

        source_rows = (
            ("项目名称", "name", None), ("搜索关键词", "keywords", None),
            ("原视频语言", "source_language", None),
            ("目标语言", "target_language", None),
            ("参考时长（翻译模式跟随素材）", "duration_seconds", None),
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
                        values=[voice_label(profile) for profile in self._voice_profiles()],
                        state="readonly",
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
                voice_widget["values"] = [voice_label(profile) for profile in profiles]
            available_labels = {voice_label(profile) for profile in profiles}
            if profiles and values["tts_voice"].get().strip() not in available_labels:
                values["tts_voice"].set(voice_label(profiles[0]))
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

        cleanup_box = ttk.LabelFrame(cleanup_form, text="项目级字幕清理默认规则（始终输出新文件）", padding=16)
        cleanup_box.pack(fill="x", pady=(4, 12))
        ttk.Label(
            cleanup_box,
            text="仅作用于逐条设置为“按项目默认”的素材；逐条设置“需要/无需清理”时，以逐条设置为准。",
            foreground="#555",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 9))
        ttk.Checkbutton(
            cleanup_box, text="项目默认：清理所有未单独设置的素材", variable=values["remove_hard_subtitles"],
        ).grid(row=1, column=0, sticky="w", padx=(0, 14), pady=5)
        ttk.Label(cleanup_box, text="模式").grid(row=1, column=1, sticky="e", pady=5)
        cleanup_mode_widget = ttk.Combobox(
            cleanup_box, textvariable=values["subtitle_cleanup_mode"],
            values=tuple(cleanup_mode_choices.values()), state="readonly", width=16,
        )
        cleanup_mode_widget.grid(row=1, column=2, sticky="w", padx=6, pady=5)
        ttk.Label(cleanup_box, text="质量").grid(row=1, column=3, sticky="e", pady=5)
        ttk.Combobox(
            cleanup_box, textvariable=values["subtitle_cleanup_quality"],
            values=tuple(cleanup_quality_choices.values()), state="readonly", width=10,
        ).grid(row=1, column=4, sticky="w", padx=6, pady=5)
        ttk.Label(cleanup_box, text="快速方式").grid(row=2, column=0, sticky="e", pady=5)
        cleanup_quick_widget = ttk.Combobox(
            cleanup_box, textvariable=values["subtitle_quick_method"],
            values=tuple(quick_method_choices.values()), state="readonly", width=14,
        )
        cleanup_quick_widget.grid(row=2, column=1, sticky="w", padx=6, pady=5)
        ttk.Label(cleanup_box, text="AI修复模型").grid(row=2, column=2, sticky="e", pady=5)
        cleanup_engine_widget = ttk.Combobox(
            cleanup_box, textvariable=values["subtitle_cleanup_engine"],
            values=tuple(cleanup_engine_choices.values()), state="disabled", width=28,
        )
        cleanup_engine_widget.grid(row=2, column=3, columnspan=2, sticky="w", padx=6, pady=5)
        ttk.Label(cleanup_box, text="字幕区域 左,上,宽,高（%）").grid(row=3, column=0, sticky="e", pady=5)
        ttk.Entry(cleanup_box, textvariable=values["subtitle_region"], width=20).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=6, pady=5,
        )
        cleanup_box.columnconfigure(3, weight=1)

        def first_cleanup_source():
            for path in local_files:
                candidate = Path(path).expanduser()
                if candidate.is_file():
                    return candidate
            for row in task_rows:
                candidate = Path(row.get("local_path") or "")
                if candidate.is_file():
                    return candidate
            raise RuntimeError("请先添加或下载至少一个本地视频，再框选区域或生成预览")

        def cleanup_task_values():
            return {
                "remove_hard_subtitles": values["remove_hard_subtitles"].get(),
                "subtitle_cleanup_mode": next(
                    key for key, label in cleanup_mode_choices.items()
                    if label == values["subtitle_cleanup_mode"].get()
                ),
                "subtitle_cleanup_engine": next(
                    key for key, label in cleanup_engine_choices.items()
                    if label == values["subtitle_cleanup_engine"].get()
                ),
                "subtitle_cleanup_quality": next(
                    key for key, label in cleanup_quality_choices.items()
                    if label == values["subtitle_cleanup_quality"].get()
                ),
                "subtitle_quick_method": next(
                    key for key, label in quick_method_choices.items()
                    if label == values["subtitle_quick_method"].get()
                ),
                "subtitle_region": values["subtitle_region"].get().strip(),
                "overlay_translation_in_cleanup_region": values[
                    "overlay_translation_in_cleanup_region"
                ].get(),
            }

        def select_subtitle_region():
            try:
                source = first_cleanup_source()
                def apply_region(region):
                    values["subtitle_region"].set(region)
                    if values["subtitle_cleanup_mode"].get() == cleanup_mode_choices["ai_auto"]:
                        values["subtitle_cleanup_mode"].set(cleanup_mode_choices["ai_manual"])
                    values["remove_hard_subtitles"].set(True)
                self._show_subtitle_region_selector(
                    source, values["subtitle_region"].get(), apply_region, dialog,
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        ttk.Button(cleanup_box, text="框选字幕区域", command=select_subtitle_region).grid(
            row=3, column=4, sticky="w", padx=6, pady=5,
        )

        def update_cleanup_mode_controls(_event=None):
            uses_ai = values["subtitle_cleanup_mode"].get() != cleanup_mode_choices["quick"]
            cleanup_engine_widget.configure(state="readonly" if uses_ai else "disabled")
            cleanup_quick_widget.configure(state="disabled" if uses_ai else "readonly")

        cleanup_mode_widget.bind("<<ComboboxSelected>>", update_cleanup_mode_controls)
        update_cleanup_mode_controls()
        ttk.Checkbutton(
            cleanup_box,
            text="将新生成的英文字幕自动放回此框选区域（推荐）",
            variable=values["overlay_translation_in_cleanup_region"],
        ).grid(row=4, column=0, columnspan=5, sticky="w", pady=(8, 2))

        def preview_subtitle_cleanup():
            try:
                if not values["remove_hard_subtitles"].get():
                    raise RuntimeError("请先勾选“去除原视频硬字幕”")
                source = first_cleanup_source()
                preview_dir = app_dir() / "subtitle-cleanup-previews"
                preview_dir.mkdir(parents=True, exist_ok=True)
                output = preview_dir / ("preview-%s.mp4" % secrets.token_hex(6))
                preview_button.config(state="disabled")
                task_values = cleanup_task_values()

                def run_preview():
                    try:
                        worker = Worker(self.config())
                        worker.clean_hard_subtitles(task_values, source, output, preview_seconds=5)
                        self.events.put(("subtitle_cleanup_preview", {
                            "button": preview_button, "path": str(output),
                        }))
                    except Exception as exc:
                        self.events.put(("subtitle_cleanup_preview", {
                            "button": preview_button, "error": str(exc),
                        }))

                threading.Thread(target=run_preview, daemon=True).start()
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        preview_button = ttk.Button(cleanup_box, text="先生成5秒效果预览", command=preview_subtitle_cleanup)
        preview_button.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(
            cleanup_box,
            text="只有AI无痕模式需要VSR + STTN；快速遮盖无需安装AI模型。",
            foreground="#666",
        ).grid(row=5, column=2, columnspan=3, sticky="w", padx=6, pady=(8, 2))

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
        quick_voice = ttk.Combobox(
            voice_bar, textvariable=values["tts_voice"], width=36, state="readonly",
        )
        quick_voice.pack(side="left", padx=6)
        voice_widgets.append(quick_voice)
        quick_provider.bind("<<ComboboxSelected>>", load_provider_voices)
        voice_hint = tk.StringVar()
        ttk.Label(voice_bar, textvariable=voice_hint, foreground="#666").pack(side="left", padx=6)

        def update_voice_hint(*_args):
            selected_label = values["tts_voice"].get().strip()
            provider_key = next(
                (key for key, label in tts_choices.items() if label == values["tts_provider"].get()),
                "none",
            )
            profile = next(
                (item for item in self._voice_profiles()
                 if item["provider"] == provider_key and voice_label(item) == selected_label),
                None,
            )
            voice_hint.set(f"音色 ID：{profile['voice_id']}" if profile else "")

        quick_voice.bind("<<ComboboxSelected>>", update_voice_hint)
        widgets["tts_voice"].bind("<<ComboboxSelected>>", update_voice_hint)
        values["tts_voice"].trace_add("write", update_voice_hint)
        ttk.Button(voice_bar, text="管理/试听音色", command=self.open_voice_manager).pack(side="left", padx=12)
        load_provider_voices()
        update_voice_hint()

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
                provider_key = next(
                    key for key, label in tts_choices.items()
                    if label == values["tts_provider"].get()
                )
                selected_voice = next((
                    profile for profile in self._voice_profiles()
                    if profile["provider"] == provider_key
                    and voice_label(profile) == values["tts_voice"].get().strip()
                ), None)
                if provider_key != "none" and not selected_voice:
                    raise ValueError("请选择当前项目统一使用的音色")
                new_voice = {
                    "tts_provider": provider_key,
                    "tts_voice": selected_voice["voice_id"] if selected_voice else "",
                    "tts_model_id": selected_voice.get("model_id", "") if selected_voice else "",
                    "tts_speed": max(0.5, min(2.0, float(values["tts_speed"].get()))),
                    "tts_volume": max(0.0, min(2.0, float(values["tts_volume"].get()))),
                }
                invalidate_voice_outputs = False
                if existing.get("id") and self._voice_signature(existing) != self._voice_signature(new_voice):
                    all_rows = self.selection_store.list(existing["id"])
                    invalidate_voice_outputs = any(row.get("processed_path") for row in all_rows)
                    if invalidate_voice_outputs and not messagebox.askyesno(
                        APP_TITLE,
                        "当前项目音色已经变化。为避免同一成片混入不同声音，已生成片段将全部标记为需重新生成。\n\n是否继续？",
                        parent=dialog,
                    ):
                        return
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
                    **new_voice,
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
                    **cleanup_task_values(),
                })
                self.selection_store.update_task(project, status=existing.get("local_status") or "draft")
                if invalidate_voice_outputs:
                    self.selection_store.invalidate_processed(task_id)
                self.selection_store.add_text(
                    task_id, "\n".join(project["source_urls"]), source_kind="pasted_link",
                )
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

        actions = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        actions.pack(side="bottom", fill="x")
        ttk.Button(
            actions, text="保存文案与项目音色" if task else "创建项目", command=save_project,
        ).pack(side="left", padx=4)
        ttk.Button(
            actions, text="保存并打开抖音搜索" if task else "创建并打开抖音搜索",
            command=lambda: save_project(True),
        ).pack(side="left", padx=4)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="right", padx=4)
        dialog.grab_set()
        dialog.focus_force()

    def _planning_options(self):
        options = fallback_options()
        if not self.vars["odoo_url"].get().strip() or not self.vars["worker_token"].get().strip():
            return options
        try:
            live = Worker(self.config()).planning_options()
            if all(live.get(key) for key in ("roles", "tracks", "scopes")):
                return live
        except Exception as exc:
            self.write_log("读取 Odoo 视频方案模板失败，已使用内置同版模板：%s" % exc)
        return options

    def _new_local_project_dialog(self):
        options = self._planning_options()
        dialog = tk.Toplevel(self)
        dialog.title("新建视频方案")
        dialog.transient(self)
        dialog.update_idletasks()
        width = min(1180, max(960, dialog.winfo_screenwidth() - 120))
        height = min(780, max(660, dialog.winfo_screenheight() - 120))
        x = max(20, (dialog.winfo_screenwidth() - width) // 2)
        y = max(20, (dialog.winfo_screenheight() - height) // 2)
        dialog.geometry("%sx%s+%s+%s" % (width, height, x, y))
        dialog.minsize(min(940, width), min(640, height))

        header = ttk.Frame(dialog, padding=(15, 12, 15, 6))
        header.pack(fill="x")
        ttk.Label(
            header, text="先建立视频整体方案，再制作分镜",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")
        ttk.Label(
            header, text="新建时不做翻译、配音、字幕或 HeyGen；这些在具体分镜加工时完成。",
            foreground="#666",
        ).pack(side="left", padx=20)
        ttk.Label(
            header, text=options.get("source") or "Odoo 模板",
            foreground="#397a66",
        ).pack(side="right")

        roles = options.get("roles") or []
        tracks = options.get("tracks") or []
        scopes = options.get("scopes") or []
        role_labels = {item["name"]: item for item in roles}
        track_labels = {item["name"]: item for item in tracks}
        scope_labels = {item["name"]: item for item in scopes}
        default_role = next((item["name"] for item in roles if item.get("code") == "trading_company"), roles[0]["name"])
        default_track = next((item["name"] for item in tracks if item.get("code") == "footwear_apparel"), tracks[0]["name"])
        default_scope = next((item["name"] for item in scopes if item.get("code") == "brand_positioning"), scopes[0]["name"])
        values = {
            "name": tk.StringVar(value="本地视频项目"),
            "role": tk.StringVar(value=default_role),
            "track": tk.StringVar(value=default_track),
            "scope": tk.StringVar(value=default_scope),
            "duration": tk.StringVar(value="30"),
            "target_language": tk.StringVar(value="English"),
            "aspect_ratio": tk.StringVar(value="9:16"),
        }

        choices = ttk.LabelFrame(dialog, text="1. 选择 Odoo 经营模板", padding=10)
        choices.pack(fill="x", padx=15, pady=6)
        fields = (
            ("项目名称", "name", None, 28),
            ("经营角色", "role", tuple(role_labels), 24),
            ("项目赛道", "track", tuple(track_labels), 24),
            ("内容模板", "scope", tuple(scope_labels), 24),
            ("目标时长", "duration", None, 8),
            ("目标语言", "target_language", ("English", "Spanish", "French", "German", "Arabic"), 12),
            ("画面比例", "aspect_ratio", ("9:16", "4:5", "1:1"), 8),
        )
        choice_widgets = {}
        column = 0
        for label, key, items, width_value in fields:
            ttk.Label(choices, text=label).grid(row=0, column=column, sticky="w", padx=(0, 5))
            if items:
                widget = ttk.Combobox(
                    choices, textvariable=values[key], values=items,
                    state="readonly", width=width_value,
                )
            else:
                widget = ttk.Entry(choices, textvariable=values[key], width=width_value)
            widget.grid(row=1, column=column, sticky="ew", padx=(0, 10), pady=(3, 0))
            choice_widgets[key] = widget
            choices.columnconfigure(column, weight=1 if key == "name" else 0)
            column += 1

        details = ttk.LabelFrame(dialog, text="2. 核对内容方向和画面要求", padding=10)
        details.pack(fill="both", expand=True, padx=15, pady=6)
        details.columnconfigure(0, weight=1)
        details.columnconfigure(1, weight=1)
        details.rowconfigure(2, weight=1)
        role_summary = tk.StringVar()
        goal_summary = tk.StringVar()
        evidence_summary = tk.StringVar()
        ttk.Label(
            details, textvariable=role_summary, wraplength=520, justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 5))
        ttk.Label(
            details, textvariable=goal_summary, wraplength=520, justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 5))
        ttk.Label(
            details, textvariable=evidence_summary, wraplength=1080, justify="left",
            foreground="#6f3f64",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        preview = ttk.Treeview(
            details, columns=("sequence", "name", "purpose", "visual", "narration", "duration"),
            show="headings", height=7,
        )
        for name, title, width_value in (
            ("sequence", "顺序", 55), ("name", "分镜名称", 130),
            ("purpose", "叙事作用", 135), ("visual", "画面要求", 360),
            ("narration", "文案任务", 280), ("duration", "目标", 65),
        ):
            preview.heading(name, text=title)
            preview.column(name, width=width_value, anchor="w")
        preview.grid(row=2, column=0, columnspan=2, sticky="nsew")

        copy_box = ttk.LabelFrame(dialog, text="3. 中文文案结构模板（这里只确认方向，不翻译）", padding=8)
        copy_box.pack(fill="x", padx=15, pady=6)
        copy_preview = tk.Text(copy_box, height=4, wrap="word", background="#f5f6f7")
        copy_preview.pack(fill="x")
        current_plan = {"value": None}

        def update_preview(_event=None):
            try:
                role = role_labels[values["role"].get()]
                track = track_labels[values["track"].get()]
                scope = scope_labels[values["scope"].get()]
                plan = build_video_plan(
                    options, role["code"], track["code"], scope["code"],
                    int(values["duration"].get() or 30),
                )
            except (KeyError, TypeError, ValueError):
                return
            current_plan["value"] = plan
            role_summary.set("经营身份：%s｜%s" % (
                role["name"], role.get("description") or role.get("content_focus") or "",
            ))
            goal_summary.set("本条内容：%s｜%s" % (scope["name"], plan["goal"]))
            evidence_summary.set("画面与证据要求：%s" % plan["visual_requirements"])
            for item in preview.get_children():
                preview.delete(item)
            for shot in plan["storyboard"]:
                preview.insert("", "end", values=(
                    shot["sequence"], shot["name"], shot["purpose"],
                    shot["visual_requirement"], shot["narration"],
                    "%g秒" % float(shot["target_duration"]),
                ))
            copy_preview.config(state="normal")
            copy_preview.delete("1.0", "end")
            copy_preview.insert("1.0", plan["copy_template"])
            copy_preview.config(state="disabled")

        for key in ("role", "track", "scope"):
            choice_widgets[key].bind("<<ComboboxSelected>>", update_preview)
        values["duration"].trace_add("write", update_preview)
        update_preview()

        def create_project():
            try:
                name = values["name"].get().strip()
                if not name:
                    raise ValueError("请填写项目名称")
                plan = current_plan["value"]
                if not plan:
                    raise ValueError("请选择经营角色、项目赛道和内容模板")
                task_id = self.selection_store.next_local_task_id()
                aspect = values["aspect_ratio"].get()
                project = {
                    "id": task_id, "type": "local_project", "local_only": True,
                    "name": name, "keywords": "", "source_language": "Chinese",
                    "target_language": values["target_language"].get() or "English",
                    "duration_seconds": int(values["duration"].get() or 30),
                    "aspect_ratio": aspect, "export_preset": {
                        "9:16": "douyin", "4:5": "feed", "1:1": "square",
                    }.get(aspect, "douyin"),
                    "video_plan_summary": plan["summary"],
                    "storyboard": plan["storyboard"],
                    "business_role": {"code": plan["role"]["code"], "name": plan["role"]["name"]},
                    "project_track": {"code": plan["track"]["code"], "name": plan["track"]["name"]},
                    "content_scope": {"code": plan["scope"]["code"], "name": plan["scope"]["name"]},
                    "prompt": plan["goal"], "video_script": plan["copy_template"],
                    "content_source": "odoo_translation", "source_urls": [], "local_files": [],
                    "edit_mode": "sequence", "transition": "none",
                    "tts_provider": "none", "tts_voice": "", "tts_model_id": "",
                    "tts_speed": 1.0, "tts_volume": 1.0,
                    "background_music": "", "music_volume": 0.2,
                    "remove_hard_subtitles": False, "subtitle_cleanup_mode": "quick",
                    "subtitle_cleanup_engine": "sttn", "subtitle_cleanup_quality": "standard",
                    "subtitle_quick_method": "blur", "subtitle_region": "5,72,90,22",
                    "overlay_translation_in_cleanup_region": True,
                }
                self.selection_store.save_task(project, status="draft")
                self.selection_store.sync_storyboard(task_id, plan["storyboard"])
                self.selection_task_id = task_id
                dialog.destroy()
                self._refresh_selection_tasks()
                self._refresh_selection_tree()
                self.notebook.select(self.selection_tab)
                self.selection_workflow.select(self.selection_source_page)
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        actions = ttk.Frame(dialog, padding=(15, 6, 15, 12))
        actions.pack(fill="x")
        ttk.Button(actions, text="创建并进入分镜制作", command=create_project).pack(side="left")
        ttk.Label(
            actions, text="创建后：导入全局原素材 → 逐条制作分镜 → 关联到画面要求 → 排序合成。",
            foreground="#666",
        ).pack(side="left", padx=18)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="right")
        dialog.grab_set()
        dialog.focus_force()

    def create_local_project(self):
        self._new_local_project_dialog()

    def edit_active_project(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个项目")
            return
        self._project_dialog(task)

    def open_subtitle_cleanup(self):
        self._project_dialog(self._active_selection_task(), initial_tab="cleanup")

    def _show_subtitle_region_selector(self, source, initial_region, on_save, parent):
        frame = app_dir() / ("subtitle-region-%s.jpg" % secrets.token_hex(5))
        Worker(self.config()).extract_video_frame(source, frame)
        with Image.open(frame) as image:
            display = image.convert("RGB")
        display.thumbnail((920, 560), Image.Resampling.LANCZOS)
        selector = tk.Toplevel(parent)
        selector.title("拖动框选需要处理的中文字幕区域")
        selector.transient(parent)
        canvas = tk.Canvas(selector, width=display.width, height=display.height, cursor="crosshair")
        canvas.pack(padx=12, pady=12)
        photo = ImageTk.PhotoImage(display)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo
        region = Worker.subtitle_region(initial_region)
        rectangle = canvas.create_rectangle(
            region[0] * display.width, region[1] * display.height,
            (region[0] + region[2]) * display.width,
            (region[1] + region[3]) * display.height,
            outline="#ff3b30", width=3,
        )
        state = {"start": None}

        def press(event):
            state["start"] = (event.x, event.y)
            canvas.coords(rectangle, event.x, event.y, event.x, event.y)

        def drag(event):
            if state["start"]:
                x0, y0 = state["start"]
                canvas.coords(
                    rectangle, x0, y0,
                    max(0, min(display.width, event.x)),
                    max(0, min(display.height, event.y)),
                )

        def save_region():
            x0, y0, x1, y1 = canvas.coords(rectangle)
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            if right - left < 8 or bottom - top < 8:
                messagebox.showerror(APP_TITLE, "框选区域太小", parent=selector)
                return
            on_save("%.2f,%.2f,%.2f,%.2f" % (
                left * 100 / display.width, top * 100 / display.height,
                (right - left) * 100 / display.width,
                (bottom - top) * 100 / display.height,
            ))
            selector.destroy()

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        actions = ttk.Frame(selector, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        ttk.Label(actions, text="只框选中文字幕，不要包含Logo或水印。", foreground="#666").pack(side="left")
        ttk.Button(actions, text="保存区域", command=save_region).pack(side="right")

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
        selected_before = set(self.selection_tree.selection())
        self.selection_cover_images.clear()
        for item in self.selection_tree.get_children():
            self.selection_tree.delete(item)
        self._refresh_review_lists(task)
        if not task:
            self.selection_title.set("当前没有等待处理的抖音选片任务")
            self.video_plan_summary.set("请选择项目；先确认整体视频方案，再逐个完成分镜。")
            self.storyboard_progress.set("分镜进度：0/0")
            self.storyboard_choice_map = {}
            self.storyboard_choice["values"] = ()
            self.storyboard_choice_var.set("")
            self.current_storyboard_slot_key = ""
            for item in self.storyboard_tree.get_children():
                self.storyboard_tree.delete(item)
            self.selection_summary.set("0 条")
            self._refresh_media_library()
            self._refresh_assembly()
            if hasattr(self, "target_shot_label"):
                self.target_shot_label.set("尚未选择要填充的成片分镜")
            return
        if isinstance(task.get("storyboard"), list):
            self.selection_store.sync_storyboard(task["id"], task.get("storyboard") or [])
        self._refresh_storyboard(task)
        rows = self.selection_store.list_sources()
        labels = {
            "selected": "已选择", "downloading": "下载中", "downloaded": "已下载",
            "mixing": "混剪中", "ready_review": "待审核", "done": "已完成", "failed": "失败",
        }
        cleanup_labels = {
            "inherit": "按项目默认", "skip": "无需清理", "clean": "需要清理",
        }
        source_labels = {
            "douyin_search": "抖音选片", "pasted_link": "粘贴链接",
            "local_upload": "本地上传", "local_library": "本地素材库",
        }
        clip_type_labels = {
            "unknown": "未分类", "talking_face": "口播人脸",
            "face_no_speech": "非口播人脸", "no_face": "无人脸",
        }
        for row in rows:
            cover = self._selection_cover(row)
            caption = row.get("caption") or (
                "暂无文案" if row.get("caption_checked") else "待获取"
            )
            cleanup_label = cleanup_labels.get(
                row.get("subtitle_cleanup_policy"), "按项目默认",
            )
            cleanup_status = row.get("subtitle_cleanup_status") or ""
            if row.get("subtitle_cleanup_policy") == "clean":
                cleanup_label = {
                    "processing": "清理中", "ready": "已清理", "failed": "清理失败",
                    "pending": "待清理",
                }.get(cleanup_status, "待清理")
            processed = Path(row.get("processed_path") or "")
            processing_status = row.get("processing_status") or ""
            status_label = labels.get(row["status"], row["status"])
            final_source = "尚未生成"
            if processing_status == "processing":
                status_label = "片段生成中"
            elif processing_status == "failed":
                status_label = "片段生成失败"
            elif processing_status == "ready" and processed.is_file():
                status_label = "可合成"
                final_source = row.get("processed_kind") or "已处理片段"
            self.selection_tree.insert("", "end", iid=str(row["id"]), image=cover, values=(
                row.get("clip_name") or row["video_id"] or "待下载解析",
                source_labels.get(row.get("source_kind"), "粘贴链接"),
                clip_type_labels.get(row.get("clip_type"), "未分类"),
                caption.replace("\n", " "),
                self._format_duration(row.get("duration") or 0),
                status_label,
                "%s-%s" % (row.get("trim_start") or 0, row.get("trim_end") or "结束"),
                cleanup_label,
                final_source,
                row.get("copyright_status") or "unreviewed", row["url"],
                row.get("processing_error") or row.get("subtitle_cleanup_error") or row["error"],
            ))
        available = set(self.selection_tree.get_children())
        preserved = [item for item in selected_before if item in available]
        if preserved:
            self.selection_tree.selection_set(preserved)
        self._schedule_selection_metadata(task, rows)
        kind = "本地项目" if task.get("local_only") else "Odoo任务"
        self.selection_title.set("%s %s · %s · %s｜全局原始素材 %s 条" % (
            kind, task["id"], task.get("name") or task.get("keywords") or task.get("target_language") or "抖音选片",
            task.get("local_status") or "处理中", len(rows),
        ))
        self._refresh_selection_summary()
        self._refresh_media_library()
        self._refresh_assembly()

    def _refresh_storyboard(self, task=None):
        task = task or self._active_selection_task()
        selected_before = self._selected_storyboard_slot()
        for item in self.storyboard_tree.get_children():
            self.storyboard_tree.delete(item)
        if not task:
            return
        self.video_plan_summary.set(
            (task.get("video_plan_summary") or "本地项目：请先明确整条视频方案和各分镜用途。")[:500]
        )
        state_labels = {
            "missing": "缺少素材", "producing": "制作中", "ready": "已有候选",
            "selected": "已关联",
        }
        rows = self.selection_store.list_storyboard(task["id"])
        selected_count = sum(1 for row in rows if row["state"] == "selected")
        candidate_count = sum(1 for row in rows if row["state"] == "ready")
        missing_count = sum(1 for row in rows if row["state"] in ("missing", "producing"))
        self.storyboard_progress.set(
            "已选定 %s/%s｜候选 %s｜缺少 %s" %
            (selected_count, len(rows), candidate_count, missing_count)
        )
        labels = []
        self.storyboard_choice_map = {}
        assets = {item["asset_uuid"]: item for item in self.selection_store.list_assets()}
        for index, row in enumerate(rows, 1):
            asset = assets.get(row.get("selected_asset_uuid") or "") or {}
            label = "%02d. %s · %s%s" % (
                index, row["name"], state_labels.get(row["state"], row["state"]),
                (" · " + asset["name"]) if asset.get("name") else "",
            )
            labels.append(label)
            self.storyboard_choice_map[label] = row["slot_key"]
            self.storyboard_tree.insert("", "end", iid=row["slot_key"], values=(
                row["sequence"], row["name"], row["purpose"],
                row.get("visual_requirement") or "—",
                row.get("narration") or "—",
                "%g秒" % float(row["target_duration"] or 0),
                state_labels.get(row["state"], row["state"]),
            ))
        self.storyboard_choice["values"] = labels
        active_slot = selected_before if self.storyboard_tree.exists(selected_before) else ""
        if not active_slot and rows:
            active_slot = rows[0]["slot_key"]
        self.current_storyboard_slot_key = active_slot
        if active_slot:
            self.storyboard_tree.selection_set(active_slot)
            selected_label = next(
                (label for label, key in self.storyboard_choice_map.items() if key == active_slot),
                "",
            )
            self.storyboard_choice_var.set(selected_label)
        else:
            self.storyboard_choice_var.set("")
        self._update_target_shot_label()

    def _update_target_shot_label(self):
        if not hasattr(self, "target_shot_label"):
            return
        task = self._active_selection_task()
        selected = self.storyboard_tree.selection()
        if selected:
            self.current_storyboard_slot_key = selected[0]
        slot_key = self.current_storyboard_slot_key
        if not task or not slot_key:
            self.target_shot_label.set("尚未选择要填充的成片分镜；请在上方选择")
            if hasattr(self, "production_shot_label"):
                self.production_shot_label.set("尚未选择本次要制作的分镜要求；请在上方选择")
            return
        slot = next(
            (row for row in self.selection_store.list_storyboard(task["id"])
             if row["slot_key"] == slot_key),
            None,
        )
        if not slot:
            self.target_shot_label.set("所选分镜已不存在，请刷新当前项目")
            if hasattr(self, "production_shot_label"):
                self.production_shot_label.set("所选分镜已不存在，请刷新当前项目")
            return
        description = "%s｜用途：%s｜画面：%s｜目标：%g秒" % (
            slot["name"], slot.get("purpose") or "未填写",
            slot.get("visual_requirement") or "未填写",
            float(slot.get("target_duration") or 0),
        )
        self.target_shot_label.set(description)
        selected_label = next(
            (label for label, key in self.storyboard_choice_map.items() if key == slot_key),
            "",
        )
        if selected_label:
            self.storyboard_choice_var.set(selected_label)
        if hasattr(self, "production_shot_label"):
            self.production_shot_label.set(description + "｜完成后仅进入素材库")

    def _refresh_media_library(self):
        if not hasattr(self, "library_tree"):
            return
        selected = self.library_tree.selection()
        for item in self.library_tree.get_children():
            self.library_tree.delete(item)
        kind_labels = {
            "standard_shot": "标准分镜", "voice_variant": "配音分镜",
            "heygen_variant": "HeyGen分镜", "music": "背景音乐",
        }
        type_labels = {
            "talking_face": "口播人脸", "face_no_speech": "非口播人脸",
            "no_face": "无人脸", "unknown": "未分类",
        }
        for asset in self.selection_store.list_assets():
            self.library_tree.insert("", "end", iid=asset["asset_uuid"], values=(
                asset["name"], kind_labels.get(asset["asset_kind"], asset["asset_kind"]),
                type_labels.get(asset["clip_type"], asset["clip_type"]),
                asset.get("role_name") or asset.get("role_code") or "—",
                asset.get("track_name") or asset.get("track_code") or "—",
                asset.get("scope_name") or asset.get("scope_code") or "—",
                asset.get("shot_purpose") or "—", self._format_duration(asset.get("duration") or 0),
                asset.get("subtitle_state") or "unknown",
                asset.get("copyright_status") or "unreviewed", asset["file_path"],
            ))
        available = set(self.library_tree.get_children())
        if selected and selected[0] in available:
            self.library_tree.selection_set(selected[0])

    def _selected_storyboard_slot(self):
        selected = self.storyboard_tree.selection()
        return selected[0] if selected else getattr(self, "current_storyboard_slot_key", "")

    def add_library_asset_to_current_shot(self):
        task = self._active_selection_task()
        selected = self.library_tree.selection()
        slot_key = self._selected_storyboard_slot()
        if not task or not selected:
            messagebox.showerror(APP_TITLE, "请先选择当前项目和一条本地分镜素材")
            return
        if self.selection_store.list_storyboard(task["id"]) and not slot_key:
            messagebox.showerror(APP_TITLE, "请先在当前视频方案中选择要填充的分镜")
            return
        try:
            self.selection_store.select_asset_for_composition(task["id"], slot_key, selected[0])
            self._refresh_storyboard(task)
            self._refresh_assembly()
            messagebox.showinfo(
                APP_TITLE,
                "已将所选素材关联到当前画面要求，并按视频方案顺序加入成片。\n"
                "素材库原件仍保留，可继续供其他视频使用。",
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def _refresh_assembly(self):
        if not hasattr(self, "assembly_tree"):
            return
        selected_before = set(self.assembly_tree.selection())
        for item in self.assembly_tree.get_children():
            self.assembly_tree.delete(item)
        task = self._active_selection_task()
        if not task:
            return
        kind_labels = {
            "standard_shot": "标准分镜", "voice_variant": "配音分镜",
            "heygen_variant": "HeyGen分镜", "music": "背景音乐",
        }
        for index, row in enumerate(self.selection_store.list_composition(task["id"]), 1):
            voice = row.get("voice_signature") or "无配音"
            if voice != "无配音":
                voice = "当前项目音色" if voice == self._voice_signature(task) else "音色不一致"
            self.assembly_tree.insert("", "end", iid=str(row["id"]), values=(
                index, row.get("shot_name") or row["slot_key"], row.get("name") or "—",
                kind_labels.get(row.get("asset_kind"), row.get("asset_kind") or "—"),
                self._format_duration(row.get("duration") or 0), voice,
                row.get("file_path") or "",
            ))
        available = set(self.assembly_tree.get_children())
        preserved = [item for item in selected_before if item in available]
        if preserved:
            self.assembly_tree.selection_set(preserved)

    def _assembly_ids(self):
        return [int(value) for value in self.assembly_tree.selection()]

    def select_all_assembly(self):
        self.assembly_tree.selection_set(self.assembly_tree.get_children())

    def move_assembly_clips(self, direction):
        task = self._active_selection_task()
        ids = self._assembly_ids()
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先选择要调整顺序的成片分镜")
            return
        self.selection_store.move_composition(task["id"], ids, direction)
        self._refresh_assembly()

    def remove_assembly_clips(self):
        task = self._active_selection_task()
        ids = self._assembly_ids()
        if not task or not ids:
            messagebox.showerror(APP_TITLE, "请先选择要移出本次成片的分镜")
            return
        if not messagebox.askyesno(
            APP_TITLE, "只从本次成片时间线移除所选分镜；本地分镜素材库文件不会删除。是否继续？",
        ):
            return
        self.selection_store.remove_composition(task["id"], ids)
        self._refresh_storyboard(task)
        self._refresh_assembly()

    def preview_assembly_clip(self):
        task = self._active_selection_task()
        ids = self._assembly_ids()
        if not task or len(ids) != 1:
            messagebox.showerror(APP_TITLE, "请选择一条成片分镜进行预览")
            return
        row = next(
            (item for item in self.selection_store.list_composition(task["id"])
             if item["id"] == ids[0]),
            None,
        )
        path = Path((row or {}).get("file_path") or "")
        if not path.is_file():
            messagebox.showerror(APP_TITLE, "分镜素材文件已不存在，请回到素材库重新选择")
            return
        os.startfile(str(path))

    def preview_library_asset(self):
        selected = self.library_tree.selection()
        if not selected:
            messagebox.showerror(APP_TITLE, "请先选择一条本地素材")
            return
        asset = self.selection_store.get_asset(selected[0])
        path = Path((asset or {}).get("file_path") or "")
        if not path.is_file():
            messagebox.showerror(APP_TITLE, "素材文件已不存在，请检查本地素材库")
            return
        os.startfile(str(path))

    def sync_media_library(self):
        assets = self.selection_store.list_assets()
        if not assets:
            messagebox.showinfo(APP_TITLE, "本地素材库当前为空")
            return
        if not self.vars["worker_token"].get().strip():
            messagebox.showerror(APP_TITLE, "请先配置并保存 Odoo 工作节点令牌")
            return
        payload = self._asset_sync_payload(assets)

        def run_sync():
            try:
                worker = self.worker or Worker(self.config())
                result = worker.sync_local_assets(payload)
                self.events.put(("log", {"message": "已同步 %s 条本地素材索引到 Odoo" % result.get("saved", 0)}))
                self.events.put(("media_library_synced", {"count": result.get("saved", 0)}))
            except Exception as exc:
                self.events.put(("selection_operation_error", {"error": str(exc)}))
        threading.Thread(target=run_sync, daemon=True).start()

    def _asset_sync_payload(self, assets, work_dir=None):
        root = Path(
            work_dir or self.vars["work_dir"].get().strip() or app_dir() / "jobs"
        ).resolve()
        payload = []
        for asset in assets:
            path = Path(asset["file_path"])
            try:
                relative_path = str(path.resolve().relative_to(root))
            except ValueError:
                relative_path = path.name
            payload.append({
                "asset_uuid": asset["asset_uuid"], "name": asset["name"],
                "asset_kind": asset["asset_kind"], "clip_type": asset["clip_type"],
                "business_role_code": asset.get("role_code") or "",
                "track_code": asset.get("track_code") or "",
                "scope_code": asset.get("scope_code") or "",
                "shot_purpose": asset.get("shot_purpose") or "",
                "duration": asset.get("duration") or 0,
                "aspect_ratio": asset.get("aspect_ratio") or "",
                "language": asset.get("language") or "",
                "subtitle_state": asset.get("subtitle_state") or "unknown",
                "voice_signature": asset.get("voice_signature") or "",
                "copyright_status": asset.get("copyright_status") or "",
                "local_relative_path": relative_path,
                "file_size": path.stat().st_size if path.is_file() else 0,
                "content_hash": asset.get("content_hash") or "",
                "metadata": asset.get("metadata") or {}, "active": bool(asset.get("active", 1)),
            })
        return payload

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
        rows = self.selection_store.list_composition(task["id"])
        selected = self.render_tree.selection()
        versions = self.selection_store.list_versions(task["id"])
        version = next(
            (item for item in versions if selected and item["id"] == int(selected[0])),
            versions[0] if versions else None,
        )
        source_ids = set(version.get("source_video_ids") or []) if version else set()
        if not source_ids:
            source_ids = {row["id"] for row in rows}
        for row in rows:
            if row["id"] in source_ids:
                actual = Path(row.get("file_path") or "")
                self.review_source_tree.insert("", "end", iid=str(row["id"]), values=(
                    row.get("shot_name") or row.get("slot_key") or "分镜",
                    row.get("asset_kind") or "已处理分镜",
                    str(actual),
                ))

    def _refresh_selection_summary(self):
        selected = [int(value) for value in self.selection_tree.selection()]
        rows = self.selection_store.get_many(selected) if selected else []
        cleaned = sum(
            1 for row in rows
            if row.get("subtitle_cleanup_status") == "ready"
            and Path(row.get("subtitle_cleaned_path") or "").is_file()
        )
        talking = sum(1 for row in rows if row.get("clip_type") == "talking_face")
        no_lipsync = sum(
            1 for row in rows if row.get("clip_type") in ("face_no_speech", "no_face")
        )
        ready = sum(
            1 for row in rows
            if row.get("processing_status") == "ready"
            and Path(row.get("processed_path") or "").is_file()
        )
        self.selection_summary.set("共 %s 条｜已选 %s 条｜口播人脸 %s｜无需口型 %s｜已清字幕 %s｜可合成 %s" % (
            len(self.selection_tree.get_children()), len(selected), talking, no_lipsync, cleaned, ready,
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

    def select_talking_face_clips(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个视频项目")
            return []
        ids = [
            row["id"] for row in self.selection_store.list_sources()
            if row.get("clip_type") == "talking_face"
        ]
        self.selection_tree.selection_remove(*self.selection_tree.selection())
        if ids:
            self.selection_tree.selection_set([str(value) for value in ids])
            self.selection_tree.see(str(ids[0]))
        else:
            messagebox.showinfo(APP_TITLE, "当前没有标记为“口播人脸”的片段。")
        self._refresh_selection_summary()
        return ids

    def select_cleaned_videos(self, show_empty=True):
        task = self._active_selection_task()
        if not task:
            if show_empty:
                messagebox.showerror(APP_TITLE, "请先选择一个视频项目")
            return []
        ids = [
            row["id"] for row in self.selection_store.list_sources()
            if row.get("subtitle_cleanup_status") == "ready"
            and Path(row.get("subtitle_cleaned_path") or "").is_file()
        ]
        self.selection_tree.selection_remove(*self.selection_tree.selection())
        if ids:
            self.selection_tree.selection_set([str(value) for value in ids])
            self.selection_tree.see(str(ids[0]))
        elif show_empty:
            messagebox.showinfo(
                APP_TITLE,
                "全局原始素材库没有可用的已清理素材。请先选择视频并执行“逐条字幕清理”。",
            )
        self._refresh_selection_summary()
        return ids

    def open_cleaned_mix_workflow(self):
        if self.select_cleaned_videos():
            self.edit_active_project()

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
                    added = self.selection_store.add_text(
                        task["id"], value, source_kind="pasted_link",
                    )
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
        added = self.selection_store.add_text(
            task["id"], self._clipboard_text(), source_kind="pasted_link",
        )
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
            added = self.selection_store.add_text(
                task["id"], editor.get("1.0", "end"), source_kind="pasted_link",
            )
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
            self._open_local_path(self._mix_source_path(row))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def preview_cleaned_selected_video(self):
        ids = self._selection_ids()
        if len(ids) != 1:
            messagebox.showerror(APP_TITLE, "请选择一条已完成字幕清理的视频")
            return
        row = self.selection_store.get_many(ids)[0]
        try:
            self._open_local_path(row.get("subtitle_cleaned_path"))
        except Exception:
            messagebox.showinfo(
                APP_TITLE,
                "这条素材还没有生成完整清理文件。请点击“逐条字幕清理”，再点“立即处理完整素材”。",
            )

    def _save_clip_cleanup_settings(self, rows, saved):
        setting_fields = (
            "subtitle_cleanup_policy", "subtitle_cleanup_mode",
            "subtitle_cleanup_engine",
            "subtitle_cleanup_quality", "subtitle_quick_method", "subtitle_region",
        )
        for row in rows:
            changed = any(row.get(field) != saved[field] for field in setting_fields)
            values = dict(saved)
            if changed:
                values.update({
                    "subtitle_cleaned_path": "", "subtitle_cleanup_signature": "",
                    "subtitle_cleanup_status": (
                        "pending" if saved["subtitle_cleanup_policy"] == "clean" else ""
                    ),
                    "subtitle_cleanup_error": "",
                    "processed_path": "", "processed_kind": "",
                    "processing_status": "", "processing_error": "",
                    "voice_signature": "",
                })
            self.selection_store.update(row["id"], **values)

    def _start_full_subtitle_cleanup(self, task, rows, button=None):
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个视频项目")
            return False
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有素材处理正在运行")
            return False
        invalid = [
            row for row in rows
            if row.get("subtitle_cleanup_policy") != "clean"
            or not Path(row.get("local_path") or "").is_file()
        ]
        if invalid:
            messagebox.showerror(
                APP_TITLE,
                "完整处理只执行标记为“需要清理”且已下载的素材，请检查所选视频。",
            )
            return False
        worker = Worker(self.config())
        output_dir = worker.root / str(task["id"]) / "subtitle-cleaned"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.selection_busy = True
        if button:
            button.config(state="disabled")

        def run_cleanup():
            paths, errors = [], []
            for selected in rows:
                row = self.selection_store.get_many([selected["id"]])[0]
                source = Path(row["local_path"])
                try:
                    signature = worker.subtitle_cleanup_signature(row, source)
                    existing = Path(row.get("subtitle_cleaned_path") or "")
                    if (
                        existing.is_file()
                        and row.get("subtitle_cleanup_signature") == signature
                    ):
                        paths.append(str(existing))
                        self.selection_store.update(
                            row["id"], subtitle_cleanup_status="ready",
                            subtitle_cleanup_error="",
                        )
                        continue
                    output = output_dir / (
                        "clip-%s-%s.mp4" % (row["id"], signature[:12])
                    )
                    self.selection_store.update(
                        row["id"], subtitle_cleanup_status="processing",
                        subtitle_cleanup_error="",
                    )
                    self.events.put(("selection_changed", {}))
                    worker.clean_hard_subtitles(row, source, output)
                    self.selection_store.update(
                        row["id"], subtitle_cleaned_path=str(output),
                        subtitle_cleanup_signature=signature,
                        subtitle_cleanup_status="ready", subtitle_cleanup_error="",
                    )
                    paths.append(str(output))
                except Exception as exc:
                    self.selection_store.update(
                        row["id"], subtitle_cleanup_status="failed",
                        subtitle_cleanup_error=str(exc),
                    )
                    errors.append("素材 %s：%s" % (row.get("video_id") or row["id"], exc))
            self.events.put(("subtitle_cleanup_batch_done", {
                "button": button, "paths": paths, "errors": errors,
                "folder": str(output_dir),
            }))

        threading.Thread(target=run_cleanup, daemon=True).start()
        return True

    @staticmethod
    def _selection_folder(task, rows, work_dir):
        if len(rows) == 1:
            local_path = Path(rows[0].get("local_path") or "").expanduser()
            if local_path.is_file():
                return local_path.resolve().parent
        return Path(work_dir).expanduser().resolve() / str(task["id"]) / "selected-videos"

    def open_selection_folder(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择或新建一个项目")
            return
        ids = self._selection_ids()
        rows = self.selection_store.get_many(ids) if ids else []
        folder = self._selection_folder(task, rows, self.vars["work_dir"].get())
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

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
        dialog.title("② 人工初剪与片段分类")
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
        has_custom_trim = bool(row.get("trim_start") or row.get("trim_end"))
        full_clip = tk.BooleanVar(value=not has_custom_trim)
        trim_start = tk.StringVar(value=str(row.get("trim_start") or 0))
        trim_end = tk.StringVar(value=str(row.get("trim_end") or round(duration, 3)))
        copyright_status = tk.StringVar(value=row.get("copyright_status") or "unreviewed")
        copyright_note = tk.StringVar(value=row.get("copyright_note") or "")
        clip_name = tk.StringVar(value=row.get("clip_name") or row.get("video_id") or "")
        clip_type_choices = {
            "未分类": "unknown", "口播人脸（进入 HeyGen）": "talking_face",
            "非口播人脸（不做口型）": "face_no_speech", "无人脸（不做口型）": "no_face",
        }
        current_clip_type = next(
            (label for label, value in clip_type_choices.items()
             if value == (row.get("clip_type") or "unknown")),
            "未分类",
        )
        clip_type = tk.StringVar(value=current_clip_type)
        cleanup_needed = tk.BooleanVar(
            value=(row.get("subtitle_cleanup_policy") == "clean")
        )
        trim_entries = []
        for index, (label, variable) in enumerate((("入点（秒）", trim_start), ("出点（秒）", trim_end))):
            ttk.Label(fields, text=label).grid(row=0, column=index * 2, sticky="w", padx=(0, 6))
            entry = ttk.Entry(fields, textvariable=variable, width=12)
            entry.grid(row=0, column=index * 2 + 1, padx=(0, 18))
            trim_entries.append(entry)
        ttk.Checkbutton(
            fields, text="使用完整原片",
            variable=full_clip,
        ).grid(row=0, column=4, sticky="w")
        ttk.Label(fields, text="片段名称").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(fields, textvariable=clip_name).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 18),
        )
        ttk.Label(fields, text="片段类型").grid(row=1, column=3, sticky="w", pady=8)
        ttk.Combobox(
            fields, textvariable=clip_type, state="readonly",
            values=tuple(clip_type_choices), width=24,
        ).grid(row=1, column=4, sticky="w")
        ttk.Label(fields, text="版权状态").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Combobox(
            fields, textvariable=copyright_status, state="readonly",
            values=("unreviewed", "authorized", "self_owned", "restricted"), width=18,
        ).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(
            fields,
            text="需要处理原字幕（保存后打开清理设置）",
            variable=cleanup_needed,
        ).grid(row=2, column=3, columnspan=2, sticky="w", pady=8)
        ttk.Label(fields, text="版权备注").grid(row=3, column=0, sticky="w")
        ttk.Entry(fields, textvariable=copyright_note).grid(row=3, column=1, columnspan=4, sticky="ew")
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
            full_clip.set(False)
            for entry in trim_entries:
                entry.config(state="normal")
            variable.set("%.3f" % float(position.get()))

        def toggle_full_clip():
            state = "disabled" if full_clip.get() else "normal"
            for entry in trim_entries:
                entry.config(state=state)

        for widget in fields.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(command=toggle_full_clip)
        toggle_full_clip()

        point_controls = ttk.Frame(control_panel)
        point_controls.pack(pady=8)
        ttk.Button(point_controls, text="当前位置设为入点", command=lambda: set_point(trim_start)).pack(side="left", padx=4)
        ttk.Button(point_controls, text="当前位置设为出点", command=lambda: set_point(trim_end)).pack(side="left", padx=4)
        ttk.Button(point_controls, text="用系统播放器播放", command=lambda: os.startfile(str(path))).pack(side="left", padx=4)

        def clip_values(require_range=False):
            if full_clip.get():
                if require_range:
                    messagebox.showerror(
                        APP_TITLE, "另存新片段前，请先设置入点和出点。", parent=dialog,
                    )
                    return None
                start, end = 0.0, 0.0
            else:
                try:
                    start, end = float(trim_start.get()), float(trim_end.get())
                except ValueError:
                    messagebox.showerror(APP_TITLE, "入点和出点必须是数字", parent=dialog)
                    return None
                if start < 0 or end <= start or end > duration + 0.1:
                    messagebox.showerror(APP_TITLE, "入点和出点超出视频有效时长", parent=dialog)
                    return None
            return start, end

        def save_clip():
            values = clip_values()
            if not values:
                return
            start, end = values
            self.selection_store.update(
                row["id"], trim_start=start, trim_end=end,
                copyright_status=copyright_status.get(), copyright_note=copyright_note.get().strip(),
                clip_name=clip_name.get().strip(), clip_type=clip_type_choices[clip_type.get()],
                subtitle_cleanup_policy="clean" if cleanup_needed.get() else "skip",
                subtitle_cleanup_status=(
                    row.get("subtitle_cleanup_status") or "pending"
                    if cleanup_needed.get() else ""
                ),
                subtitle_cleanup_error="",
                processed_path="", processed_kind="", processing_status="",
                processing_error="", voice_signature="",
            )
            dialog.destroy()
            self._refresh_selection_tree()
            self.selection_tree.selection_set(str(row["id"]))
            if cleanup_needed.get():
                self.after(80, self.edit_selected_subtitle_cleanup)

        def save_as_new_clip():
            values = clip_values(require_range=True)
            if not values:
                return
            start, end = values
            try:
                new_id = self.selection_store.create_clip(
                    row["id"], start, end, clip_name.get(), clip_type_choices[clip_type.get()],
                )
                self.selection_store.update(
                    new_id,
                    subtitle_cleanup_policy="clean" if cleanup_needed.get() else "skip",
                    subtitle_cleanup_status="pending" if cleanup_needed.get() else "",
                    subtitle_cleanup_error="",
                )
            except (ValueError, OSError) as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)
                return
            dialog.destroy()
            self._refresh_selection_tree()
            self.selection_tree.selection_set(str(new_id))
            self.selection_tree.see(str(new_id))
            self._refresh_selection_summary()
            if cleanup_needed.get():
                self.after(80, self.edit_selected_subtitle_cleanup)

        buttons = ttk.Frame(control_panel)
        buttons.pack(pady=10)
        ttk.Button(buttons, text="保存当前记录", command=save_clip).pack(side="left", padx=4)
        ttk.Button(
            buttons, text="另存为新片段（保留原片）", command=save_as_new_clip,
        ).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)
        render_frame()

    def edit_selected_subtitle_cleanup(self):
        ids = self._selection_ids()
        if not ids:
            messagebox.showerror(APP_TITLE, "请先选择需要设置的一条或多条视频")
            return
        rows = self.selection_store.get_many(ids)
        first = rows[0]
        policy_choices = {
            "inherit": "按项目默认", "skip": "无需清理", "clean": "需要清理",
        }
        mode_choices = {
            "quick": "快速遮盖（无需AI）",
            "ai_auto": "AI无痕（自动识别）",
            "ai_manual": "AI无痕（手工框选）",
        }
        engine_choices = {"sttn": "VSR + STTN（时序修复，推荐）"}
        quality_choices = {"fast": "快速", "standard": "标准", "high": "高质量"}
        method_choices = {"blur": "模糊", "crop": "裁切", "cover": "底色覆盖"}
        values = {
            "policy": tk.StringVar(value=policy_choices.get(
                first.get("subtitle_cleanup_policy") or "inherit", policy_choices["inherit"],
            )),
            "mode": tk.StringVar(value=mode_choices.get(
                first.get("subtitle_cleanup_mode") or "quick", mode_choices["quick"],
            )),
            "engine": tk.StringVar(value=engine_choices.get(
                first.get("subtitle_cleanup_engine") or "sttn", engine_choices["sttn"],
            )),
            "quality": tk.StringVar(value=quality_choices.get(
                first.get("subtitle_cleanup_quality") or "standard", quality_choices["standard"],
            )),
            "method": tk.StringVar(value=method_choices.get(
                first.get("subtitle_quick_method") or "blur", method_choices["blur"],
            )),
            "region": tk.StringVar(value=first.get("subtitle_region") or "5,72,90,22"),
        }
        dialog = tk.Toplevel(self)
        dialog.title("② 初剪分类 · 字幕清理设置")
        dialog.geometry("860x410")
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="当前设置将应用到选中的 %s 条素材；未标记的视频不会执行去字幕。" % len(rows),
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))
        fields = (
            ("本条素材处理", "policy", tuple(policy_choices.values())),
            ("处理模式", "mode", tuple(mode_choices.values())),
            ("处理质量", "quality", tuple(quality_choices.values())),
            ("快速处理方式", "method", tuple(method_choices.values())),
        )
        field_widgets = {}
        for index, (label, key, choices) in enumerate(fields, 1):
            column = 0 if index % 2 else 2
            row = (index + 1) // 2
            ttk.Label(body, text=label).grid(row=row, column=column, sticky="e", padx=(0, 8), pady=8)
            widget = ttk.Combobox(
                body, textvariable=values[key], values=choices, state="readonly", width=18,
            )
            widget.grid(row=row, column=column + 1, sticky="ew", pady=8)
            field_widgets[key] = widget
        ttk.Label(body, text="AI修复模型").grid(
            row=3, column=0, sticky="e", padx=(0, 8), pady=8,
        )
        engine_widget = ttk.Combobox(
            body, textvariable=values["engine"], values=tuple(engine_choices.values()),
            state="disabled", width=28,
        )
        engine_widget.grid(row=3, column=1, columnspan=3, sticky="ew", pady=8)
        ttk.Label(body, text="字幕区域 左,上,宽,高（%）").grid(
            row=4, column=0, sticky="e", padx=(0, 8), pady=8,
        )
        ttk.Entry(body, textvariable=values["region"]).grid(
            row=4, column=1, columnspan=2, sticky="ew", pady=8,
        )
        for column in (1, 3):
            body.columnconfigure(column, weight=1)

        def source_path():
            path = Path(first.get("local_path") or "")
            if not path.is_file():
                raise RuntimeError("请先下载这条视频，再框选字幕区域或生成预览")
            return path

        def settings():
            region = values["region"].get().strip()
            Worker.subtitle_region(region)
            return {
                "subtitle_cleanup_policy": next(key for key, label in policy_choices.items() if label == values["policy"].get()),
                "subtitle_cleanup_mode": next(key for key, label in mode_choices.items() if label == values["mode"].get()),
                "subtitle_cleanup_engine": next(key for key, label in engine_choices.items() if label == values["engine"].get()),
                "subtitle_cleanup_quality": next(key for key, label in quality_choices.items() if label == values["quality"].get()),
                "subtitle_quick_method": next(key for key, label in method_choices.items() if label == values["method"].get()),
                "subtitle_region": region,
            }

        def select_region():
            try:
                def apply_region(region):
                    values["region"].set(region)
                    values["policy"].set(policy_choices["clean"])
                    if values["mode"].get() == mode_choices["ai_auto"]:
                        values["mode"].set(mode_choices["ai_manual"])
                self._show_subtitle_region_selector(
                    source_path(), values["region"].get(), apply_region, dialog,
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        ttk.Button(body, text="框选字幕区域", command=select_region).grid(
            row=4, column=3, sticky="w", padx=(8, 0), pady=8,
        )

        def update_clip_cleanup_mode(_event=None):
            uses_ai = values["mode"].get() != mode_choices["quick"]
            engine_widget.configure(state="readonly" if uses_ai else "disabled")
            field_widgets["method"].configure(state="disabled" if uses_ai else "readonly")

        field_widgets["mode"].bind("<<ComboboxSelected>>", update_clip_cleanup_mode)
        update_clip_cleanup_mode()

        def preview():
            try:
                task_values = settings()
                if task_values["subtitle_cleanup_policy"] != "clean":
                    raise RuntimeError("请先把“本条素材处理”设置为“需要清理”")
                preview_dir = app_dir() / "subtitle-cleanup-previews"
                preview_dir.mkdir(parents=True, exist_ok=True)
                output = preview_dir / ("clip-%s-%s.mp4" % (first["id"], secrets.token_hex(5)))
                preview_button.config(state="disabled")

                def run_preview():
                    try:
                        Worker(self.config()).clean_hard_subtitles(
                            task_values, source_path(), output, preview_seconds=5,
                        )
                        self.events.put(("subtitle_cleanup_preview", {
                            "button": preview_button, "path": str(output),
                        }))
                    except Exception as exc:
                        self.events.put(("subtitle_cleanup_preview", {
                            "button": preview_button, "error": str(exc),
                        }))
                threading.Thread(target=run_preview, daemon=True).start()
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        preview_button = ttk.Button(body, text="先生成首条素材5秒预览", command=preview)
        preview_button.grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 0))

        def process_full():
            try:
                saved = settings()
                if saved["subtitle_cleanup_policy"] != "clean":
                    raise RuntimeError("请先把“本条素材处理”设置为“需要清理”")
                self._save_clip_cleanup_settings(rows, saved)
                current_rows = self.selection_store.get_many(ids)
                self._refresh_selection_tree()
                self._start_full_subtitle_cleanup(
                    self._active_selection_task(), current_rows, process_button,
                )
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        process_button = ttk.Button(body, text="立即处理完整素材", command=process_full)
        process_button.grid(row=5, column=2, sticky="w", padx=(8, 0), pady=(16, 0))
        ttk.Button(
            body, text="查看处理后素材", command=self.preview_cleaned_selected_video,
        ).grid(row=5, column=3, sticky="w", padx=(8, 0), pady=(16, 0))

        def save_settings():
            try:
                saved = settings()
                self._save_clip_cleanup_settings(rows, saved)
                dialog.destroy()
                self._refresh_selection_tree()
            except Exception as exc:
                messagebox.showerror(APP_TITLE, str(exc), parent=dialog)

        actions = ttk.Frame(dialog, padding=(18, 0, 18, 16))
        actions.pack(fill="x")
        ttk.Button(actions, text="保存", command=save_settings).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="left")

    def preview_review_source(self):
        selected = self.review_source_tree.selection()
        if not selected:
            messagebox.showerror(APP_TITLE, "请先选择要预览的源视频")
            return
        task = self._active_selection_task()
        row = next(
            (item for item in self.selection_store.list_composition(task["id"])
             if item["id"] == int(selected[0])),
            None,
        ) if task else None
        try:
            self._open_local_path(Path((row or {}).get("file_path") or ""))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, "分镜素材文件不可用：%s" % exc)

    @staticmethod
    def _voice_signature(task):
        values = {
            key: task.get(key) or ""
            for key in (
                "tts_provider", "tts_voice", "tts_model_id", "tts_speed", "tts_volume",
            )
        }
        return hashlib.sha256(
            json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _mix_source_path(row):
        processed_value = row.get("processed_path") or ""
        processed = Path(processed_value) if processed_value else None
        if row.get("processing_status") == "ready" and processed and processed.is_file():
            return processed
        cleaned_value = row.get("subtitle_cleaned_path") or ""
        cleaned = Path(cleaned_value) if cleaned_value else None
        if row.get("subtitle_cleanup_status") == "ready" and cleaned and cleaned.is_file():
            return cleaned
        local_value = row.get("local_path") or ""
        return Path(local_value) if local_value else None

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
        rows = self.selection_store.get_many(ids)
        selected_ids = {row["id"] for row in rows}
        task = self._active_selection_task()
        remaining_paths = {
            str(Path(row.get("local_path") or "").resolve())
            for row in (self.selection_store.list(task["id"]) if task else [])
            if row["id"] not in selected_ids and row.get("local_path")
        }
        for row in rows:
            path = Path(row["local_path"]) if row["local_path"] else None
            if (
                path and path.is_file() and not row["url"].startswith("file:")
                and row.get("record_kind") != "derived_clip"
                and str(path.resolve()) not in remaining_paths
            ):
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
        worker = self.worker or Worker(
            self.config(), lambda event, data: self.events.put((event, data)),
        )
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

            def clip_spec(row, path):
                return {
                    "record_id": row["id"],
                    "clip_name": row.get("clip_name") or row.get("video_id") or "",
                    "clip_type": row.get("clip_type") or "unknown",
                    "duration": row.get("duration") or 0,
                    "path": path,
                    "trim_start": row.get("trim_start") or 0,
                    "trim_end": row.get("trim_end") or 0,
                    "subtitle_cleanup_policy": row.get("subtitle_cleanup_policy") or "inherit",
                    "subtitle_cleanup_mode": row.get("subtitle_cleanup_mode") or "quick",
                    "subtitle_cleanup_engine": row.get("subtitle_cleanup_engine") or "sttn",
                    "subtitle_cleanup_quality": row.get("subtitle_cleanup_quality") or "standard",
                    "subtitle_quick_method": row.get("subtitle_quick_method") or "blur",
                    "subtitle_region": row.get("subtitle_region") or "5,72,90,22",
                    "subtitle_cleaned_path": row.get("subtitle_cleaned_path") or "",
                    "subtitle_cleanup_signature": row.get("subtitle_cleanup_signature") or "",
                }

            for index, row in enumerate(rows, 1):
                if row.get("copyright_status") == "restricted":
                    raise RuntimeError("视频 %s 已标记为限制使用，不能加入成片" % (row.get("video_id") or row["id"]))
                existing = Path(row["local_path"]) if row["local_path"] else None
                if existing and existing.is_file() and row["status"] in ("downloaded", "ready_review", "done"):
                    clips.append(clip_spec(row, existing))
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
                    clips.append(clip_spec(row, path))
                except Exception as exc:
                    fallback = existing if existing and existing.is_file() else target
                    if fallback.is_file() and worker.probe_duration(fallback) > 0:
                        self.selection_store.update(
                            row["id"], status="downloaded", local_path=str(fallback),
                            error="重新下载暂时失败，已保留并复用原有完整视频：%s" % exc,
                        )
                        clips.append(clip_spec(row, fallback))
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

    def process_selected_clip(self):
        task = self._active_selection_task()
        ids = self._selection_ids()
        if not task or len(ids) != 1:
            messagebox.showerror(APP_TITLE, "请选择一条已经完成初剪和分类的片段")
            return
        row = self.selection_store.get_many(ids)[0]
        source = Path(row.get("local_path") or "")
        if not source.is_file():
            messagebox.showerror(APP_TITLE, "请先下载这条视频")
            return
        if row.get("clip_type") not in ("talking_face", "face_no_speech", "no_face"):
            messagebox.showerror(APP_TITLE, "请先人工标记片段类型")
            return
        cleanup_policy = row.get("subtitle_cleanup_policy") or "inherit"
        if cleanup_policy == "inherit":
            messagebox.showerror(APP_TITLE, "请先人工决定这条片段是否需要处理字幕")
            return
        if cleanup_policy == "clean":
            cleaned = Path(row.get("subtitle_cleaned_path") or "")
            if row.get("subtitle_cleanup_status") != "ready" or not cleaned.is_file():
                messagebox.showerror(APP_TITLE, "这条片段已标记需要处理字幕，请先完成字幕清理")
                return
            source = cleaned
        try:
            prepared_task = Worker.prepare_edit_workflow(task, 1)
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not prepared_task.get("tts_voice"):
            messagebox.showerror(APP_TITLE, "请先选择并保存当前项目统一使用的音色")
            return
        uses_heygen = row.get("clip_type") == "talking_face"
        slot_key = self._selected_storyboard_slot()
        storyboard = self.selection_store.list_storyboard(task["id"])
        if storyboard and not slot_key:
            messagebox.showerror(
                APP_TITLE,
                "请先在上方视频整体方案中选择本次要制作的分镜要求。\n"
                "加工结果只会成为候选素材，不会自动加入成片。",
            )
            return
        if uses_heygen:
            if not self.vars["heygen_api_key"].get().strip():
                messagebox.showerror(
                    APP_TITLE,
                    "口播人脸片段需要 HeyGen。请先到“连接与配置 → HeyGen口型同步”填写 API Key。",
                )
                return
            if not messagebox.askyesno(
                APP_TITLE,
                "这条片段被标记为“口播人脸”，将先生成英文配音片，再上传 HeyGen 生成口型同步片段。\n"
                "此操作会消耗 HeyGen 额度，是否继续？",
            ):
                return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有媒体处理正在运行")
            return
        self.selection_busy = True
        self.selection_store.update(
            row["id"], processing_status="processing", processing_error="",
            processed_path="", processed_kind="", voice_signature="",
        )
        self._refresh_selection_tree()
        config = self.config()

        def run_process():
            worker = self.worker or Worker(
                config, lambda event, data: self.events.put((event, data)),
            )
            try:
                output_dir = (
                    worker.root / str(task["id"]) / "processed-clips"
                    / ("clip-%s-%s" % (row["id"], secrets.token_hex(5)))
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                clip_task = dict(prepared_task)
                clip_task.update({
                    "background_music": "", "transition": "none",
                    "subtitle_region": row.get("subtitle_region") or clip_task.get("subtitle_region"),
                })
                output, _subtitle = worker.compose_video(clip_task, [{
                    "record_id": row["id"],
                    "clip_name": row.get("clip_name") or row.get("video_id") or "",
                    "clip_type": row.get("clip_type"),
                    "duration": row.get("duration") or 0,
                    "path": source,
                    "trim_start": row.get("trim_start") or 0,
                    "trim_end": row.get("trim_end") or 0,
                    "subtitle_cleanup_policy": "skip",
                }], output_dir / "local-render")
                final_path = output
                kind = "英文配音片段（无需口型）"
                if uses_heygen:
                    audio = worker.prepare_heygen_audio(
                        output, output_dir / "heygen-audio.mp3",
                    )
                    final_path = worker.heygen_lipsync(
                        output, audio, output_dir / "output-heygen.mp4",
                        title=clip_task.get("name") or row.get("clip_name") or "LightLink",
                    )
                    kind = "HeyGen口型片段"
                role = task.get("business_role") or {}
                track = task.get("project_track") or {}
                scope = task.get("content_scope") or {}
                slot = next(
                    (item for item in storyboard if item["slot_key"] == slot_key),
                    {},
                )
                asset_uuid = self.selection_store.register_asset({
                    "name": row.get("clip_name") or row.get("video_id") or final_path.stem,
                    "file_path": str(final_path), "source_path": str(source),
                    "source_task_id": task["id"], "source_record_id": row["id"],
                    "asset_kind": "heygen_variant" if uses_heygen else "voice_variant",
                    "clip_type": row.get("clip_type") or "unknown",
                    "role_code": role.get("code") or "", "role_name": role.get("name") or "",
                    "track_code": track.get("code") or "", "track_name": track.get("name") or "",
                    "scope_code": scope.get("code") or "", "scope_name": scope.get("name") or "",
                    "shot_purpose": (
                        slot.get("purpose") or slot.get("name") or row.get("clip_name") or
                        scope.get("name") or task.get("name") or "通用分镜"
                    ),
                    "language": clip_task.get("target_language") or "",
                    "aspect_ratio": clip_task.get("aspect_ratio") or "",
                    "duration": worker.probe_duration(final_path),
                    "subtitle_state": "cleaned" if cleanup_policy == "clean" else "clean",
                    "voice_signature": self._voice_signature(clip_task),
                    "copyright_status": row.get("copyright_status") or "unreviewed",
                    "metadata": {
                        "source_record_id": row["id"],
                        "candidate_for_shot": slot_key,
                        "processed_kind": kind,
                    },
                })
                self.selection_store.update(
                    row["id"], processed_path=str(final_path), processed_kind=kind,
                    processing_status="ready", processing_error="",
                    voice_signature=self._voice_signature(clip_task),
                    library_asset_uuid=asset_uuid,
                )
                if slot_key:
                    self.selection_store.mark_storyboard_candidate(task["id"], slot_key)
                try:
                    indexed = self.selection_store.get_asset(asset_uuid)
                    worker.sync_local_assets(self._asset_sync_payload(
                        [indexed], work_dir=config.get("work_dir"),
                    ))
                except Exception as sync_error:
                    self.events.put(("log", {
                        "message": "片段已保存到本地素材库；Odoo 索引稍后重试：%s" % sync_error,
                    }))
                self.events.put(("clip_process_done", {
                    "record_id": row["id"], "path": str(final_path), "kind": kind,
                    "asset_uuid": asset_uuid,
                }))
            except Exception as exc:
                self.selection_store.update(
                    row["id"], processing_status="failed", processing_error=str(exc),
                    processed_path="", processed_kind="", voice_signature="",
                )
                self.events.put(("clip_process_error", {"error": str(exc)}))

        threading.Thread(target=run_process, daemon=True).start()

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

    def mix_assembly_clips(self):
        task = self._active_selection_task()
        if not task:
            messagebox.showerror(APP_TITLE, "请先选择一个视频项目")
            return
        if self.selection_busy:
            messagebox.showinfo(APP_TITLE, "已有媒体处理正在运行")
            return
        storyboard = self.selection_store.list_storyboard(task["id"])
        if not storyboard:
            messagebox.showerror(APP_TITLE, "当前项目没有视频方案和分镜清单，不能直接拼接成片")
            return
        rows = self.selection_store.list_composition(task["id"])
        selected_slots = {row["slot_key"] for row in rows}
        required_missing = [
            slot["name"] for slot in storyboard
            if slot["required"] and slot["slot_key"] not in selected_slots
        ]
        if required_missing:
            messagebox.showerror(
                APP_TITLE,
                "视频方案尚未完成，以下必要分镜还没有从素材库选定：\n" +
                "、".join(required_missing),
            )
            return
        if not rows:
            messagebox.showerror(APP_TITLE, "成片时间线为空，请先从分镜素材库选择")
            return
        current_voice = self._voice_signature(task)
        invalid_files = [row for row in rows if not Path(row.get("file_path") or "").is_file()]
        invalid_voice = [
            row for row in rows
            if row.get("asset_kind") not in ("standard_shot", "music")
            and row.get("voice_signature") != current_voice
        ]
        if invalid_files or invalid_voice:
            details = []
            if invalid_files:
                details.append("文件不存在：" + "、".join(row["name"] for row in invalid_files[:5]))
            if invalid_voice:
                details.append(
                    "与当前项目音色不一致：" + "、".join(row["name"] for row in invalid_voice[:5])
                )
            messagebox.showerror(APP_TITLE, "成片时间线不能生成：\n" + "\n".join(details))
            return
        order_text = "\n".join(
            "%s. %s ← %s" % (index, row["shot_name"], row["name"])
            for index, row in enumerate(rows, 1)
        )
        if not messagebox.askyesno(
            APP_TITLE,
            "将严格按成片时间线拼接，不会再次翻译、去字幕或调用 HeyGen：\n\n%s\n\n"
            "是否生成最终审核稿？" % order_text,
        ):
            return
        self.selection_busy = True
        config = self.config()

        def run_stitch():
            worker = self.worker or Worker(
                config, lambda event, data: self.events.put((event, data)),
            )
            try:
                version_no, mix_dir = create_version_directory(
                    worker.root / str(task["id"]),
                    self.selection_store.next_render_version(task["id"]),
                )
                clips = [{
                    "record_id": row["id"],
                    "clip_name": row.get("name") or row.get("shot_name") or "",
                    "clip_type": row.get("clip_type") or "unknown",
                    "processed_kind": row.get("asset_kind") or "已处理分镜",
                    "path": Path(row["file_path"]),
                } for row in rows]
                output, subtitle = worker.stitch_processed_clips(task, clips, mix_dir)
                manifest = {
                    "schema": "lightlink-media-v2",
                    "video_plan_summary": task.get("video_plan_summary") or "",
                    "used_assets": [{
                        "sequence": index,
                        "composition_id": row["id"],
                        "asset_uuid": row["asset_uuid"],
                        "shot_key": row["slot_key"],
                        "shot_name": row["shot_name"],
                        "name": row["name"],
                        "asset_kind": row["asset_kind"],
                    } for index, row in enumerate(rows, 1)],
                }
                updated_task = dict(task)
                updated_task["output_manifest"] = manifest
                self.selection_store.update_task(updated_task, status="ready_review")
                self.selection_store.set_task_result(
                    task["id"], output, subtitle or "", status="ready_review",
                    version_no=version_no,
                    source_video_ids=[row["id"] for row in rows],
                )
                self.events.put(("selection_mix_ready", {"task": task, "output": str(output)}))
            except Exception as exc:
                self.events.put(("selection_operation_error", {"error": str(exc)}))

        threading.Thread(target=run_stitch, daemon=True).start()

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
        manifest = task.get("output_manifest") or {}
        asset_uuids = [
            item.get("asset_uuid") for item in manifest.get("used_assets", [])
            if item.get("asset_uuid")
        ]
        assets = [
            asset for asset_uuid in asset_uuids
            for asset in [self.selection_store.get_asset(asset_uuid)] if asset
        ]
        asset_payload = self._asset_sync_payload(assets) if assets else []
        self.selection_busy = True

        def run_upload():
            worker = self.worker or Worker(self.config())
            try:
                if asset_payload:
                    worker.sync_local_assets(asset_payload)
                worker.complete(
                    task, result, subtitle if subtitle and subtitle.is_file() else None,
                    manifest=manifest,
                )
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
