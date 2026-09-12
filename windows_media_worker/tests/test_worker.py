import sys
import unittest
import requests
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import Worker, create_version_directory
from mumu_adapter import MumuBridge, discover_serial
from selection_store import SelectionStore, extract_douyin_urls, extract_video_id
from selector_bridge import SelectorBridge
import json
from urllib.request import Request, urlopen


class StopAfterFirstHeartbeat:
    def __init__(self):
        self.calls = 0

    def wait(self, _seconds):
        self.calls += 1
        return self.calls > 1


class VersionDirectoryTests(unittest.TestCase):
    def test_existing_render_directory_uses_next_available_version(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "mix-output-v1").mkdir()
            (root / "mix-output-v2").mkdir()
            version, target = create_version_directory(root, 1)

            self.assertEqual(version, 3)
            self.assertEqual(target, root / "mix-output-v3")
            self.assertTrue(target.is_dir())


class RecordingWorker(Worker):
    def __init__(self, config):
        super().__init__(config)
        self.heartbeats = []

    def heartbeat(self, task_id):
        self.heartbeats.append(task_id)


class DownloadWorker(Worker):
    def __init__(self, config):
        super().__init__(config)
        self.calls = []

    def download_via_douyin(self, _url, target):
        self.calls.append("douyin")
        target.write_bytes(b"video")
        return target


class NoTranslationWorker(Worker):
    def translate(self, _text, _language):
        raise AssertionError("已有目标语种脚本时不应调用翻译模型")


class WorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.work_dir = TemporaryDirectory()

    def tearDown(self):
        self.work_dir.cleanup()

    def config(self):
        return {
            "odoo_url": "https://example.invalid",
            "worker_token": "test-token",
            "worker_id": "media-test-01",
            "work_dir": self.work_dir.name,
            "heartbeat_seconds": 1,
        }

    def test_bitbrowser_sync_only_uploads_allowlisted_metadata(self):
        worker = Worker(self.config())
        response = mock.Mock()
        response.json.return_value = {"ok": True, "saved": 1}
        with mock.patch.object(worker, "api", return_value=response) as api:
            result = worker.sync_bitbrowser_environments([{
                "id": "browser-1", "seq": 1, "name": "TikTok US",
                "userName": "seller", "password": "must-not-upload",
                "cookie": "must-not-upload",
            }])
        payload = api.call_args.kwargs["json"]
        self.assertEqual(result["saved"], 1)
        self.assertEqual(payload["worker_id"], "media-test-01")
        self.assertNotIn("password", payload["environments"][0])
        self.assertNotIn("cookie", payload["environments"][0])

    def test_worker_identity_is_sent_with_every_request(self):
        worker = Worker(self.config())
        self.assertEqual(worker.headers["X-LightLink-Worker-ID"], "media-test-01")
        self.assertEqual(worker.headers["Authorization"], "Bearer test-token")

    def test_registration_environment_uploads_only_validation_result(self):
        worker = Worker(self.config())
        response = mock.Mock()
        response.json.return_value = {"ok": True}
        with mock.patch.object(worker, "api", return_value=response) as api:
            worker.report_registration_environment(7, {
                "ip": "203.0.113.7", "country": "US", "timezone": "America/New_York",
                "password": "must-not-upload", "cookie": "must-not-upload", "two_factor_secret": "must-not-upload",
            })
        payload = api.call_args.kwargs["json"]
        self.assertEqual(payload, {
            "actual_ip": "203.0.113.7", "actual_country_code": "US",
            "actual_timezone": "America/New_York",
        })

    def test_publication_environment_uploads_only_required_validation_data(self):
        worker = Worker(self.config())
        response = mock.Mock()
        response.json.return_value = {"ok": True}
        with mock.patch.object(worker, "api", return_value=response) as api:
            worker.report_publication_environment(8, {
                "ip": "203.0.113.7", "country": "US", "timezone": "America/New_York",
                "password": "must-not-upload", "cookie": "must-not-upload",
            }, "brand_account")
        payload = api.call_args.kwargs["json"]
        self.assertEqual(payload, {
            "actual_ip": "203.0.113.7", "actual_country_code": "US",
            "actual_timezone": "America/New_York", "actual_username": "brand_account",
        })

    def test_heartbeat_loop_renews_the_claim(self):
        worker = RecordingWorker(self.config())
        worker.heartbeat_loop(42, StopAfterFirstHeartbeat())
        self.assertEqual(worker.heartbeats, [42])

    def test_douyin_downloader_is_used(self):
        worker = DownloadWorker(self.config())
        target = worker.download_url("https://v.douyin.com/example/", Path(self.work_dir.name), 1)
        self.assertEqual(worker.calls, ["douyin"])
        self.assertEqual(target.read_bytes(), b"video")

    def test_attachment_retries_transient_gateway_failure(self):
        worker = Worker(self.config())
        failed = requests.Response()
        failed.status_code = 502
        failed.url = "https://example.invalid/psc/local-worker/attachments/2351"
        gateway_error = requests.HTTPError("502 Bad Gateway", response=failed)
        target = Path(self.work_dir.name) / "source.jpg"
        with mock.patch.object(
            worker,
            "api",
            side_effect=[gateway_error, SimpleNamespace(content=b"image")],
        ) as api, mock.patch("worker.time.sleep") as sleep:
            result = worker.attachment(2351, target)
        self.assertEqual(result, target)
        self.assertEqual(target.read_bytes(), b"image")
        self.assertFalse(Path(str(target) + ".part").exists())
        self.assertEqual(api.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_attachment_does_not_retry_not_found(self):
        worker = Worker(self.config())
        failed = requests.Response()
        failed.status_code = 404
        failed.url = "https://example.invalid/psc/local-worker/attachments/2351"
        not_found = requests.HTTPError("404 Not Found", response=failed)
        target = Path(self.work_dir.name) / "missing.jpg"
        with mock.patch.object(worker, "api", side_effect=not_found) as api, \
                mock.patch("worker.time.sleep") as sleep:
            with self.assertRaises(requests.HTTPError):
                worker.attachment(2351, target)
        api.assert_called_once()
        sleep.assert_not_called()

    def test_non_douyin_url_is_rejected(self):
        worker = DownloadWorker(self.config())
        with self.assertRaisesRegex(ValueError, "仅接受抖音链接"):
            worker.download_url("https://example.com/video", Path(self.work_dir.name), 1)
        self.assertEqual(worker.calls, [])

    def test_video_order_can_be_moved_and_is_used_when_rows_are_loaded(self):
        store = SelectionStore(Path(self.work_dir.name) / "selections.db")
        task_id = -1
        store.save_task({"id": task_id, "name": "排序测试"})
        store.add_text(task_id, "\n".join((
            "https://v.douyin.com/first/",
            "https://v.douyin.com/second/",
            "https://v.douyin.com/third/",
        )))
        rows = store.list(task_id)
        store.move(task_id, [rows[2]["id"]], -1)
        moved = store.list(task_id)
        self.assertEqual(
            [row["url"] for row in moved],
            [rows[0]["url"], rows[2]["url"], rows[1]["url"]],
        )
        self.assertEqual(
            [row["id"] for row in store.get_many([row["id"] for row in moved])],
            [row["id"] for row in moved],
        )
        selected = store.list_selected(task_id, [moved[0]["id"], moved[2]["id"]])
        self.assertEqual(
            [row["id"] for row in selected], [moved[0]["id"], moved[2]["id"]],
        )

    def test_target_language_video_script_skips_ollama(self):
        worker = NoTranslationWorker(self.config())
        task = {
            "content_source": "odoo_translation",
            "odoo_translation": "Ready-to-use English subtitle",
            "target_language": "English", "duration_seconds": 15,
        }
        srt = worker.make_srt(task, Path(self.work_dir.name))
        self.assertIn("Ready-to-use English subtitle", srt.read_text(encoding="utf-8"))

    def test_translate_auto_starts_local_ollama_and_retries(self):
        worker = Worker({
            **self.config(),
            "local_ai": {
                "ollama_url": "http://127.0.0.1:11434",
                "translation_model": "qwen3:8b",
            },
        })
        translated = mock.Mock(status_code=200)
        translated.json.return_value = {"response": "Hello"}
        translated.raise_for_status.return_value = None
        with mock.patch("worker.requests.post", side_effect=[requests.ConnectionError(), translated]), \
                mock.patch.object(worker, "_start_local_ollama") as start:
            self.assertEqual(worker.translate("你好", "English"), "Hello")
        start.assert_called_once_with("http://127.0.0.1:11434")

    def test_translate_does_not_start_local_program_for_remote_ollama(self):
        worker = Worker({
            **self.config(),
            "local_ai": {
                "ollama_url": "https://ollama.example.com",
                "translation_model": "qwen3:8b",
            },
        })
        with mock.patch("worker.requests.post", side_effect=requests.ConnectionError()), \
                mock.patch("worker.subprocess.Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "检查配置的地址和网络"):
                worker.translate("你好", "English")
        popen.assert_not_called()

    def test_operator_can_choose_each_editable_content_source(self):
        task = {
            "original_translation": "Original video translation",
            "odoo_translation": "Odoo translation",
            "custom_translation": "Custom translation",
        }
        for source, expected in (
            ("original_translation", "Original video translation"),
            ("odoo_translation", "Odoo translation"),
            ("custom_translation", "Custom translation"),
        ):
            task["content_source"] = source
            self.assertEqual(Worker.selected_content_text(task), expected)

    def test_single_video_workflow_uses_selected_copy_and_replaces_original_audio(self):
        prepared = Worker.prepare_edit_workflow({
            "content_source": "original_translation",
            "original_translation": "Translated original narration",
            "tts_provider": "sherpa",
            "target_language": "English",
        }, 1)
        self.assertEqual(prepared["workflow_mode"], "single_voice_translation")
        self.assertEqual(prepared["edit_mode"], "sequence")
        self.assertEqual(prepared["audio_mode"], "mute")
        self.assertFalse(prepared["translate_subtitles"])

    def test_multi_video_workflow_rejects_original_transcript(self):
        with self.assertRaisesRegex(ValueError, "多条视频模式"):
            Worker.prepare_edit_workflow({
                "content_source": "original_translation",
                "original_translation": "Should not be used",
                "tts_provider": "sherpa",
            }, 2)

    def test_multi_video_workflow_accepts_custom_copy(self):
        prepared = Worker.prepare_edit_workflow({
            "content_source": "custom_translation",
            "custom_translation": "Custom English copy",
            "tts_provider": "volcengine",
        }, 2)
        self.assertEqual(prepared["workflow_mode"], "multi_sequence_script")
        self.assertEqual(prepared["edit_mode"], "sequence")

    def test_voiceover_is_required_for_translation_workflows(self):
        with self.assertRaisesRegex(ValueError, "配音服务和音色"):
            Worker.prepare_edit_workflow({
                "content_source": "odoo_translation", "odoo_translation": "English copy",
            }, 2)

    def test_empty_selected_content_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "原视频目标语译文.*为空"):
            Worker.selected_content_text({
                "content_source": "original_translation",
                "original_translation": "",
            })

    def test_verified_translation_is_not_translated_twice(self):
        worker = NoTranslationWorker(self.config())
        task = {
            "content_source": "odoo_translation",
            "odoo_translation": "Human-approved English copy",
            "translate_subtitles": True,
            "target_language": "English", "duration_seconds": 15,
        }
        srt = worker.make_srt(task, Path(self.work_dir.name))
        self.assertIn("Human-approved English copy", srt.read_text(encoding="utf-8"))

    def test_subtitles_can_be_disabled(self):
        worker = NoTranslationWorker(self.config())
        task = {"subtitle_mode": "none", "target_language": "English"}
        self.assertIsNone(worker.make_srt(task, Path(self.work_dir.name)))

    def test_subtitle_region_accepts_percentages_and_rejects_overflow(self):
        self.assertEqual(Worker.subtitle_region("5,72,90,22"), (0.05, 0.72, 0.9, 0.22))
        self.assertEqual(Worker.subtitle_region(""), Worker.DEFAULT_SUBTITLE_REGION)
        with self.assertRaisesRegex(ValueError, "四个百分比"):
            Worker.subtitle_region("5,72,90")
        with self.assertRaisesRegex(ValueError, "字幕区域"):
            Worker.subtitle_region("5,90,90,20")

    def test_translated_subtitles_are_laid_out_inside_cleanup_region(self):
        folder = Path(self.work_dir.name)
        srt = folder / "subtitle.srt"
        ass = folder / "subtitle-overlay.ass"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:05,000\nA verified English translation.\n",
            encoding="utf-8",
        )
        Worker.srt_to_region_ass(srt, ass, 1080, 1920, "5,72,90,22")
        content = ass.read_text(encoding="utf-8-sig")
        self.assertIn("PlayResX: 1080", content)
        self.assertIn("PlayResY: 1920", content)
        self.assertIn(",2,76,76,233,1", content)
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:05.00", content)
        self.assertIn("A verified English translation.", content)

    def test_quick_subtitle_cleanup_writes_new_file_and_keeps_source(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name)
        source = folder / "source.mp4"
        output = folder / "cleaned.mp4"
        source.write_bytes(b"original")

        def create_output(command, **_kwargs):
            Path(command[-1]).write_bytes(b"cleaned")

        with mock.patch("worker.subprocess.run", side_effect=create_output) as run:
            worker.clean_hard_subtitles({
                "subtitle_cleanup_mode": "quick",
                "subtitle_cleanup_quality": "standard",
                "subtitle_quick_method": "blur",
                "subtitle_region": "5,72,90,22",
            }, source, output, preview_seconds=5)
        command = run.call_args.args[0]
        self.assertIn("boxblur", command[command.index("-filter_complex") + 1])
        self.assertEqual(command[command.index("-t") + 1], "5.0")
        self.assertEqual(source.read_bytes(), b"original")
        self.assertEqual(output.read_bytes(), b"cleaned")

    def test_vsr_cleanup_manifest_uses_sttn_and_manual_region(self):
        folder = Path(self.work_dir.name)
        adapter = folder / "vsr-adapter.exe"
        adapter.write_bytes(b"stub")
        config = self.config()
        config["local_ai"] = {"vsr_command": str(adapter)}
        worker = Worker(config)
        source, output = folder / "source.mp4", folder / "cleaned.mp4"
        source.write_bytes(b"original")

        def create_output(command, **_kwargs):
            Path(command[-1]).write_bytes(b"cleaned")

        with mock.patch("worker.subprocess.run", side_effect=create_output):
            worker.clean_hard_subtitles({
                "subtitle_cleanup_mode": "ai_manual",
                "subtitle_cleanup_engine": "sttn",
                "subtitle_cleanup_quality": "high",
                "subtitle_region": "4,70,92,24",
            }, source, output)
        manifest = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["engine"], "sttn")
        self.assertFalse(manifest["auto_detect"])
        self.assertEqual(manifest["region_percent"], [4.0, 70.0, 92.0, 24.0])
        self.assertEqual(manifest["quality"], "high")

    def test_cleanup_failure_falls_back_without_overwriting_source(self):
        config = self.config()
        worker = Worker(config)
        folder = Path(self.work_dir.name)
        source = folder / "source.mp4"
        source.write_bytes(b"original")
        events = []
        worker.event_callback = lambda event, data: events.append((event, data))
        result = worker.prepare_subtitle_cleanup({
            "remove_hard_subtitles": True,
            "subtitle_cleanup_mode": "ai_manual",
        }, [{"path": source}], folder)
        self.assertEqual(result[0]["path"], source)
        self.assertEqual(source.read_bytes(), b"original")
        self.assertTrue(any(event == "subtitle_cleanup_warning" for event, _data in events))
        report = json.loads((folder / "subtitle-cleanup-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report[0]["status"], "fallback")

    def test_cleanup_is_applied_only_to_marked_clips(self):
        worker = Worker(self.config())
        folder = Path(self.work_dir.name)
        first, second = folder / "first.mp4", folder / "second.mp4"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        cleaned = folder / "cleaned.mp4"
        cleaned.write_bytes(b"cleaned")
        with mock.patch.object(worker, "clean_hard_subtitles", return_value=cleaned) as clean:
            result = worker.prepare_subtitle_cleanup({
                "remove_hard_subtitles": False,
            }, [
                {"path": first, "subtitle_cleanup_policy": "clean"},
                {"path": second, "subtitle_cleanup_policy": "skip"},
            ], folder)
        clean.assert_called_once()
        self.assertEqual(result[0]["path"], cleaned)
        self.assertEqual(result[1]["path"], second)
        report = json.loads((folder / "subtitle-cleanup-report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["status"] for row in report], ["cleaned", "skipped"])

    def test_cleanup_reuses_matching_preprocessed_clip(self):
        worker = Worker(self.config())
        folder = Path(self.work_dir.name)
        source = folder / "source.mp4"
        prepared = folder / "prepared.mp4"
        source.write_bytes(b"original")
        prepared.write_bytes(b"cleaned")
        settings = {
            "subtitle_cleanup_policy": "clean",
            "subtitle_cleanup_mode": "quick",
            "subtitle_cleanup_quality": "standard",
            "subtitle_quick_method": "blur",
            "subtitle_region": "5,72,90,22",
        }
        settings["path"] = source
        settings["subtitle_cleaned_path"] = str(prepared)
        settings["subtitle_cleanup_signature"] = worker.subtitle_cleanup_signature(
            settings, source,
        )
        with mock.patch.object(worker, "clean_hard_subtitles") as clean:
            result = worker.prepare_subtitle_cleanup({}, [settings], folder)
        clean.assert_not_called()
        self.assertEqual(result[0]["path"], prepared)
        report = json.loads((folder / "subtitle-cleanup-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report[0]["status"], "reused")

    def test_srt_timestamp_supports_more_than_one_minute(self):
        worker = NoTranslationWorker(self.config())
        task = {
            "content_source": "odoo_translation", "odoo_translation": "Long video",
            "subtitle_mode": "script",
            "translate_subtitles": False, "target_language": "English",
            "duration_seconds": 75,
        }
        srt = worker.make_srt(task, Path(self.work_dir.name))
        self.assertIn("00:01:15,000", srt.read_text(encoding="utf-8"))

    def test_voiceover_subtitles_are_split_and_timed_to_audio(self):
        worker = Worker(self.config())
        folder = Path(self.work_dir.name)
        srt = folder / "subtitle.srt"
        voiceover = folder / "voiceover.wav"
        script = (
            "Warm indoor slippers for boys and girls. Soft fuzzy feel for cozy home wear. "
            "Non-slip outsole for indoor use. Cotton fabric upper and lining."
        )
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:15,000\n" + script + "\n",
            encoding="utf-8",
        )
        voiceover.write_bytes(b"audio")
        with mock.patch.object(worker, "probe_duration", return_value=12.5):
            result = worker.sync_voiceover_subtitles(srt, voiceover)
        content = result.read_text(encoding="utf-8")
        self.assertGreater(content.count("-->"), 1)
        self.assertIn("00:00:12,500", content)
        self.assertNotIn("\n" + script + "\n", content)

    def test_voiceover_uses_the_selected_volcengine_model(self):
        config = self.config()
        config["speech"] = {
            "volc_api_key": "secret", "volc_resource_id": "seed-tts-2.0",
        }
        worker = Worker(config)
        folder = Path(self.work_dir.name)
        srt = folder / "subtitle.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nVoice preview\n",
            encoding="utf-8",
        )
        expected = folder / "voiceover.mp3"
        with mock.patch("worker.synthesize", return_value=expected) as synthesize:
            result = worker.make_voiceover({
                "tts_provider": "volcengine", "tts_voice": "voice-id",
                "tts_model_id": "seed-tts-custom",
            }, srt, folder)
        self.assertEqual(result, expected)
        self.assertEqual(synthesize.call_args.args[0]["volc_resource_id"], "seed-tts-custom")

    def test_heygen_audio_is_padded_to_the_review_duration(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name)
        video = folder / "review.mp4"
        output = folder / "heygen-audio.mp3"
        video.write_bytes(b"video")

        def write_audio(command, **_kwargs):
            Path(command[-1]).write_bytes(b"audio")
            return SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(worker, "probe_duration", return_value=46.2), \
                mock.patch("worker.subprocess.run", side_effect=write_audio) as run:
            result = worker.prepare_heygen_audio(video, output)
        command = run.call_args.args[0]
        self.assertEqual(result, output)
        self.assertEqual(command[command.index("-t") + 1], "46.2")
        self.assertIn("apad", command)

    def test_heygen_lipsync_uses_assets_and_preserves_duration(self):
        config = self.config()
        config["heygen"] = {
            "api_key": "secret", "mode": "precision", "poll_seconds": 3,
        }
        worker = Worker(config)
        folder = Path(self.work_dir.name)
        video, audio, output = folder / "review.mp4", folder / "audio.mp3", folder / "result.mp4"
        video.write_bytes(b"video")
        audio.write_bytes(b"audio")

        created = mock.Mock(status_code=200, text="")
        created.json.return_value = {"data": {"lipsync_id": "lip-1"}}
        completed = mock.Mock(status_code=200, text="")
        completed.json.return_value = {
            "data": {"status": "completed", "video_url": "https://files.example/result.mp4"},
        }
        download = mock.Mock(status_code=200, text="")
        download.iter_content.return_value = [b"result-video"]

        with mock.patch.object(worker, "heygen_upload_asset", side_effect=["video-asset", "audio-asset"]), \
                mock.patch.object(worker, "probe_duration", return_value=46.2), \
                mock.patch("worker.requests.post", return_value=created) as post, \
                mock.patch("worker.requests.get", side_effect=[completed, download]):
            result = worker.heygen_lipsync(video, audio, output, title="Review V2")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(result, output)
        self.assertEqual(output.read_bytes(), b"result-video")
        self.assertEqual(payload["video"], {"type": "asset_id", "asset_id": "video-asset"})
        self.assertEqual(payload["audio"], {"type": "asset_id", "asset_id": "audio-asset"})
        self.assertEqual(payload["mode"], "precision")
        self.assertFalse(payload["enable_dynamic_duration"])

    def test_heygen_api_error_reports_remote_message(self):
        response = mock.Mock(status_code=401, text="unauthorized")
        response.json.return_value = {"error": {"message": "Invalid API key"}}
        with self.assertRaisesRegex(RuntimeError, "Invalid API key"):
            Worker._heygen_response_data(response)

    def test_overlong_voiceover_extends_video_without_speed_change(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name) / "render"
        folder.mkdir()
        srt = folder / "subtitle.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:30,000\nKeep the original narration speed.\n",
            encoding="utf-8",
        )
        voiceover = folder / "voiceover.wav"
        voiceover.write_bytes(b"audio")
        with mock.patch.object(worker, "make_srt", return_value=srt), \
                mock.patch.object(worker, "make_voiceover", return_value=voiceover), \
                mock.patch.object(worker, "probe_duration", return_value=34.2), \
                mock.patch("worker.subprocess.run") as run:
            worker.compose_video(
                {"duration_seconds": 30, "audio_mode": "mute"},
                [{"path": Path("relative.mp4")}], folder,
            )
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-t") + 1], "34.2")
        self.assertNotIn("atempo", " ".join(command))

    def test_translation_workflow_preserves_source_video_duration(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name) / "preserved-duration"
        folder.mkdir()
        srt = folder / "subtitle.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:20,000\nTranslated narration.\n",
            encoding="utf-8",
        )
        voiceover = folder / "voiceover.wav"
        voiceover.write_bytes(b"audio")
        with mock.patch.object(worker, "make_srt", return_value=srt), \
                mock.patch.object(worker, "make_voiceover", return_value=voiceover), \
                mock.patch.object(worker, "probe_duration", side_effect=[20.0, 30.0]), \
                mock.patch("worker.subprocess.run") as run:
            worker.compose_video({
                "workflow_mode": "single_voice_translation",
                "duration_seconds": 15, "audio_mode": "mute",
            }, [{"path": Path("single.mp4")}], folder)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-t") + 1], "20.0")
        self.assertNotIn("-shortest", command)
        self.assertIn("00:00:20,000", srt.read_text(encoding="utf-8"))

    def test_multi_video_resets_each_trimmed_clip_timestamp_before_concat(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name) / "normalized-sequence"
        folder.mkdir()
        with mock.patch.object(worker, "make_srt", return_value=None), \
                mock.patch.object(worker, "probe_duration", side_effect=[12.0, 20.0, 12.0, 20.0]), \
                mock.patch("worker.subprocess.run") as run:
            worker.compose_video({
                "workflow_mode": "multi_sequence_script",
                "duration_seconds": 5, "audio_mode": "mute", "aspect_ratio": "9:16",
            }, [
                {"path": Path("one.mp4"), "trim_start": 2, "trim_end": 8},
                {"path": Path("two.mp4"), "trim_start": 1, "trim_end": 0},
            ], folder)
        segment_commands = [call.args[0] for call in run.call_args_list[:2]]
        self.assertIn("trim=start=2.000:end=8.000,setpts=PTS-STARTPTS", segment_commands[0][segment_commands[0].index("-vf") + 1])
        self.assertIn("trim=start=1.000:end=20.000,setpts=PTS-STARTPTS", segment_commands[1][segment_commands[1].index("-vf") + 1])
        final_command = run.call_args_list[-1].args[0]
        self.assertIn(str(folder / "normalized-source.mp4"), final_command)
        self.assertEqual(final_command[final_command.index("-t") + 1], "25.0")

    def test_clip_order_can_be_reversed(self):
        worker = Worker(self.config())
        clips = [Path("one.mp4"), Path("two.mp4")]
        self.assertEqual(
            worker.arrange_clips({"edit_mode": "reverse"}, clips, Path(self.work_dir.name)),
            list(reversed(clips)),
        )

    def test_ai_edit_manifest_keeps_timeline_values(self):
        command = Path(self.work_dir.name) / "editor.exe"
        command.write_bytes(b"stub")
        config = self.config()
        config["local_ai"] = {"ai_edit_command": str(command)}
        worker = Worker(config)

        def write_plan(_command, **_kwargs):
            (Path(self.work_dir.name) / "edit-plan.json").write_text("[0]", encoding="utf-8")

        clips = [{"path": Path("one.mp4"), "trim_start": 1.25, "trim_end": 8.5}]
        with mock.patch("worker.subprocess.run", side_effect=write_plan):
            worker.arrange_clips({"edit_mode": "ai"}, clips, Path(self.work_dir.name))
        manifest = json.loads(
            (Path(self.work_dir.name) / "edit-input.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["clips"],
            [{"path": "one.mp4", "trim_start": 1.25, "trim_end": 8.5}],
        )

    def test_compose_manifest_uses_absolute_clip_paths(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        with mock.patch.object(worker, "make_srt", return_value=None), \
                mock.patch("worker.subprocess.run"):
            worker.compose_video(
                {"duration_seconds": 3, "audio_mode": "mute"},
                [{"path": Path("relative.mp4")}], Path(self.work_dir.name) / "render",
            )
        manifest = (Path(self.work_dir.name) / "render" / "concat.txt").read_text(encoding="utf-8")
        self.assertIn(str(Path("relative.mp4").resolve()), manifest)

    def test_final_stitch_uses_only_processed_paths_in_given_order(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name) / "final-stitch"
        first = Path(self.work_dir.name) / "first-processed.mp4"
        second = Path(self.work_dir.name) / "second-processed.mp4"
        first.write_bytes(b"one")
        second.write_bytes(b"two")

        def create_output(command, **_kwargs):
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"video")
            return SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(worker, "probe_duration", side_effect=[2.0, 3.0]), \
                mock.patch("worker.subprocess.run", side_effect=create_output):
            output, subtitle = worker.stitch_processed_clips({"aspect_ratio": "9:16"}, [
                {"path": first, "record_id": 2, "clip_name": "先播"},
                {"path": second, "record_id": 1, "clip_name": "后播"},
            ], folder)

        self.assertTrue(output.is_file())
        self.assertIsNone(subtitle)
        timeline = json.loads((folder / "clip-timeline.json").read_text(encoding="utf-8"))
        self.assertEqual([item["record_id"] for item in timeline], [2, 1])
        self.assertEqual([item["start"] for item in timeline], [0.0, 2.0])

    def test_final_stitch_adds_project_background_music_after_shot_processing(self):
        config = self.config()
        config["ffmpeg"] = "C:/test/ffmpeg.exe"
        worker = Worker(config)
        folder = Path(self.work_dir.name) / "final-stitch-music"
        shot = Path(self.work_dir.name) / "processed-shot.mp4"
        music = Path(self.work_dir.name) / "project-music.mp3"
        shot.write_bytes(b"video")
        music.write_bytes(b"music")
        commands = []

        def create_output(command, **_kwargs):
            commands.append(command)
            if len(command) == 3 and command[1] == "-i":
                return SimpleNamespace(returncode=1, stderr="Stream #0:1: Audio: aac")
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"video")
            return SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(worker, "probe_duration", return_value=2.0), \
                mock.patch("worker.subprocess.run", side_effect=create_output):
            output, _subtitle = worker.stitch_processed_clips({
                "aspect_ratio": "9:16", "background_music": str(music), "music_volume": 0.18,
            }, [{"path": shot, "record_id": 1, "clip_name": "厂房开场"}], folder)

        self.assertTrue(output.is_file())
        self.assertTrue(any("amix=inputs=2:duration=first" in " ".join(command) for command in commands))

    def test_mumu_bridge_uses_configured_serial(self):
        calls = []
        def runner(command, **_kwargs):
            calls.append(command)
            output = "connected to 127.0.0.1:7555" if command[1] == "connect" else "device"
            return SimpleNamespace(returncode=0, stdout=output, stderr="")
        with TemporaryDirectory() as folder:
            adb = Path(folder) / "adb.exe"
            adb.write_bytes(b"")
            result = MumuBridge(str(adb), "127.0.0.1:7555", runner=runner).connect()
        self.assertEqual(result["state"], "device")
        self.assertEqual(calls[0][1:], ["connect", "127.0.0.1:7555"])
        self.assertEqual(calls[1][1:], ["-s", "127.0.0.1:7555", "get-state"])

    def test_mumu_serial_discovery_reads_running_android_instance(self):
        def runner(_command, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"0":{"adb_host_ip":"127.0.0.1","adb_port":16384,"is_android_started":true}}',
                stderr="",
            )
        with mock.patch("mumu_adapter._candidate_roots", return_value=[Path("D:/MuMu")]), \
                mock.patch.object(Path, "is_file", return_value=True):
            self.assertEqual(discover_serial(runner), "127.0.0.1:16384")

    def test_mumu_image_search_enters_reference_image_automatically(self):
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            joined = " ".join(command)
            if " get-state" in joined:
                output = "device"
            elif "pm list packages com.lightlink.selector" in joined:
                output = "package:com.lightlink.selector"
            elif "pm list packages" in joined:
                output = "package:com.ss.android.ugc.aweme"
            elif "wm size" in joined:
                output = "Physical size: 1440x2560"
            elif "dumpsys activity activities" in joined:
                output = "topResumedActivity=com.ss.android.ugc.aweme/.search.visualsearch.VisualSearchActivity"
            else:
                output = "connected"
            return SimpleNamespace(returncode=0, stdout=output, stderr="")

        with TemporaryDirectory() as folder, \
                mock.patch("mumu_adapter.find_adb", return_value="D:/MuMu/adb.exe"), \
                mock.patch("mumu_adapter.find_player", return_value=""), \
                mock.patch("mumu_adapter.time.sleep"):
            image = Path(folder) / "reference.jpg"
            image.write_bytes(b"image")
            remote = MumuBridge(
                "D:/MuMu/adb.exe", "127.0.0.1:16384", runner=runner,
                selector_port=18765, selector_token="test-token",
            ).prepare_image_search(image, 3)

        taps = [call[-2:] for call in calls if "input" in call and "tap" in call]
        self.assertEqual(remote, "/sdcard/Pictures/LightLink/task-3.jpg")
        self.assertEqual(taps, [["1380", "82"], ["1259", "82"], ["1125", "2240"], ["176", "330"]])
        joined_calls = [" ".join(call) for call in calls]
        self.assertTrue(any("reverse tcp:18765 tcp:18765" in call for call in joined_calls))
        self.assertTrue(any("lightlink://configure?" in call and "task_id=3" in call for call in joined_calls))

    def test_selector_bridge_accepts_authenticated_local_submission(self):
        store = SelectionStore(Path(self.work_dir.name) / "bridge.db")
        store.save_task({"id": 55, "keywords": "鞋", "target_language": "English"})
        changes = []
        bridge = SelectorBridge(store, "secret", lambda task_id, added: changes.append((task_id, added)))
        bridge.start()
        try:
            body = json.dumps({
                "task_id": 55,
                "urls": ["https://www.douyin.com/video/7531234567890123456"],
            }).encode("utf-8")
            request = Request(
                "http://127.0.0.1:%s/selection/submit" % bridge.port,
                data=body, method="POST",
                headers={"Content-Type": "application/json", "X-LightLink-Token": "secret"},
            )
            response = json.loads(urlopen(request, timeout=3).read())
        finally:
            bridge.close()
        self.assertTrue(response["ok"])
        self.assertEqual(response["added"], 1)
        self.assertEqual(changes, [(55, 1)])
        self.assertEqual(len(store.list(55)), 1)

    def test_selection_store_saves_metadata_and_deduplicates(self):
        store = SelectionStore(Path(self.work_dir.name) / "selections.db")
        text = (
            "分享 https://www.douyin.com/video/7531234567890123456 复制打开\n"
            "https://www.douyin.com/video/7531234567890123456"
        )
        self.assertEqual(store.add_text(101, text), 1)
        rows = store.list(101)
        self.assertEqual(rows[0]["video_id"], "7531234567890123456")
        self.assertTrue(rows[0]["selected_at"])
        self.assertEqual(rows[0]["status"], "selected")
        store.update(
            rows[0]["id"], status="downloaded", local_path="D:/video.mp4",
            cover_path="D:/cover.jpg", caption="视频原文案", duration=12.5,
            caption_checked=1, media_checked=1,
        )
        saved_video = store.list(101)[0]
        self.assertEqual(saved_video["status"], "downloaded")
        self.assertEqual(saved_video["cover_path"], "D:/cover.jpg")
        self.assertEqual(saved_video["caption"], "视频原文案")
        self.assertEqual(saved_video["duration"], 12.5)
        self.assertEqual(saved_video["caption_checked"], 1)
        self.assertEqual(saved_video["media_checked"], 1)
        store.save_task({"id": 101, "keywords": "鞋子", "target_language": "English"})
        self.assertEqual(store.get_task(101)["keywords"], "鞋子")
        store.set_task_status(101, "done")
        self.assertEqual(store.list_tasks()[0]["local_status"], "done")

    def test_raw_library_is_global_deduplicated_and_survives_project_deletion(self):
        store = SelectionStore(Path(self.work_dir.name) / "global-sources.db")
        store.save_task({"id": -1, "local_only": True, "name": "项目一"}, status="draft")
        store.save_task({"id": -2, "local_only": True, "name": "项目二"}, status="draft")
        url = "https://www.douyin.com/video/7531234567890123456"

        self.assertEqual(store.add_text(-1, url), 1)
        self.assertEqual(store.add_text(-2, url), 0)
        sources = store.list_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["task_id"], -1)

        store.delete_task(-1)

        self.assertIsNone(store.get_task(-1))
        self.assertEqual(store.list(-1), sources)
        self.assertEqual(store.list_sources(), sources)

    def test_local_project_files_and_review_result_are_persisted(self):
        store = SelectionStore(Path(self.work_dir.name) / "local-projects.db")
        task_id = store.next_local_task_id()
        store.save_task({
            "id": task_id, "local_only": True, "name": "Local test",
            "target_language": "English",
        }, status="draft")
        video = Path(self.work_dir.name) / "clip.mp4"
        video.write_bytes(b"video")
        self.assertEqual(store.add_local_files(task_id, [video]), 1)
        row = store.list(task_id)[0]
        self.assertEqual(row["status"], "downloaded")
        self.assertEqual(Path(row["local_path"]), video)
        self.assertEqual(row["caption"], "clip")
        store.reset_download([row["id"]])
        preserved = store.list(task_id)[0]
        self.assertEqual(preserved["status"], "downloaded")
        self.assertEqual(Path(preserved["local_path"]), video)
        output = Path(self.work_dir.name) / "output.mp4"
        store.set_task_result(
            task_id, output, status="ready_review", source_video_ids=[row["id"]],
        )
        saved = store.get_task(task_id)
        self.assertEqual(saved["local_status"], "ready_review")
        self.assertEqual(saved["result_path"], str(output))
        store.set_task_result(task_id, output.with_name("output-v2.mp4"), status="ready_review")
        versions = store.list_versions(task_id)
        self.assertEqual([item["version_no"] for item in versions], [2, 1])
        self.assertEqual(versions[1]["source_video_ids"], [row["id"]])
        store.set_task_result(
            task_id, output.with_name("output-v5.mp4"), status="ready_review", version_no=5,
        )
        self.assertEqual(store.next_render_version(task_id), 6)
        latest = store.list_versions(task_id)[0]
        store.delete_version(task_id, latest["id"])
        self.assertEqual([item["version_no"] for item in store.list_versions(task_id)], [2, 1])
        self.assertEqual(store.get_task(task_id)["result_path"], str(output.with_name("output-v2.mp4")))
        remaining = store.list_versions(task_id)
        deleted = store.delete_versions(task_id, [item["id"] for item in remaining])
        self.assertEqual(len(deleted), 2)
        self.assertEqual(store.list_versions(task_id), [])
        self.assertEqual(store.get_task(task_id)["result_path"], "")
        self.assertEqual(store.get_task(task_id)["local_status"], "downloaded")

    def test_clip_timeline_and_copyright_are_persisted(self):
        store = SelectionStore(Path(self.work_dir.name) / "timeline.db")
        store.add_text(7, "https://www.douyin.com/video/7531234567890123456")
        row = store.list(7)[0]
        store.update(
            row["id"], trim_start=1.25, trim_end=8.5,
            copyright_status="authorized", copyright_note="supplier approved",
        )
        saved = store.list(7)[0]
        self.assertEqual(saved["trim_start"], 1.25)
        self.assertEqual(saved["trim_end"], 8.5)
        self.assertEqual(saved["copyright_status"], "authorized")

    def test_source_and_derived_clip_workflow_are_persisted(self):
        store = SelectionStore(Path(self.work_dir.name) / "clip-workflow.db")
        store.add_text(
            9, "https://www.douyin.com/video/7531234567890123456",
            source_kind="douyin_search",
        )
        source = store.list(9)[0]
        store.update(
            source["id"], status="downloaded", local_path="D:/source.mp4",
            duration=30, clip_type="no_face",
        )
        clip_id = store.create_clip(
            source["id"], 3.5, 11.25, "产品口播", "talking_face",
        )
        source, clip = store.list(9)
        self.assertEqual(source["source_kind"], "douyin_search")
        self.assertEqual(source["record_kind"], "source")
        self.assertEqual(clip["id"], clip_id)
        self.assertEqual(clip["record_kind"], "derived_clip")
        self.assertEqual(clip["parent_id"], source["id"])
        self.assertEqual(clip["clip_name"], "产品口播")
        self.assertEqual(clip["clip_type"], "talking_face")
        self.assertEqual(clip["local_path"], "D:/source.mp4")
        self.assertEqual(clip["trim_start"], 3.5)
        self.assertEqual(clip["trim_end"], 11.25)

    def test_per_clip_subtitle_cleanup_settings_are_persisted(self):
        store = SelectionStore(Path(self.work_dir.name) / "subtitle-cleanup.db")
        store.add_text(8, "https://www.douyin.com/video/7531234567890123456")
        row = store.list(8)[0]
        self.assertEqual(row["subtitle_cleanup_policy"], "inherit")
        store.update(
            row["id"], subtitle_cleanup_policy="clean",
            subtitle_cleanup_mode="ai_manual", subtitle_cleanup_quality="high",
            subtitle_cleanup_engine="sttn", subtitle_quick_method="blur",
            subtitle_region="5,70,90,24",
        )
        saved = store.list(8)[0]
        self.assertEqual(saved["subtitle_cleanup_policy"], "clean")
        self.assertEqual(saved["subtitle_cleanup_mode"], "ai_manual")
        self.assertEqual(saved["subtitle_cleanup_engine"], "sttn")
        self.assertEqual(saved["subtitle_cleanup_quality"], "high")
        self.assertEqual(saved["subtitle_region"], "5,70,90,24")
        store.update(
            row["id"], subtitle_cleaned_path="C:/prepared.mp4",
            subtitle_cleanup_signature="abc", subtitle_cleanup_status="ready",
        )
        prepared = store.list(8)[0]
        self.assertEqual(prepared["subtitle_cleanup_status"], "ready")
        self.assertEqual(prepared["subtitle_cleaned_path"], "C:/prepared.mp4")

    def test_project_voice_change_invalidates_all_processed_clips(self):
        store = SelectionStore(Path(self.work_dir.name) / "processed-clips.db")
        store.add_text(12, "\n".join((
            "https://www.douyin.com/video/7531234567890123456",
            "https://www.douyin.com/video/7531234567890123457",
        )))
        rows = store.list(12)
        for index, row in enumerate(rows, 1):
            store.update(
                row["id"], processed_path="C:/clip-%s.mp4" % index,
                processed_kind="HeyGen口型片段", processing_status="ready",
                voice_signature="old-voice",
            )

        store.invalidate_processed(12)

        for row in store.list(12):
            self.assertEqual(row["processed_path"], "")
            self.assertEqual(row["processing_status"], "")
            self.assertEqual(row["voice_signature"], "")

    def test_selection_url_parser_accepts_only_douyin(self):
        urls = extract_douyin_urls(
            "https://v.douyin.com/abc123/ https://example.com/video "
            "https://www.douyin.com/video/7531234567890123456?modal_id=1"
        )
        self.assertEqual(len(urls), 2)
        self.assertEqual(extract_video_id(urls[1]), "7531234567890123456")

    def test_v2_storyboard_and_local_library_workflow(self):
        folder = Path(self.work_dir.name)
        store = SelectionStore(folder / "media-library-v2.db")
        store.save_task({"id": 88, "name": "工厂介绍"})
        storyboard = [{
            "slot_key": "factory-opening", "sequence": 10, "name": "厂房开场",
            "purpose": "建立可信度", "visual_requirement": "厂房外景",
            "target_duration": 3, "required": True,
        }, {
            "slot_key": "production-line", "sequence": 20, "name": "生产线",
            "purpose": "展示产能", "visual_requirement": "生产过程",
            "target_duration": 5, "required": True,
        }]
        store.sync_storyboard(88, storyboard)
        opening = folder / "factory-opening.mp4"
        opening.write_bytes(b"video")
        opening_uuid = store.register_asset({
            "name": "厂房开场", "file_path": str(opening), "asset_kind": "standard_shot",
            "clip_type": "no_face", "role_code": "factory", "track_code": "footwear",
            "scope_code": "factory_intro", "shot_purpose": "建立可信度",
            "copyright_status": "authorized",
        })
        line = folder / "production-line.mp4"
        line.write_bytes(b"video")
        line_uuid = store.register_asset({
            "name": "生产线", "file_path": str(line), "asset_kind": "standard_shot",
            "clip_type": "no_face", "role_code": "factory", "track_code": "footwear",
            "scope_code": "factory_intro", "shot_purpose": "展示产能",
            "copyright_status": "authorized",
        })

        store.mark_storyboard_candidate(88, "factory-opening")
        store.sync_storyboard(88, storyboard)
        self.assertEqual(store.list_storyboard(88)[0]["state"], "ready")
        store.select_asset_for_composition(88, "factory-opening", opening_uuid)
        store.select_asset_for_composition(88, "production-line", line_uuid)

        self.assertEqual(store.list(88), [])
        composition = store.list_composition(88)
        self.assertEqual([row["slot_key"] for row in composition], [
            "factory-opening", "production-line",
        ])
        self.assertEqual(store.list_storyboard(88)[0]["state"], "selected")
        self.assertEqual(store.list_assets()[0]["scope_code"], "factory_intro")

        store.move_composition(88, [composition[1]["id"]], -1)
        moved = store.list_composition(88)
        self.assertEqual([row["slot_key"] for row in moved], [
            "production-line", "factory-opening",
        ])
        store.select_asset_for_composition(88, "factory-opening", line_uuid)
        self.assertEqual(len(store.list_composition(88)), 2)
        self.assertEqual(
            next(row for row in store.list_composition(88) if row["slot_key"] == "factory-opening")["asset_uuid"],
            line_uuid,
        )
        store.remove_composition(88, [moved[0]["id"]])
        self.assertTrue(line.is_file())
        self.assertEqual(len(store.list_assets()), 2)
        self.assertEqual(
            next(row for row in store.list_storyboard(88) if row["slot_key"] == "production-line")["state"],
            "ready",
        )

    def test_complete_uploads_final_manifest(self):
        folder = Path(self.work_dir.name)
        output = folder / "final.mp4"
        output.write_bytes(b"video")
        worker = Worker(self.config())
        manifest = {"schema": "lightlink-media-v2", "used_assets": [{
            "asset_uuid": "asset-1", "shot_key": "opening",
        }]}
        with mock.patch.object(worker, "api") as api:
            worker.complete({"id": 9}, output, None, manifest=manifest)
        _args, kwargs = api.call_args
        self.assertEqual(json.loads(kwargs["data"]["manifest"]), manifest)


if __name__ == "__main__":
    unittest.main()
