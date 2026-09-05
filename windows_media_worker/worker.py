import mimetypes
import os
import shutil
import subprocess
import threading
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


class DownloadLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if href.startswith(("/api/proxy?", "/api/fetch?")):
            self.links.append(href)


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

    def download_proxies(self):
        proxy = (self.config.get("download_proxy") or "").strip()
        return {"http": proxy, "https": proxy} if proxy else None

    def download_via_online_service(self, url, target):
        service = (self.config.get("online_downloader_url") or "https://paste2vid.com").rstrip("/")
        if urlparse(service).scheme != "https":
            raise ValueError("在线视频下载服务必须使用 https://")
        session = requests.Session()
        request_options = {"timeout": 60, "proxies": self.download_proxies()}
        home = session.get(service + "/", **request_options)
        home.raise_for_status()
        response = session.post(
            service + "/api/parse2?lang=zh",
            json={"url": url},
            headers={"Origin": service, "Referer": service + "/"},
            **request_options,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message") or "在线视频解析失败")
        parser = DownloadLinkParser()
        parser.feed((payload.get("data") or {}).get("html") or "")
        if not parser.links:
            raise RuntimeError("在线视频解析结果中没有下载地址")
        media = session.get(urljoin(service + "/", parser.links[0]), stream=True, **request_options)
        media.raise_for_status()
        content_type = (media.headers.get("Content-Type") or "").lower()
        if content_type and not any(value in content_type for value in ("video/", "octet-stream")):
            raise RuntimeError("在线视频下载服务返回的不是视频文件")
        with target.open("wb") as stream:
            for chunk in media.iter_content(1024 * 1024):
                if chunk:
                    stream.write(chunk)
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("在线视频下载服务返回了空文件")
        return target

    def download_via_ytdlp(self, url, target_dir, index):
        output = target_dir / f"source-{index}.%(ext)s"
        proxy = (self.config.get("download_proxy") or "").strip()
        options = {
            "noplaylist": True, "restrictfilenames": True,
            "format": "bv*+ba/b", "merge_output_format": "mp4",
            "outtmpl": str(output), "ffmpeg_location": self.ffmpeg(),
            "quiet": True, "no_warnings": True,
        }
        if proxy:
            options["proxy"] = proxy
        if YoutubeDL:
            with YoutubeDL(options) as downloader:
                downloader.download([url])
        else:
            command = [self.config.get("yt_dlp", "yt-dlp"), "--no-playlist", "--restrict-filenames",
                       "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", str(output)]
            if proxy:
                command.extend(["--proxy", proxy])
            subprocess.run(command + [url], check=True)
        matches = sorted(target_dir.glob(f"source-{index}.*"))
        if not matches:
            raise RuntimeError("Downloader produced no file")
        return matches[0]

    def download_url(self, url, target_dir, index):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) source URLs are accepted")
        online_target = target_dir / f"source-{index}.mp4"
        if self.config.get("online_downloader_enabled", True):
            try:
                return self.download_via_online_service(url, online_target)
            except Exception as exc:
                online_target.unlink(missing_ok=True)
                self.emit("log", message=f"免费网页下载失败，改用本地下载器：{exc}")
        return self.download_via_ytdlp(url, target_dir, index)

    def translate(self, text, language):
        if not text.strip():
            return text
        ai = self.config.get("local_ai", {})
        endpoint = ai.get("ollama_url", "").rstrip("/")
        model = ai.get("translation_model")
        if not endpoint or not model:
            return text
        response = requests.post(endpoint + "/api/generate", json={
            "model": model, "stream": False,
            "prompt": f"Translate the following subtitle into {language}. Return only the translation:\n{text}",
        }, timeout=300)
        response.raise_for_status()
        return response.json().get("response", text).strip()

    def make_srt(self, task, job_dir):
        text = task.get("video_script") or task.get("prompt") or task.get("keywords") or ""
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
            try:
                self.api("POST", f"/psc/local-worker/tasks/{task['id']}/fail", json={"error": str(exc)})
            except Exception as report_error:
                self.emit("log", message=f"任务 {task['id']} 失败状态回传失败：{report_error}")
            self.emit("task_failed", task=task, error=str(exc))
            raise
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
