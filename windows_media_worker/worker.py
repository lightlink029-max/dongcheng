import mimetypes
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import textwrap
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from douyin_adapter import download_video, get_video_metadata
from mumu_adapter import MumuBridge
from speech import asr_available, synthesize, transcribe

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


def create_version_directory(task_root, first_version):
    version = max(1, int(first_version))
    while True:
        target = Path(task_root) / ("mix-output-v%s" % version)
        try:
            target.mkdir(parents=True)
            return version, target
        except FileExistsError:
            version += 1


class Worker:
    DEFAULT_SUBTITLE_REGION = (0.05, 0.72, 0.90, 0.22)
    HEYGEN_BASE_URL = "https://api.heygen.com"
    HEYGEN_DIRECT_UPLOAD_LIMIT = 32 * 1024 * 1024
    _ollama_start_lock = threading.Lock()

    def __init__(self, config, event_callback=None):
        self.config = config
        self.base = config["odoo_url"].rstrip("/")
        self.worker_id = config.get("worker_id") or os.environ.get("COMPUTERNAME", "windows-worker")
        self.headers = {
            "Authorization": "Bearer " + config["worker_token"],
            "X-LightLink-Worker-ID": self.worker_id,
        }
        self.root = Path(config.get("work_dir", "jobs")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback or (lambda event, data: None)

    def emit(self, event, **data):
        self.event_callback(event, data)

    def ffmpeg(self):
        configured = self.config.get("ffmpeg")
        if configured and configured != "ffmpeg":
            return configured
        return imageio_ffmpeg.get_ffmpeg_exe() if imageio_ffmpeg else "ffmpeg"

    def probe_duration(self, path):
        result = subprocess.run(
            [self.ffmpeg(), "-i", str(path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if not match:
            return 0.0
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))

    @staticmethod
    def _heygen_response_data(response):
        try:
            payload = response.json()
        except (TypeError, ValueError):
            payload = {}
        if 200 <= int(response.status_code) < 300:
            return payload.get("data") or {}
        error = payload.get("error") or {}
        message = error.get("message") or payload.get("message") or response.text
        raise RuntimeError(
            "HeyGen 请求失败（HTTP %s）：%s" %
            (response.status_code, str(message or "未知错误").strip())
        )

    def _heygen_api_key(self):
        api_key = (self.config.get("heygen", {}).get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("尚未配置 HeyGen API Key，请先到“连接与配置 → HeyGen口型同步”填写并保存")
        return api_key

    def heygen_upload_asset(self, path):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError("HeyGen 上传文件不存在：%s" % path)
        size = path.stat().st_size
        if size > self.HEYGEN_DIRECT_UPLOAD_LIMIT:
            raise RuntimeError(
                "文件 %.1f MB，超过 HeyGen 直接上传 32 MB 限制。请先压缩视频后再试。" %
                (size / 1024 / 1024)
            )
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.emit("log", message="正在上传到 HeyGen：%s（%.1f MB）" % (path.name, size / 1024 / 1024))
        with path.open("rb") as stream:
            response = requests.post(
                self.HEYGEN_BASE_URL + "/v3/assets",
                headers={"x-api-key": self._heygen_api_key()},
                files={"file": (path.name, stream, content_type)},
                timeout=(20, 300),
            )
        data = self._heygen_response_data(response)
        asset_id = data.get("asset_id")
        if not asset_id:
            raise RuntimeError("HeyGen 上传成功但没有返回 asset_id")
        return asset_id

    def prepare_heygen_audio(self, video, output):
        """Extract the approved mix audio and pad it to the exact video duration."""
        video, output = Path(video), Path(output)
        duration = self.probe_duration(video)
        if duration <= 0:
            raise RuntimeError("无法读取审核稿时长，不能执行 HeyGen 口型同步")
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            self.ffmpeg(), "-y", "-i", str(video), "-vn", "-af", "apad",
            "-t", str(duration), "-c:a", "libmp3lame", "-b:a", "128k", str(output),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise RuntimeError("审核稿没有可用的英文配音音轨，无法执行 HeyGen 口型同步")
        return output

    def heygen_lipsync(self, video, audio, output, title=""):
        """Create and download a HeyGen lip-sync render without changing duration."""
        video, audio, output = Path(video), Path(audio), Path(output)
        source_duration = self.probe_duration(video)
        video_asset = self.heygen_upload_asset(video)
        audio_asset = self.heygen_upload_asset(audio)
        mode = self.config.get("heygen", {}).get("mode") or "precision"
        if mode not in ("speed", "precision"):
            mode = "precision"
        response = requests.post(
            self.HEYGEN_BASE_URL + "/v3/lipsyncs",
            headers={
                "x-api-key": self._heygen_api_key(),
                "Content-Type": "application/json",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "video": {"type": "asset_id", "asset_id": video_asset},
                "audio": {"type": "asset_id", "asset_id": audio_asset},
                "title": title or video.stem,
                "mode": mode,
                "keep_the_same_format": True,
                "enable_dynamic_duration": False,
                "disable_music_track": False,
                "enable_speech_enhancement": False,
                "enable_watermark": False,
                "fps_mode": "passthrough",
            },
            timeout=(20, 120),
        )
        lipsync_id = self._heygen_response_data(response).get("lipsync_id")
        if not lipsync_id:
            raise RuntimeError("HeyGen 没有返回口型同步任务 ID")
        self.emit("log", message="HeyGen 口型同步任务已提交：%s" % lipsync_id)
        poll_seconds = max(3, int(self.config.get("heygen", {}).get("poll_seconds") or 10))
        timeout_seconds = max(60, int(self.config.get("heygen", {}).get("timeout_seconds") or 3600))
        deadline = time.monotonic() + timeout_seconds
        video_url = ""
        while time.monotonic() < deadline:
            status_response = requests.get(
                self.HEYGEN_BASE_URL + "/v3/lipsyncs/" + lipsync_id,
                headers={"x-api-key": self._heygen_api_key()}, timeout=(20, 60),
            )
            data = self._heygen_response_data(status_response)
            status = (data.get("status") or "").lower()
            if status == "completed":
                video_url = data.get("video_url") or ""
                break
            if status == "failed":
                raise RuntimeError("HeyGen 口型同步失败：%s" % (data.get("failure_message") or "未知错误"))
            self.emit("log", message="HeyGen 处理中：%s" % (status or "pending"))
            time.sleep(poll_seconds)
        if not video_url:
            raise RuntimeError("HeyGen 口型同步等待超时，可稍后在 HeyGen 后台查看任务 %s" % lipsync_id)

        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(output.suffix + ".part")
        download = requests.get(video_url, stream=True, timeout=(20, 300))
        if not 200 <= int(download.status_code) < 300:
            self._heygen_response_data(download)
        try:
            with partial.open("wb") as stream:
                for chunk in download.iter_content(1024 * 1024):
                    if chunk:
                        stream.write(chunk)
            if not partial.is_file() or not partial.stat().st_size:
                raise RuntimeError("HeyGen 返回的成片为空")
            partial.replace(output)
        finally:
            partial.unlink(missing_ok=True)
        result_duration = self.probe_duration(output)
        if source_duration > 0 and result_duration > 0 and abs(result_duration - source_duration) > 0.5:
            self.emit("log", message=(
                "提醒：HeyGen 返回时长 %.2f 秒，与原审核稿 %.2f 秒相差 %.2f 秒" %
                (result_duration, source_duration, abs(result_duration - source_duration))
            ))
        return output

    def heygen_lipsync_timeline(self, video, timeline, output, title="", width=1080, height=1920):
        """Apply HeyGen only to talking-face segments, then rebuild the approved timeline."""
        video, output = Path(video), Path(output)
        segments = [item for item in timeline if float(item.get("end") or 0) > float(item.get("start") or 0)]
        talking = [item for item in segments if item.get("clip_type") == "talking_face"]
        if not talking:
            raise RuntimeError("当前审核稿没有标记为“口播人脸”的片段，不需要执行 HeyGen")
        output.parent.mkdir(parents=True, exist_ok=True)
        ready_parts = []
        for index, item in enumerate(segments, 1):
            start = float(item["start"])
            duration = float(item["end"]) - start
            extracted = output.parent / ("route-%02d-source.mp4" % index)
            result = subprocess.run([
                self.ffmpeg(), "-y", "-ss", "%.3f" % start, "-i", str(video),
                "-t", "%.3f" % duration, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "22", "-c:a", "aac", "-movflags", "+faststart", str(extracted),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode or not extracted.is_file():
                raise RuntimeError("无法提取第 %s 个成片片段：%s" % (index, result.stderr[-500:]))
            routed = extracted
            if item.get("clip_type") == "talking_face":
                audio = self.prepare_heygen_audio(
                    extracted, output.parent / ("route-%02d-audio.mp3" % index),
                )
                routed = self.heygen_lipsync(
                    extracted, audio, output.parent / ("route-%02d-heygen.mp4" % index),
                    title="%s - %s" % (title or video.stem, item.get("clip_name") or index),
                )
            else:
                self.emit(
                    "log", message="片段 %s 为%s，已跳过 HeyGen" % (
                        item.get("clip_name") or index,
                        {"face_no_speech": "非口播人脸", "no_face": "无人脸"}.get(
                            item.get("clip_type"), "未分类",
                        ),
                    ),
                )
            ready = output.parent / ("route-%02d-ready.mp4" % index)
            normalize = subprocess.run([
                self.ffmpeg(), "-y", "-i", str(routed),
                "-vf", (
                    "scale=%s:%s:force_original_aspect_ratio=decrease," % (width, height)
                    + "pad=%s:%s:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p" %
                    (width, height)
                ),
                "-af", "apad", "-t", "%.3f" % duration,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", str(ready),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if normalize.returncode or not ready.is_file():
                raise RuntimeError("无法标准化第 %s 个成片片段：%s" % (index, normalize.stderr[-500:]))
            ready_parts.append(ready)
        concat = output.parent / "heygen-route-concat.txt"
        concat.write_text("".join(
            "file '%s'\n" % str(path.resolve()).replace(chr(39), chr(39) * 2)
            for path in ready_parts
        ), encoding="utf-8")
        result = subprocess.run([
            self.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode or not output.is_file():
            raise RuntimeError("口型片段重组失败：%s" % result.stderr[-700:])
        return output

    def create_video_cover(self, path, target):
        duration = self.probe_duration(path)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        seek = min(1.0, max(0.0, duration / 3))
        result = subprocess.run([
            self.ffmpeg(), "-y", "-ss", str(seek), "-i", str(path),
            "-frames:v", "1", "-vf", "scale=180:-2", str(target),
        ], capture_output=True)
        return duration, target if result.returncode == 0 and target.is_file() else None

    def extract_video_frame(self, path, target, at_seconds=1.0):
        """Write one full-size frame for subtitle-region selection."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            self.ffmpeg(), "-y", "-ss", str(max(0.0, float(at_seconds))),
            "-i", str(path), "-frames:v", "1", str(target),
        ], capture_output=True)
        if result.returncode or not target.is_file():
            raise RuntimeError("无法读取视频画面，请确认视频文件完整")
        return target

    @classmethod
    def subtitle_region(cls, value):
        """Return a validated normalized x/y/width/height subtitle rectangle."""
        if value in (None, "", [], ()):
            return cls.DEFAULT_SUBTITLE_REGION
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
        elif isinstance(value, (list, tuple)):
            parts = list(value)
        else:
            parts = []
        try:
            numbers = [float(item) for item in parts]
        except (TypeError, ValueError):
            numbers = []
        if len(numbers) != 4:
            raise ValueError("字幕区域必须填写左、上、宽、高四个百分比")
        # The desktop UI stores percentages; Odoo/API callers may send 0..1.
        if any(number > 1 for number in numbers):
            numbers = [number / 100 for number in numbers]
        x, y, width, height = numbers
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise ValueError("字幕区域必须是有效的左、上、宽、高百分比")
        return tuple(numbers)

    @staticmethod
    def _subtitle_cleanup_quality(quality):
        return {
            "fast": ("superfast", "26", 8),
            "high": ("medium", "18", 20),
        }.get(quality, ("veryfast", "22", 14))

    def _quick_subtitle_filter(self, task):
        x, y, width, height = self.subtitle_region(task.get("subtitle_region"))
        method = task.get("subtitle_quick_method") or "blur"
        _preset, _crf, blur_radius = self._subtitle_cleanup_quality(
            task.get("subtitle_cleanup_quality") or "standard"
        )
        if method == "cover":
            return (
                "[0:v]drawbox=x=iw*%.6f:y=ih*%.6f:w=iw*%.6f:h=ih*%.6f:"
                "color=black@0.78:t=fill[outv]" % (x, y, width, height)
            )
        if method == "crop":
            if y + height < 0.96:
                raise ValueError("裁切方式只适用于靠近画面底部的字幕区域")
            return (
                "[0:v]crop=iw:ih*%.6f:0:0,"
                "scale=trunc(iw/2)*2:trunc(ih/%.6f/2)*2[outv]" % (y, y)
            )
        if method != "blur":
            raise ValueError("未知的快速字幕处理方式")
        return (
            "[0:v]split=2[base][zone];"
            "[zone]crop=iw*%.6f:ih*%.6f:iw*%.6f:ih*%.6f,"
            "boxblur=luma_radius=%s:luma_power=1[clean];"
            "[base][clean]overlay=x=main_w*%.6f:y=main_h*%.6f[outv]"
        ) % (width, height, x, y, blur_radius, x, y)

    def _run_vsr_subtitle_cleanup(self, task, source, output, preview_seconds=None):
        command = (self.config.get("local_ai", {}).get("vsr_command") or "").strip()
        executable = Path(command).expanduser() if command else None
        if not executable or not executable.is_file():
            raise RuntimeError(
                "当前素材选择了AI无痕去字幕，但尚未配置VSR/STTN适配程序；"
                "可改选“快速遮盖（无需AI）”，或到“连接与配置 → 本地AI”配置程序。"
            )
        mode = task.get("subtitle_cleanup_mode") or "ai_manual"
        engine = task.get("subtitle_cleanup_engine") or "sttn"
        if engine != "sttn":
            raise ValueError("当前版本暂不支持所选AI字幕修复模型")
        manifest = output.with_suffix(".json")
        manifest.write_text(json.dumps({
            "input_video": str(Path(source).resolve()),
            "output_video": str(output.resolve()),
            "engine": engine,
            "auto_detect": mode == "ai_auto",
            "region_percent": (
                None if mode == "ai_auto"
                else [round(value * 100, 4) for value in self.subtitle_region(task.get("subtitle_region"))]
            ),
            "quality": task.get("subtitle_cleanup_quality") or "standard",
            "preview_seconds": float(preview_seconds) if preview_seconds else None,
            "preserve_audio": True,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        runner = [str(executable)]
        if executable.suffix.lower() == ".py":
            runner.insert(0, sys.executable)
        subprocess.run(runner + [str(manifest), str(output)], check=True, capture_output=True)

    def clean_hard_subtitles(self, task, source, output, preview_seconds=None):
        """Create a cleaned copy. The source file is never modified."""
        source, output = Path(source), Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() == output.resolve():
            raise ValueError("字幕清理输出不能覆盖原始素材")
        mode = task.get("subtitle_cleanup_mode") or "quick"
        if mode == "quick":
            preset, crf, _blur = self._subtitle_cleanup_quality(
                task.get("subtitle_cleanup_quality") or "standard"
            )
            command = [
                self.ffmpeg(), "-y", "-i", str(source),
                "-filter_complex", self._quick_subtitle_filter(task),
                "-map", "[outv]", "-map", "0:a?",
            ]
            if preview_seconds:
                command += ["-t", str(float(preview_seconds))]
            command += [
                "-c:v", "libx264", "-preset", preset, "-crf", crf,
                "-c:a", "aac", "-movflags", "+faststart", str(output),
            ]
            subprocess.run(command, check=True, capture_output=True)
        elif mode in ("ai_auto", "ai_manual"):
            self._run_vsr_subtitle_cleanup(task, source, output, preview_seconds)
        else:
            raise ValueError("未知的硬字幕清理模式")
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("字幕清理程序没有生成有效的新视频")
        return output

    @staticmethod
    def subtitle_cleanup_signature(task, source):
        """Identify a prepared copy by source revision and cleanup settings."""
        source = Path(source).resolve()
        stat = source.stat()
        payload = {
            "source": str(source),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "mode": task.get("subtitle_cleanup_mode") or "quick",
            "engine": task.get("subtitle_cleanup_engine") or "sttn",
            "quality": task.get("subtitle_cleanup_quality") or "standard",
            "quick_method": task.get("subtitle_quick_method") or "blur",
            "region": [round(value, 6) for value in Worker.subtitle_region(
                task.get("subtitle_region")
            )],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def prepare_subtitle_cleanup(self, task, clip_specs, job_dir):
        if not task.get("remove_hard_subtitles") and not any(
            item.get("subtitle_cleanup_policy") == "clean" for item in clip_specs
        ):
            return clip_specs
        cleaned_specs, report = [], []
        for index, item in enumerate(clip_specs, 1):
            source = Path(item["path"])
            output = Path(job_dir) / ("subtitle-cleaned-%02d.mp4" % index)
            updated = dict(item)
            policy = item.get("subtitle_cleanup_policy") or "inherit"
            enabled = (
                policy == "clean" or
                (policy == "inherit" and bool(task.get("remove_hard_subtitles")))
            )
            if policy == "skip" or not enabled:
                report.append({"source": str(source), "status": "skipped"})
                cleaned_specs.append(updated)
                continue
            cleanup_task = dict(task)
            for field in (
                "subtitle_cleanup_mode", "subtitle_cleanup_engine",
                "subtitle_cleanup_quality",
                "subtitle_quick_method", "subtitle_region",
            ):
                if item.get(field) not in (None, ""):
                    cleanup_task[field] = item[field]
            prepared = Path(item.get("subtitle_cleaned_path") or "")
            expected_signature = self.subtitle_cleanup_signature(cleanup_task, source)
            if (
                prepared.is_file() and
                item.get("subtitle_cleanup_signature") == expected_signature
            ):
                updated["path"] = prepared
                report.append({
                    "source": str(source), "output": str(prepared), "status": "reused",
                })
                cleaned_specs.append(updated)
                continue
            try:
                updated["path"] = self.clean_hard_subtitles(cleanup_task, source, output)
                report.append({"source": str(source), "output": str(output), "status": "cleaned"})
            except Exception as exc:
                updated["path"] = source
                message = "视频%s去字幕失败，已保留并继续使用原始素材：%s" % (index, exc)
                report.append({"source": str(source), "status": "fallback", "error": str(exc)})
                self.emit("log", message=message)
                self.emit("subtitle_cleanup_warning", message=message)
            cleaned_specs.append(updated)
        (Path(job_dir) / "subtitle-cleanup-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        return cleaned_specs

    def api(self, method, path, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(method, self.base + path, headers=headers, timeout=300, **kwargs)
        response.raise_for_status()
        return response

    def claim(self):
        return self.api("POST", "/psc/local-worker/claim", json={
            "worker_id": self.worker_id,
        }).json().get("task")

    def health(self):
        return self.api("GET", "/psc/local-worker/ping").json()

    def sync_bitbrowser_environments(self, environments):
        safe_environments = []
        for item in environments:
            if not isinstance(item, dict):
                continue
            safe_environments.append({key: item.get(key) for key in (
                "id", "browserId", "seq", "name", "platform", "platformName",
                "userName", "username", "isOpen", "opened", "status",
            ) if key in item})
        return self.api(
            "POST", "/psc/local-worker/bitbrowser/environments",
            json={"worker_id": self.worker_id, "environments": safe_environments},
        ).json()

    def sync_local_assets(self, assets):
        return self.api(
            "POST", "/psc/local-worker/assets/sync",
            json={"worker_id": self.worker_id, "assets": assets},
        ).json()

    def registration_tasks(self):
        return self.api("GET", "/psc/local-worker/registration/tasks").json().get("tasks", [])

    def start_registration(self, task_id):
        return self.api("POST", f"/psc/local-worker/registration/tasks/{task_id}/start").json()

    def report_registration_environment(self, task_id, actual):
        return self.api("POST", f"/psc/local-worker/registration/tasks/{task_id}/environment", json={
            "actual_ip": actual.get("ip", ""),
            "actual_country_code": actual.get("country", ""),
            "actual_timezone": actual.get("timezone", ""),
        }).json()

    def complete_registration(self, task_id, username, profile_url, platform_account_id, screenshot):
        with Path(screenshot).open("rb") as stream:
            return self.api(
                "POST", f"/psc/local-worker/registration/tasks/{task_id}/complete",
                data={"username": username, "profile_url": profile_url,
                      "platform_account_id": platform_account_id},
                files={"screenshot": (Path(screenshot).name, stream, "image/png")},
            ).json()

    def fail_registration(self, task_id, error):
        return self.api("POST", f"/psc/local-worker/registration/tasks/{task_id}/fail",
                        json={"error": str(error)}).json()

    def publication_tasks(self):
        return self.api("GET", "/psc/local-worker/publication/tasks").json().get("tasks", [])

    def start_publication(self, task_id):
        return self.api("POST", f"/psc/local-worker/publication/tasks/{task_id}/start").json()

    def report_publication_environment(self, task_id, actual, username):
        return self.api("POST", f"/psc/local-worker/publication/tasks/{task_id}/environment", json={
            "actual_ip": actual.get("ip", ""),
            "actual_country_code": actual.get("country", ""),
            "actual_timezone": actual.get("timezone", ""),
            "actual_username": username,
        }).json()

    def download_publication_media(self, task_id, media_type, target):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.api(
            "GET", f"/psc/local-worker/publication/tasks/{task_id}/media/{media_type}",
        )
        target.write_bytes(response.content)
        return target

    def complete_publication(self, task_id, published_url, screenshot):
        with Path(screenshot).open("rb") as stream:
            return self.api(
                "POST", f"/psc/local-worker/publication/tasks/{task_id}/complete",
                data={"published_url": published_url},
                files={"screenshot": (Path(screenshot).name, stream, "image/png")},
            ).json()

    def fail_publication(self, task_id, error):
        return self.api(
            "POST", f"/psc/local-worker/publication/tasks/{task_id}/fail",
            json={"error": str(error)},
        ).json()

    def progress(self, task_id, progress, message):
        self.api("POST", f"/psc/local-worker/tasks/{task_id}/progress",
                 json={"progress": progress, "message": message})

    def heartbeat(self, task_id):
        self.api("POST", f"/psc/local-worker/tasks/{task_id}/heartbeat")

    def heartbeat_loop(self, task_id, stop_event):
        interval = max(15, min(120, int(self.config.get("heartbeat_seconds", 30))))
        while not stop_event.wait(interval):
            try:
                self.heartbeat(task_id)
            except Exception as exc:
                self.emit("log", message=f"任务 {task_id} 心跳失败：{exc}")

    def attachment(self, attachment_id, target):
        target = Path(target)
        partial = target.with_name(target.name + ".part")
        retry_statuses = {502, 503, 504}
        attempts = 5
        for attempt in range(1, attempts + 1):
            error = None
            try:
                response = self.api("GET", f"/psc/local-worker/attachments/{attachment_id}")
                partial.write_bytes(response.content)
                os.replace(partial, target)
                return target
            except (requests.ConnectionError, requests.Timeout) as exc:
                retryable = True
                error = exc
            except requests.HTTPError as exc:
                retryable = exc.response is not None and exc.response.status_code in retry_statuses
                error = exc
            if not retryable or attempt == attempts:
                partial.unlink(missing_ok=True)
                raise error
            delay = min(8, 2 ** (attempt - 1))
            self.emit(
                "log",
                message=(
                    f"附件 {attachment_id} 下载暂时失败（第 {attempt}/{attempts} 次）：{error}；"
                    f"{delay} 秒后重试"
                ),
            )
            time.sleep(delay)

    def download_via_douyin(self, url, target):
        cookie_store = self.config.get("douyin_cookie_store") or str(
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "LightLinkMediaWorker" / "secrets.json"
        )
        return download_video(
            url, target, cookie_store,
            (self.config.get("download_proxy") or "").strip(),
        )

    def download_selection_video(self, url, target):
        cookie_store = self.config.get("douyin_cookie_store") or str(
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "LightLinkMediaWorker" / "secrets.json"
        )
        return download_video(
            url, target, cookie_store,
            (self.config.get("download_proxy") or "").strip(),
            return_video_id=True,
        )

    def douyin_video_metadata(self, url):
        cookie_store = self.config.get("douyin_cookie_store") or str(
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "LightLinkMediaWorker" / "secrets.json"
        )
        return get_video_metadata(
            url, cookie_store, (self.config.get("download_proxy") or "").strip(),
        )

    def download_url(self, url, target_dir, index):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) source URLs are accepted")
        host = (parsed.hostname or "").lower()
        if host != "douyin.com" and not host.endswith(".douyin.com") and host != "v.iesdouyin.com":
            raise ValueError("当前本地下载器仅接受抖音链接")
        return self.download_via_douyin(url, target_dir / f"source-{index}.mp4")

    @staticmethod
    def _is_local_ollama(endpoint):
        return (urlparse(endpoint).hostname or "").lower() in {
            "127.0.0.1", "localhost", "::1",
        }

    def _ollama_executable(self):
        ai = self.config.get("local_ai", {})
        configured = (ai.get("ollama_command") or "").strip()
        candidates = [
            configured,
            r"D:\odooAiwoker\AI\ollama\bin\ollama.exe",
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
            str(Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe"),
            shutil.which("ollama") or "",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return Path(candidate).resolve()
        return None

    @staticmethod
    def _ollama_ready(endpoint):
        try:
            response = requests.get(endpoint + "/api/tags", timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def _start_local_ollama(self, endpoint):
        if not self._is_local_ollama(endpoint):
            raise RuntimeError("Ollama 服务连接失败，请检查配置的地址和网络")
        with self._ollama_start_lock:
            if self._ollama_ready(endpoint):
                return
            executable = self._ollama_executable()
            if not executable:
                raise RuntimeError(
                    "需要翻译字幕，但未找到本机 Ollama。请在“连接与配置 → 本地AI”中"
                    "选择 Ollama 程序，或改用已经按目标语种生成的视频脚本"
                )
            environment = os.environ.copy()
            configured_models = (
                self.config.get("local_ai", {}).get("ollama_models") or ""
            ).strip()
            portable_models = executable.parent.parent / "models"
            if configured_models:
                environment["OLLAMA_MODELS"] = configured_models
            elif portable_models.is_dir():
                environment["OLLAMA_MODELS"] = str(portable_models)
            creation_flags = 0
            if os.name == "nt":
                creation_flags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            process = subprocess.Popen(
                [str(executable), "serve"],
                cwd=str(executable.parent),
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if self._ollama_ready(endpoint):
                    self.emit("log", message="本机 Ollama 已自动启动")
                    return
                if process.poll() is not None:
                    break
                time.sleep(0.5)
        raise RuntimeError("已尝试自动启动 Ollama，但服务仍不可用，请检查本机 Ollama 安装")

    def translate(self, text, language):
        if not text.strip():
            return text
        ai = self.config.get("local_ai", {})
        endpoint = ai.get("ollama_url", "").rstrip("/")
        model = ai.get("translation_model")
        if not endpoint or not model:
            return text
        payload = {
                "model": model, "stream": False,
                "prompt": f"Translate the following subtitle into {language}. Return only the translation:\n{text}",
            }
        try:
            response = requests.post(endpoint + "/api/generate", json=payload, timeout=300)
        except requests.ConnectionError:
            self._start_local_ollama(endpoint)
            try:
                response = requests.post(endpoint + "/api/generate", json=payload, timeout=300)
            except requests.ConnectionError as exc:
                raise RuntimeError("Ollama 已启动，但翻译服务仍无法连接") from exc
        if response.status_code == 404:
            try:
                detail = response.json().get("error", "")
            except (TypeError, ValueError):
                detail = ""
            if "model" in str(detail).lower():
                raise RuntimeError(
                    "本机 Ollama 中没有翻译模型 %s，请先安装该模型" % model
                )
        response.raise_for_status()
        return response.json().get("response", text).strip()

    @staticmethod
    def _srt_time(seconds):
        milliseconds = max(0, int(round(float(seconds) * 1000)))
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    @staticmethod
    def _ass_time(value):
        match = re.fullmatch(r"(\d+):(\d+):(\d+)[,.](\d+)", value.strip())
        if not match:
            raise ValueError("无法识别字幕时间：%s" % value)
        hours, minutes, seconds, fraction = match.groups()
        centiseconds = int((fraction + "00")[:2])
        return "%d:%02d:%02d.%02d" % (
            int(hours), int(minutes), int(seconds), centiseconds,
        )

    @classmethod
    def srt_to_region_ass(cls, srt, output, width, height, region):
        """Create an ASS subtitle track constrained to the cleaned subtitle area."""
        x, y, region_width, region_height = cls.subtitle_region(region)
        width, height = int(width), int(height)
        font_size = max(28, min(64, int(round(height * 0.032))))
        outline = max(2, int(round(font_size * 0.055)))
        margin_l = max(0, int(round(width * (x + 0.02))))
        margin_r = max(0, int(round(width * (1 - x - region_width + 0.02))))
        baseline = min(0.98, y + region_height * 0.72)
        margin_v = max(0, int(round(height * (1 - baseline))))
        events = []
        content = Path(srt).read_text(encoding="utf-8-sig").strip()
        for block in re.split(r"\r?\n\s*\r?\n", content):
            lines = block.splitlines()
            time_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
            if time_index is None:
                continue
            start, end = [item.strip() for item in lines[time_index].split("-->", 1)]
            text = r"\N".join(line.strip() for line in lines[time_index + 1:] if line.strip())
            text = text.replace("{", "（").replace("}", "）")
            if text:
                events.append(
                    "Dialogue: 0,%s,%s,Default,,0,0,0,,%s" %
                    (cls._ass_time(start), cls._ass_time(end), text)
                )
        if not events:
            raise RuntimeError("没有可覆盖到字幕清理区域的有效译文字幕")
        ass = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
{events}
""".format(
            width=width, height=height, font_size=font_size, outline=outline,
            margin_l=margin_l, margin_r=margin_r, margin_v=margin_v,
            events="\n".join(events),
        )
        output = Path(output)
        output.write_text(ass, encoding="utf-8-sig")
        return output

    def _translate_srt(self, text, language):
        translated = self.translate(
            "Translate only the subtitle text in this SRT into %s. Preserve every index, "
            "timestamp and blank line exactly:\n%s" % (language, text), language,
        )
        if translated.count("-->") != text.count("-->"):
            raise RuntimeError("字幕翻译结果破坏了时间轴，请调整本地翻译模型后重试")
        return translated

    @staticmethod
    def selected_content_text(task):
        source = task.get("content_source")
        choices = {
            "original_translation": task.get("original_translation") or "",
            "odoo_translation": task.get("odoo_translation") or "",
            "custom_translation": task.get("custom_translation") or "",
        }
        if source in choices:
            text = choices[source].strip()
            if not text:
                labels = {
                    "original_translation": "原视频目标语译文",
                    "odoo_translation": "Odoo文案目标语译文",
                    "custom_translation": "自写文案目标语译文",
                }
                raise ValueError("选定的文案来源“%s”为空，请先编辑内容" % labels[source])
            return text
        raise ValueError("请选择最终使用的目标语言译文")

    @classmethod
    def prepare_edit_workflow(cls, task, clip_count):
        """Apply the supported single-video or multi-video workflow."""
        if clip_count < 1:
            raise ValueError("请先选择至少一个视频素材")
        prepared = dict(task)
        prepared.update({
            "edit_mode": "sequence",
            "subtitle_mode": "script",
            "audio_mode": "mute",
            "target_language": prepared.get("target_language") or "English",
        })
        source = prepared.get("content_source")
        if clip_count > 1 and source == "original_translation":
            raise ValueError("多条视频模式不能使用原视频译文，请选择 Odoo 文案或自写文案译文")
        cls.selected_content_text(prepared)
        if (prepared.get("tts_provider") or "none") == "none":
            raise ValueError("英文合成需要先选择配音服务和音色")
        prepared["translate_subtitles"] = False
        prepared["workflow_mode"] = (
            "single_voice_translation" if clip_count == 1 else "multi_sequence_script"
        )
        return prepared

    def make_srt(self, task, job_dir, source_video=None):
        subtitle_mode = task.get("subtitle_mode")
        if subtitle_mode == "none":
            return None
        if subtitle_mode == "transcribe":
            if not source_video:
                raise ValueError("语音识别需要至少一个源视频")
            recognized = job_dir / "recognized.srt"
            result = transcribe(
                self.config.get("local_ai", {}), source_video, recognized,
                task.get("source_language") or "Chinese",
            )
            if result:
                text = recognized.read_text(encoding="utf-8-sig")
                if task.get("translate_subtitles", True):
                    text = self._translate_srt(text, task["target_language"])
                output = job_dir / "subtitle.srt"
                output.write_text(text, encoding="utf-8")
                return output
            if not (task.get("video_script") or task.get("prompt") or task.get("keywords")):
                self.emit("log", message="未安装 faster-whisper 且没有项目文本，本次成片不添加字幕")
                return None
            self.emit("log", message="未安装 faster-whisper，已自动改用项目文本生成字幕")

        text = self.selected_content_text(task)
        translate_subtitles = task.get("translate_subtitles")
        if task.get("content_source") in (
            "original_translation", "odoo_translation", "custom_translation",
        ):
            translate_subtitles = False
        if translate_subtitles is None:
            translate_subtitles = False
        translated = self.translate(text, task["target_language"]) if translate_subtitles else text
        duration = max(3, int(task.get("duration_seconds") or 15))
        srt = job_dir / "subtitle.srt"
        srt.write_text(
            "1\n00:00:00,000 --> %s\n%s\n" % (self._srt_time(duration), translated),
            encoding="utf-8",
        )
        return srt

    @staticmethod
    def subtitle_text(srt):
        if not srt:
            return ""
        lines = []
        for line in Path(srt).read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if value and "-->" not in value and not value.isdigit():
                lines.append(value)
        return " ".join(lines)

    def make_voiceover(self, task, srt, job_dir):
        provider = task.get("tts_provider") or "none"
        if provider == "none" or not srt:
            return None
        text = self.subtitle_text(srt)
        if not text:
            return None
        output = Path(job_dir) / "voiceover.wav"
        speech_config = dict(self.config.get("speech", {}))
        if provider == "volcengine" and task.get("tts_model_id"):
            speech_config["volc_resource_id"] = task["tts_model_id"]
        elif provider == "sherpa" and task.get("tts_model_id"):
            speech_config["sherpa_model"] = task["tts_model_id"]
        return synthesize(
            speech_config, provider, text, output,
            task.get("tts_voice") or "", task.get("tts_speed") or 1.0,
            task.get("tts_volume") or 1.0,
        )

    def sync_voiceover_subtitles(self, srt, voiceover, max_duration=None):
        """Split project text into readable cues timed to the generated narration."""
        text = re.sub(r"\s+", " ", self.subtitle_text(srt)).strip()
        duration = self.probe_duration(voiceover)
        if max_duration:
            duration = min(duration, float(max_duration))
        if not text or duration <= 0:
            return srt

        # Latin subtitles remain readable at about 7 words / 42 characters per cue.
        # CJK text has no spaces, so use a shorter character width.
        contains_cjk = bool(re.search(r"[\u3400-\u9fff]", text))
        width = 18 if contains_cjk and " " not in text else 42
        segments = re.split(r"(?<=[.!?。！？])\s+|\s*[•·]\s*", text)
        chunks = []
        for segment in segments:
            if segment.strip():
                chunks.extend(textwrap.wrap(
                    segment.strip(),
                    width=width,
                    break_long_words=contains_cjk,
                    break_on_hyphens=False,
                ))
        chunks = chunks or [text]
        weights = [max(1, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
        total_weight = sum(weights)
        elapsed_weight = 0
        cues = []
        for index, (chunk, weight) in enumerate(zip(chunks, weights), 1):
            start = duration * elapsed_weight / total_weight
            elapsed_weight += weight
            end = duration * elapsed_weight / total_weight
            cues.append(
                f"{index}\n{self._srt_time(start)} --> {self._srt_time(end)}\n{chunk}\n"
            )
        Path(srt).write_text("\n".join(cues), encoding="utf-8")
        return srt

    def arrange_clips(self, task, clips, job_dir):
        clips = list(clips)
        mode = task.get("edit_mode") or "sequence"
        if mode == "reverse":
            return list(reversed(clips))
        if mode == "random":
            random.Random(str(task.get("id") or "local")).shuffle(clips)
            return clips
        if mode != "ai":
            return clips
        command = (self.config.get("local_ai", {}).get("ai_edit_command") or "").strip()
        executable = Path(command).expanduser() if command else None
        if not executable or not executable.is_file():
            raise RuntimeError("选择了 AI 剪辑，但尚未配置本地 AI 剪辑程序")
        manifest = job_dir / "edit-input.json"
        plan = job_dir / "edit-plan.json"
        manifest.write_text(json.dumps({
            "clips": [
                {
                    "path": str(item.get("path") or ""),
                    "trim_start": float(item.get("trim_start") or 0),
                    "trim_end": float(item.get("trim_end") or 0),
                } if isinstance(item, dict) else {"path": str(item)}
                for item in clips
            ],
            "prompt": task.get("prompt") or "",
            "target_language": task.get("target_language") or "",
            "duration_seconds": int(task.get("duration_seconds") or 15),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        subprocess.run([str(executable), str(manifest), str(plan)], check=True)
        if not plan.is_file():
            raise RuntimeError("本地 AI 剪辑程序没有生成 edit-plan.json")
        indexes = json.loads(plan.read_text(encoding="utf-8"))
        if isinstance(indexes, dict):
            indexes = indexes.get("order")
        if not isinstance(indexes, list) or sorted(indexes) != list(range(len(clips))):
            raise RuntimeError("AI 剪辑计划中的 order 必须包含每个片段索引且不能重复")
        return [clips[index] for index in indexes]

    def image(self, task, job_dir):
        source = job_dir / "reference.jpg"
        if task.get("source_image_id"):
            self.attachment(task["source_image_id"], source)
        else:
            Image.new("RGB", (1080, 1350), "white").save(source)
        ratio = task.get("aspect_ratio", "1:1")
        size = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}.get(ratio, (1080, 1080))
        canvas = ImageOps.fit(Image.open(source).convert("RGB"), size, method=Image.Resampling.LANCZOS)
        title = self.translate(task.get("prompt") or task.get("keywords") or "", task["target_language"])
        if title:
            draw = ImageDraw.Draw(canvas, "RGBA")
            font = ImageFont.truetype(self.config.get("font_file", "C:/Windows/Fonts/msyh.ttc"), 54)
            draw.rectangle((0, size[1] - 250, size[0], size[1]), fill=(0, 0, 0, 150))
            draw.multiline_text((60, size[1] - 210), title[:140], font=font, fill="white", spacing=12)
        output = job_dir / "output.jpg"
        canvas.save(output, quality=92)
        return output, None

    def stitch_processed_clips(self, task, clips, job_dir):
        """Normalize and concatenate already-produced clips without reprocessing them."""
        if not clips:
            raise ValueError("没有可拼接的已处理片段")
        job_dir = Path(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        ratio = task.get("aspect_ratio", "9:16")
        width, height = {
            "9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080),
        }.get(ratio, (1080, 1920))
        ready_parts = []
        timeline = []
        cursor = 0.0
        for index, item in enumerate(clips, 1):
            spec = item if isinstance(item, dict) else {"path": item}
            source = Path(spec.get("path") or "")
            if not source.is_file():
                raise FileNotFoundError("第 %s 条已处理片段不存在：%s" % (index, source))
            duration = self.probe_duration(source)
            if duration <= 0:
                raise RuntimeError("无法读取第 %s 条已处理片段的时长" % index)
            ready = job_dir / ("ready-%02d.mp4" % index)
            result = subprocess.run([
                self.ffmpeg(), "-y", "-i", str(source),
                "-vf", (
                    "scale=%s:%s:force_original_aspect_ratio=decrease," % (width, height)
                    + "pad=%s:%s:(ow-iw)/2:(oh-ih)/2:black," % (width, height)
                    + "setsar=1,fps=30,format=yuv420p"
                ),
                "-af", "aresample=48000:async=1:first_pts=0,apad",
                "-t", "%.3f" % duration,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(ready),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode or not ready.is_file():
                raise RuntimeError("第 %s 条已处理片段标准化失败：%s" % (index, result.stderr[-700:]))
            ready_parts.append(ready)
            timeline.append({
                "record_id": spec.get("record_id"),
                "clip_name": spec.get("clip_name") or source.stem,
                "clip_type": spec.get("clip_type") or "unknown",
                "processed_kind": spec.get("processed_kind") or "已处理片段",
                "start": round(cursor, 3), "end": round(cursor + duration, 3),
            })
            cursor += duration
        concat = job_dir / "processed-concat.txt"
        concat.write_text("".join(
            "file '%s'\n" % str(path.resolve()).replace(chr(39), chr(39) * 2)
            for path in ready_parts
        ), encoding="utf-8")
        output = job_dir / "output.mp4"
        result = subprocess.run([
            self.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", "-movflags", "+faststart", str(output),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode or not output.is_file():
            raise RuntimeError("最终片段拼接失败：%s" % result.stderr[-700:])
        (job_dir / "clip-timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        return output, None

    def compose_video(self, task, clips, job_dir):
        if not clips:
            raise ValueError("任务没有视频URL或视频素材")
        job_dir = Path(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        clip_specs = [item if isinstance(item, dict) else {"path": item} for item in clips]
        clip_specs = self.arrange_clips(task, clip_specs, job_dir)
        clip_specs = self.prepare_subtitle_cleanup(task, clip_specs, job_dir)
        concat = job_dir / "concat.txt"
        concat_lines = []
        for item in clip_specs:
            path = str(Path(item["path"]).resolve()).replace(chr(39), chr(39) * 2)
            concat_lines.append(f"file '{path}'\n")
            if float(item.get("trim_start") or 0) > 0:
                concat_lines.append(f"inpoint {float(item['trim_start']):.3f}\n")
            if float(item.get("trim_end") or 0) > 0:
                concat_lines.append(f"outpoint {float(item['trim_end']):.3f}\n")
        concat.write_text("".join(concat_lines), encoding="utf-8")
        output = job_dir / "output.mp4"
        duration = max(3, int(task.get("duration_seconds") or 15))
        ratio = task.get("aspect_ratio", "9:16")
        width, height = {
            "9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080),
        }.get(ratio, (1080, 1920))
        if task.get("workflow_mode") in ("single_voice_translation", "multi_sequence_script"):
            source_duration = 0.0
            for item in clip_specs:
                clip_duration = self.probe_duration(item["path"])
                start = max(0.0, float(item.get("trim_start") or 0))
                end = float(item.get("trim_end") or 0)
                source_duration += max(0.0, (end if end > 0 else clip_duration) - start)
            if source_duration > 0:
                duration = source_duration

        # The concat demuxer's inpoint/outpoint keeps source MP4 timestamps. With
        # multiple trimmed clips that shifts burned subtitles and can corrupt the
        # first frames at clip boundaries. Normalize each silent segment first so
        # every clip starts at PTS 0 and has identical video parameters.
        normalized_video = None
        normalized_artifacts = []
        if len(clip_specs) > 1 and task.get("audio_mode") == "mute":
            normalized = []
            for index, item in enumerate(clip_specs, 1):
                clip_duration = self.probe_duration(item["path"])
                start = max(0.0, float(item.get("trim_start") or 0))
                requested_end = float(item.get("trim_end") or 0)
                end = min(requested_end, clip_duration) if requested_end > 0 else clip_duration
                if end <= start:
                    raise ValueError("第 %s 条视频的出点必须大于入点" % index)
                segment = job_dir / ("normalized-%02d.mp4" % index)
                video_filter = (
                    "trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS," % (start, end)
                    + "scale=%s:%s:force_original_aspect_ratio=decrease," % (width, height)
                    + "pad=%s:%s:(ow-iw)/2:(oh-ih)/2:black," % (width, height)
                    + "setsar=1,fps=30,format=yuv420p"
                )
                subprocess.run([
                    self.ffmpeg(), "-y", "-i", str(item["path"]), "-vf", video_filter,
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-movflags", "+faststart", str(segment),
                ], check=True, capture_output=True)
                normalized.append(segment)
                normalized_artifacts.append(segment)
            normalized_list = job_dir / "normalized-concat.txt"
            normalized_list.write_text("".join(
                "file '%s'\n" % str(path.resolve()).replace(chr(39), chr(39) * 2)
                for path in normalized
            ), encoding="utf-8")
            normalized_video = job_dir / "normalized-source.mp4"
            normalized_artifacts.extend((normalized_list, normalized_video))
            subprocess.run([
                self.ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                "-i", str(normalized_list), "-c", "copy", str(normalized_video),
            ], check=True, capture_output=True)
        speech_source = clip_specs[0]["path"]
        if task.get("subtitle_mode") == "transcribe" and asr_available(self.config.get("local_ai", {})):
            speech_source = job_dir / "speech-source.wav"
            subprocess.run([
                self.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-t", str(duration), "-vn", "-ac", "1", "-ar", "16000", str(speech_source),
            ], check=True, capture_output=True)
        srt = self.make_srt(task, job_dir, speech_source)
        voiceover = self.make_voiceover(task, srt, job_dir)
        if srt and voiceover:
            preserve_source_duration = task.get("workflow_mode") in (
                "single_voice_translation", "multi_sequence_script",
            )
            if not preserve_source_duration:
                duration = max(duration, self.probe_duration(voiceover))
            srt = self.sync_voiceover_subtitles(
                srt, voiceover, duration if preserve_source_duration else None,
            )
        filters = [] if normalized_video else [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        ]
        if task.get("transition") == "fade":
            filters.extend(["fade=t=in:st=0:d=0.35", f"fade=t=out:st={max(0, duration - 0.35)}:d=0.35"])
        if srt:
            overlay_in_cleanup_region = task.get("overlay_translation_in_cleanup_region", True)
            subtitle_source = srt
            if overlay_in_cleanup_region:
                subtitle_region = task.get("subtitle_region") or "5,72,90,22"
                if len(clip_specs) == 1 and clip_specs[0].get("subtitle_cleanup_policy") == "clean":
                    subtitle_region = clip_specs[0].get("subtitle_region") or subtitle_region
                subtitle_source = self.srt_to_region_ass(
                    srt, job_dir / "subtitle-overlay.ass", width, height, subtitle_region,
                )
            subtitle_path = str(subtitle_source).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            if overlay_in_cleanup_region:
                filters.append(f"subtitles='{subtitle_path}'")
            else:
                filters.append(
                    f"subtitles='{subtitle_path}':"
                    "force_style='FontName=Arial,FontSize=10,Outline=1.5,Shadow=0,"
                    "Alignment=8,MarginV=55'"
                )
        vf = ",".join(filters) or "null"
        command = [self.ffmpeg(), "-y"]
        if normalized_video:
            command += ["-i", str(normalized_video)]
        else:
            command += ["-f", "concat", "-safe", "0", "-i", str(concat)]
        if voiceover:
            command += ["-i", str(voiceover)]
        music = Path(task.get("background_music") or "").expanduser()
        if music.is_file():
            command += ["-stream_loop", "-1", "-i", str(music)]
        command += ["-t", str(duration), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                    "-movflags", "+faststart"]
        if voiceover and music.is_file():
            command += [
                "-filter_complex", f"[1:a]volume={float(task.get('tts_volume') or 1)}[v];"
                f"[2:a]volume={float(task.get('music_volume') or 0.2)}[m];[v][m]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]", "-c:a", "aac",
            ]
        elif voiceover:
            command += ["-map", "0:v", "-map", "1:a", "-c:a", "aac"]
        elif music.is_file() and task.get("audio_mode") != "mute":
            command += [
                "-filter_complex", f"[0:a]volume=0.65[o];[1:a]volume={float(task.get('music_volume') or 0.2)}[m];"
                "[o][m]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]", "-c:a", "aac",
            ]
        elif music.is_file():
            command += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
        else:
            command += ["-an"] if task.get("audio_mode") == "mute" else ["-c:a", "aac"]
        command.append(str(output))
        subprocess.run(command, check=True)
        output_duration = float(duration)
        raw_durations = []
        for item in clip_specs:
            start = max(0.0, float(item.get("trim_start") or 0))
            requested_end = float(item.get("trim_end") or 0)
            known_duration = float(item.get("duration") or 0)
            raw_durations.append(max(
                0.001,
                (requested_end - start) if requested_end > start
                else (known_duration - start) if known_duration > start else 1.0,
            ))
        duration_scale = output_duration / sum(raw_durations)
        cursor = 0.0
        timeline = []
        for index, item in enumerate(clip_specs):
            segment_duration = raw_durations[index] * duration_scale
            segment_end = min(output_duration, cursor + segment_duration)
            if index == len(clip_specs) - 1:
                segment_end = output_duration
            timeline.append({
                "record_id": item.get("record_id"),
                "clip_name": item.get("clip_name") or "片段 %s" % (index + 1),
                "clip_type": item.get("clip_type") or "unknown",
                "start": round(cursor, 3), "end": round(segment_end, 3),
            })
            cursor = segment_end
        (job_dir / "clip-timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        for artifact in normalized_artifacts:
            artifact.unlink(missing_ok=True)
        return output, srt

    def video(self, task, job_dir):
        clips = []
        for index, url in enumerate(task.get("source_urls") or [], 1):
            clips.append(self.download_url(url, job_dir, index))
        for index, item in enumerate(task.get("source_media") or [], len(clips) + 1):
            suffix = Path(item.get("name") or "clip.mp4").suffix or ".mp4"
            target = job_dir / f"asset-{index}{suffix}"
            self.attachment(item["id"], target)
            clips.append(target)
        return self.compose_video(task, clips, job_dir)

    def complete(self, task, output, subtitle, manifest=None):
        with output.open("rb") as stream:
            files = {"file": (output.name, stream, mimetypes.guess_type(output.name)[0] or "application/octet-stream")}
            subtitle_stream = subtitle.open("rb") if subtitle else None
            try:
                if subtitle_stream:
                    files["subtitle"] = (subtitle.name, subtitle_stream, "application/x-subrip")
                self.api(
                    "POST", f"/psc/local-worker/tasks/{task['id']}/complete",
                    files=files,
                    data={"manifest": json.dumps(manifest or {}, ensure_ascii=False)},
                )
            finally:
                if subtitle_stream:
                    subtitle_stream.close()

    def prepare_douyin_selection(self, task):
        if not task.get("source_image_id"):
            raise ValueError("抖音图片选片任务缺少产品参考图")
        job_dir = self.root / str(task["id"])
        job_dir.mkdir(parents=True, exist_ok=True)
        image_path = job_dir / "douyin-search-reference.jpg"
        self.attachment(task["source_image_id"], image_path)
        with Image.open(image_path) as source:
            source.convert("RGB").save(image_path, format="JPEG", quality=95)
        bridge = MumuBridge(
            self.config.get("mumu_adb", ""), self.config.get("mumu_serial", ""),
            self.config.get("mumu_player", ""),
            selector_port=self.config.get("selector_port", 0),
            selector_token=self.config.get("selector_token", ""),
        )
        remote_path = bridge.prepare_image_search(image_path, task["id"])
        self.api("POST", f"/psc/local-worker/tasks/{task['id']}/selection-ready")
        self.emit(
            "selection_pending",
            task=task,
            output=f"已自动输入参考图，等待选择视频（{remote_path}）",
        )
        return remote_path

    def complete_douyin_selection(self, task_id, urls):
        return self.api(
            "POST", f"/psc/local-worker/tasks/{task_id}/selection-complete",
            json={"urls": urls},
        ).json()

    def fail_task(self, task, error):
        try:
            self.api("POST", f"/psc/local-worker/tasks/{task['id']}/fail", json={"error": str(error)})
        except Exception as report_error:
            self.emit("log", message=f"任务 {task['id']} 失败状态回传失败：{report_error}")
        self.emit("task_failed", task=task, error=str(error))

    def process(self, task):
        job_dir = self.root / str(task["id"])
        if job_dir.exists():
            shutil.rmtree(job_dir)
        job_dir.mkdir(parents=True)
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self.heartbeat_loop, args=(task["id"], heartbeat_stop), daemon=True,
        )
        heartbeat_thread.start()
        try:
            self.emit("task_started", task=task)
            self.progress(task["id"], 5, "准备素材")
            output, subtitle = self.image(task, job_dir) if task["type"] == "image" else self.video(task, job_dir)
            self.progress(task["id"], 90, "上传成品")
            self.complete(task, output, subtitle)
            self.emit("task_done", task=task, output=str(output))
        except Exception as exc:
            self.fail_task(task, exc)
            raise
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
