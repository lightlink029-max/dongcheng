import mimetypes
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
import textwrap
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

    @staticmethod
    def _srt_time(seconds):
        milliseconds = max(0, int(round(float(seconds) * 1000)))
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

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

    def compose_video(self, task, clips, job_dir):
        if not clips:
            raise ValueError("任务没有视频URL或视频素材")
        job_dir = Path(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        clip_specs = [item if isinstance(item, dict) else {"path": item} for item in clips]
        clip_specs = self.arrange_clips(task, clip_specs, job_dir)
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
            subtitle_path = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
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
