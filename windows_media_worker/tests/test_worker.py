import sys
import unittest
import requests
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import Worker
from mumu_adapter import MumuBridge, discover_serial
from selection_store import SelectionStore, extract_douyin_urls, extract_video_id


class StopAfterFirstHeartbeat:
    def __init__(self):
        self.calls = 0

    def wait(self, _seconds):
        self.calls += 1
        return self.calls > 1


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

    def test_target_language_video_script_skips_ollama(self):
        worker = NoTranslationWorker(self.config())
        task = {
            "video_script": "Ready-to-use English subtitle",
            "source_mode": "auto", "target_language": "English", "duration_seconds": 15,
        }
        srt = worker.make_srt(task, Path(self.work_dir.name))
        self.assertIn("Ready-to-use English subtitle", srt.read_text(encoding="utf-8"))

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

    def test_selection_url_parser_accepts_only_douyin(self):
        urls = extract_douyin_urls(
            "https://v.douyin.com/abc123/ https://example.com/video "
            "https://www.douyin.com/video/7531234567890123456?modal_id=1"
        )
        self.assertEqual(len(urls), 2)
        self.assertEqual(extract_video_id(urls[1]), "7531234567890123456")


if __name__ == "__main__":
    unittest.main()
