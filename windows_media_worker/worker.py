import mimetypes
import os
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from douyin_adapter import download_video
from mumu_adapter import MumuBridge

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

class Worker:
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
        response = self.api("GET", f"/psc/local-worker/attachments/{attachment_id}")
        target.write_bytes(response.content)

    def download_via_douyin(self, url, target):
        cookie_store = self.config.get("douyin_cookie_store") or str(
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "LightLinkMediaWorker" / "secrets.json"
        )
        return download_video(
            url, target, cookie_store,
            (self.config.get("download_proxy") or "").strip(),
        )

    def download_url(self, url, target_dir, index):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) source URLs are accepted")
        host = (parsed.hostname or "").lower()
        if host != "douyin.com" and not host.endswith(".douyin.com") and host != "v.iesdouyin.com":
            raise ValueError("当前本地下载器仅接受抖音链接")
        return self.download_via_douyin(url, target_dir / f"source-{index}.mp4")

    def translate(self, text, language):
        if not text.strip():
            return text
        ai = self.config.get("local_ai", {})
        endpoint = ai.get("ollama_url", "").rstrip("/")
        model = ai.get("translation_model")
        if not endpoint or not model:
            return text
        try:
            response = requests.post(endpoint + "/api/generate", json={
                "model": model, "stream": False,
                "prompt": f"Translate the following subtitle into {language}. Return only the translation:\n{text}",
            }, timeout=300)
        except requests.ConnectionError as exc:
            raise RuntimeError(
                "需要翻译字幕，但本机 Ollama 未启动；请安装并启动 Ollama，"
                "或改用已经按目标语种生成的视频脚本"
            ) from exc
        response.raise_for_status()
        return response.json().get("response", text).strip()

    def make_srt(self, task, job_dir):
        script = (task.get("video_script") or "").strip()
        source_mode = task.get("source_mode") or "auto"
        if script and source_mode in ("auto", "project_script"):
            translated = script
        else:
            text = script or task.get("prompt") or task.get("keywords") or ""
            translated = self.translate(text, task["target_language"])
        duration = max(3, int(task.get("duration_seconds") or 15))
        srt = job_dir / "subtitle.srt"
        srt.write_text(f"1\n00:00:00,000 --> 00:00:{duration:02d},000\n{translated}\n", encoding="utf-8")
        return srt

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

    def video(self, task, job_dir):
        clips = []
        for index, url in enumerate(task.get("source_urls") or [], 1):
            clips.append(self.download_url(url, job_dir, index))
        for index, item in enumerate(task.get("source_media") or [], len(clips) + 1):
            suffix = Path(item.get("name") or "clip.mp4").suffix or ".mp4"
            target = job_dir / f"asset-{index}{suffix}"
            self.attachment(item["id"], target)
            clips.append(target)
        if not clips:
            raise ValueError("任务没有视频URL或视频素材")
        srt = self.make_srt(task, job_dir)
        concat = job_dir / "concat.txt"
        concat.write_text("".join(f"file '{str(path).replace(chr(39), chr(39)*2)}'\n" for path in clips), encoding="utf-8")
        output = job_dir / "output.mp4"
        duration = max(3, int(task.get("duration_seconds") or 15))
        ratio = task.get("aspect_ratio", "9:16")
        width, height = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}.get(ratio, (1080, 1920))
        subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
              f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
              f"subtitles='{subtitle_path}'")
        command = [self.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                   "-t", str(duration), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                   "-c:a", "aac", "-movflags", "+faststart", str(output)]
        subprocess.run(command, check=True)
        return output, srt

    def complete(self, task, output, subtitle):
        with output.open("rb") as stream:
            files = {"file": (output.name, stream, mimetypes.guess_type(output.name)[0] or "application/octet-stream")}
            subtitle_stream = subtitle.open("rb") if subtitle else None
            try:
                if subtitle_stream:
                    files["subtitle"] = (subtitle.name, subtitle_stream, "application/x-subrip")
                self.api("POST", f"/psc/local-worker/tasks/{task['id']}/complete", files=files)
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
            self.config.get("mumu_adb", ""), self.config.get("mumu_serial", "127.0.0.1:7555"),
            self.config.get("mumu_player", ""),
        )
        remote_path = bridge.prepare_image_search(image_path, task["id"])
        self.api("POST", f"/psc/local-worker/tasks/{task['id']}/selection-ready")
        self.emit("selection_pending", task=task, output=remote_path)
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
