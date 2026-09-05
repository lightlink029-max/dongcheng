import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


class Worker:
    def __init__(self, config):
        self.config = config
        self.base = config["odoo_url"].rstrip("/")
        self.headers = {"Authorization": "Bearer " + config["worker_token"]}
        self.root = Path(config.get("work_dir", "jobs")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def api(self, method, path, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(method, self.base + path, headers=headers, timeout=300, **kwargs)
        response.raise_for_status()
        return response

    def claim(self):
        return self.api("POST", "/psc/local-worker/claim", json={
            "worker_id": self.config.get("worker_id", os.environ.get("COMPUTERNAME", "windows-worker"))
        }).json().get("task")

    def progress(self, task_id, progress, message):
        self.api("POST", f"/psc/local-worker/tasks/{task_id}/progress",
                 json={"progress": progress, "message": message})

    def attachment(self, attachment_id, target):
        response = self.api("GET", f"/psc/local-worker/attachments/{attachment_id}")
        target.write_bytes(response.content)

    def download_url(self, url, target_dir, index):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) source URLs are accepted")
        output = target_dir / f"source-{index}.%(ext)s"
        command = [self.config.get("yt_dlp", "yt-dlp"), "--no-playlist", "--restrict-filenames",
                   "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", str(output), url]
        subprocess.run(command, check=True)
        matches = sorted(target_dir.glob(f"source-{index}.*"))
        if not matches:
            raise RuntimeError("Downloader produced no file")
        return matches[0]

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
        if task.get("source_image_url"):
            source_id = int(task["source_image_url"].split("/web/content/")[1].split("?")[0])
            self.attachment(source_id, source)
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
        command = [self.config.get("ffmpeg", "ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
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
        try:
            self.progress(task["id"], 5, "准备素材")
            output, subtitle = self.image(task, job_dir) if task["type"] == "image" else self.video(task, job_dir)
            self.progress(task["id"], 90, "上传成品")
            self.complete(task, output, subtitle)
        except Exception as exc:
            self.api("POST", f"/psc/local-worker/tasks/{task['id']}/fail", json={"error": str(exc)})
            raise

    def run(self):
        delay = max(3, int(self.config.get("poll_seconds", 10)))
        while True:
            try:
                task = self.claim()
                if task:
                    self.process(task)
                else:
                    time.sleep(delay)
            except KeyboardInterrupt:
                return
            except Exception as exc:
                print(time.strftime("%Y-%m-%d %H:%M:%S"), exc, file=sys.stderr)
                time.sleep(delay)


if __name__ == "__main__":
    config_path = Path(sys.argv[1] if len(sys.argv) > 1 else "config.json")
    Worker(json.loads(config_path.read_text(encoding="utf-8"))).run()
