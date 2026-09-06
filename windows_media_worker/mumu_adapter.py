import os
import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode


DOUYIN_PACKAGE = "com.ss.android.ugc.aweme"
SELECTOR_PACKAGE = "com.lightlink.selector"
DEFAULT_SERIAL = "127.0.0.1:7555"


def _candidate_roots():
    roots = []
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if base:
            roots.append(Path(base) / "Netease" / "MuMu")
            roots.append(Path(base) / "Netease" / "MuMuPlayer-12.0")
    roots.extend((
        Path("D:/Program Files/Netease/MuMu"),
        Path("D:/Program Files/Netease/MuMuPlayer-12.0"),
        Path("D:/MuMuPlayer-12.0"),
    ))
    return roots


def find_adb(configured=""):
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError("配置的 MuMu ADB 不存在：%s" % path)
    system_adb = shutil.which("adb")
    if system_adb:
        return system_adb
    relative_paths = ("nx_main/adb.exe", "shell/adb.exe", "adb.exe")
    for root in _candidate_roots():
        for relative in relative_paths:
            candidate = root / relative
            if candidate.is_file():
                return str(candidate)
        for candidate in root.glob("nx_device/*/shell/adb.exe"):
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError("未找到 MuMu ADB，请安装 MuMu 模拟器或在配置中选择 adb.exe")


def find_player(configured=""):
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError("配置的 MuMu 主程序不存在：%s" % path)
    for root in _candidate_roots():
        for name in ("nx_main/MuMuNxMain.exe", "shell/MuMuPlayer.exe", "MuMuPlayer.exe", "nx_main/3.0/MuMuPlayer.exe"):
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    return ""


def discover_serial(runner=None):
    run = runner or subprocess.run
    for root in _candidate_roots():
        cli = root / "nx_main" / "mumu-cli.exe"
        if not cli.is_file():
            continue
        result = run(
            [str(cli), "info", "--vmindex", "all"], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        if result.returncode:
            continue
        try:
            players = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            continue
        for player in players.values():
            host, port = player.get("adb_host_ip"), player.get("adb_port")
            if player.get("is_android_started") and host and port:
                return "%s:%s" % (host, port)
    return ""


class MumuBridge:
    def __init__(self, adb_path="", serial=DEFAULT_SERIAL, player_path="", runner=None,
                 selector_port=0, selector_token=""):
        self.adb = find_adb(adb_path)
        self.runner = runner or subprocess.run
        self.serial = (serial or discover_serial(self.runner) or DEFAULT_SERIAL).strip()
        self.player = find_player(player_path)
        self.selector_port = int(selector_port or 0)
        self.selector_token = selector_token or ""

    def _run(self, *args, timeout=30, check=True):
        result = self.runner(
            [self.adb, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        if check and result.returncode:
            detail = (result.stderr or result.stdout or "ADB 命令失败").strip()
            raise RuntimeError(detail)
        return result

    def connect(self):
        result = self._run("connect", self.serial, check=False)
        output = "%s\n%s" % (result.stdout or "", result.stderr or "")
        if result.returncode or not any(word in output.lower() for word in ("connected", "already connected")):
            raise RuntimeError("无法连接 MuMu（%s），请先启动模拟器并开启 ADB：%s" % (self.serial, output.strip()))
        state = self._run("-s", self.serial, "get-state").stdout.strip()
        if state != "device":
            raise RuntimeError("MuMu ADB 状态异常：%s" % (state or "unknown"))
        return {"adb": self.adb, "serial": self.serial, "state": state}

    def start_player(self):
        if not self.player:
            raise FileNotFoundError("未找到 MuMu 主程序，请在配置中选择 MuMuPlayer.exe")
        subprocess.Popen([self.player], cwd=str(Path(self.player).parent))

    def connect_or_start(self):
        try:
            return self.connect()
        except RuntimeError:
            if not self.player:
                raise
            self.start_player()
            last_error = None
            for _attempt in range(30):
                time.sleep(2)
                try:
                    return self.connect()
                except RuntimeError as exc:
                    last_error = exc
            raise RuntimeError("MuMu 启动后仍无法连接 ADB：%s" % last_error)

    def prepare_image_search(self, image_path, task_id):
        self.connect_or_start()
        remote = "/sdcard/Pictures/LightLink/task-%s.jpg" % task_id
        self._run("-s", self.serial, "shell", "mkdir", "-p", "/sdcard/Pictures/LightLink")
        self._run("-s", self.serial, "push", str(Path(image_path).resolve()), remote, timeout=120)
        self._run(
            "-s", self.serial, "shell", "am", "broadcast",
            "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", "file://" + remote,
        )
        packages = self._run("-s", self.serial, "shell", "pm", "list", "packages", DOUYIN_PACKAGE).stdout
        if DOUYIN_PACKAGE not in packages:
            raise RuntimeError("MuMu 中尚未安装抖音 App")
        selector_packages = self._run(
            "-s", self.serial, "shell", "pm", "list", "packages", SELECTOR_PACKAGE,
        ).stdout
        if SELECTOR_PACKAGE not in selector_packages:
            raise RuntimeError("MuMu 中尚未安装 LightLink 选片 APK")
        if not self.selector_port or not self.selector_token:
            raise RuntimeError("Windows 选片接收通道尚未启动")
        self._run(
            "-s", self.serial, "reverse",
            "tcp:%s" % self.selector_port, "tcp:%s" % self.selector_port,
        )
        configure_url = "lightlink://configure?" + urlencode({
            "task_id": int(task_id), "port": self.selector_port,
            "token": self.selector_token,
        })
        self._run(
            "-s", self.serial, "shell", "am", "start", "-W",
            "-a", "android.intent.action.VIEW", "-d", configure_url,
            SELECTOR_PACKAGE,
        )
        self._run("-s", self.serial, "shell", "am", "force-stop", DOUYIN_PACKAGE)
        self._run(
            "-s", self.serial, "shell", "monkey", "-p", DOUYIN_PACKAGE,
            "-c", "android.intent.category.LAUNCHER", "1",
        )
        time.sleep(4)
        size_output = self._run("-s", self.serial, "shell", "wm", "size").stdout
        match = __import__("re").search(r"Physical size:\s*(\d+)x(\d+)", size_output)
        if not match:
            raise RuntimeError("无法读取 MuMu 屏幕尺寸")
        width, height = int(match.group(1)), int(match.group(2))
        # 抖音首页搜索、图搜相机、相册、最新图片。坐标按屏幕比例计算，
        # MuMu 分辨率变化时仍能保持相同位置。
        for x_ratio, y_ratio, delay in (
            (0.958, 0.032, 2),
            (0.874, 0.032, 2),
            (0.781, 0.875, 2),
            (0.122, 0.129, 6),
        ):
            self._run(
                "-s", self.serial, "shell", "input", "tap",
                str(round(width * x_ratio)), str(round(height * y_ratio)),
            )
            time.sleep(delay)
        activity = self._run(
            "-s", self.serial, "shell", "dumpsys", "activity", "activities",
        ).stdout
        if "VisualSearchActivity" not in activity:
            raise RuntimeError("抖音未进入图片搜索结果页，请保持抖音已登录后重试")
        return remote


def check_mumu(config):
    bridge = MumuBridge(
        config.get("mumu_adb", ""), config.get("mumu_serial", ""),
        config.get("mumu_player", ""),
    )
    return bridge.connect()


def install_selector_apk(config, apk_path):
    apk = Path(apk_path)
    if not apk.is_file():
        raise FileNotFoundError("未找到 LightLink 选片 APK：%s" % apk)
    bridge = MumuBridge(
        config.get("mumu_adb", ""), config.get("mumu_serial", ""),
        config.get("mumu_player", ""),
    )
    bridge.connect_or_start()
    result = bridge._run(
        "-s", bridge.serial, "install", "-r", str(apk.resolve()), timeout=180,
    )
    if "Success" not in result.stdout:
        raise RuntimeError("APK 安装未成功：%s" % result.stdout.strip())
    return {"serial": bridge.serial, "apk": str(apk.resolve())}
