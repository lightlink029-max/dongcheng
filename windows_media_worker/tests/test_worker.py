import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import Worker


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

    def test_non_douyin_url_is_rejected(self):
        worker = DownloadWorker(self.config())
        with self.assertRaisesRegex(ValueError, "仅接受抖音链接"):
            worker.download_url("https://example.com/video", Path(self.work_dir.name), 1)
        self.assertEqual(worker.calls, [])


if __name__ == "__main__":
    unittest.main()
