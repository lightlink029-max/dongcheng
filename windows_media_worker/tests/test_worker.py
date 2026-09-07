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

    def test_worker_identity_is_sent_with_every_request(self):
        worker = Worker(self.config())
        self.assertEqual(worker.headers["X-LightLink-Worker-ID"], "media-test-01")
        self.assertEqual(worker.headers["Authorization"], "Bearer test-token")

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
        store.update(rows[0]["id"], status="downloaded", local_path="D:/video.mp4")
        self.assertEqual(store.list(101)[0]["status"], "downloaded")
        store.save_task({"id": 101, "keywords": "鞋子", "target_language": "English"})
        self.assertEqual(store.get_task(101)["keywords"], "鞋子")
        store.set_task_status(101, "done")
        self.assertEqual(store.list_tasks()[0]["local_status"], "done")

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

    def test_selection_url_parser_accepts_only_douyin(self):
        urls = extract_douyin_urls(
            "https://v.douyin.com/abc123/ https://example.com/video "
            "https://www.douyin.com/video/7531234567890123456?modal_id=1"
        )
        self.assertEqual(len(urls), 2)
        self.assertEqual(extract_video_id(urls[1]), "7531234567890123456")


if __name__ == "__main__":
    unittest.main()
