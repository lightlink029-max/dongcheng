import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import DownloadLinkParser, Worker


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
    def __init__(self, config, online_error=None):
        super().__init__(config)
        self.online_error = online_error
        self.calls = []

    def download_via_online_service(self, _url, target):
        self.calls.append("online")
        if self.online_error:
            raise self.online_error
        target.write_bytes(b"video")
        return target

    def download_via_ytdlp(self, _url, target_dir, index):
        self.calls.append("yt-dlp")
        target = target_dir / f"source-{index}.mp4"
        target.write_bytes(b"fallback")
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

    def test_online_download_link_parser_only_accepts_proxy_routes(self):
        parser = DownloadLinkParser()
        parser.feed('<a href="https://unsafe.example/video.mp4">x</a>'
                    '<a href="/api/proxy?url=https%3A%2F%2Fvideo.example">download</a>')
        self.assertEqual(parser.links, ["/api/proxy?url=https%3A%2F%2Fvideo.example"])

    def test_download_proxy_is_optional(self):
        worker = Worker(self.config())
        self.assertIsNone(worker.download_proxies())
        worker.config["download_proxy"] = "http://127.0.0.1:10808"
        self.assertEqual(worker.download_proxies(), {
            "http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808",
        })

    def test_online_downloader_is_preferred(self):
        worker = DownloadWorker(self.config())
        target = worker.download_url("https://example.com/video", Path(self.work_dir.name), 1)
        self.assertEqual(worker.calls, ["online"])
        self.assertEqual(target.read_bytes(), b"video")

    def test_ytdlp_is_used_after_online_failure(self):
        worker = DownloadWorker(self.config(), RuntimeError("offline"))
        target = worker.download_url("https://example.com/video", Path(self.work_dir.name), 1)
        self.assertEqual(worker.calls, ["online", "yt-dlp"])
        self.assertEqual(target.read_bytes(), b"fallback")


if __name__ == "__main__":
    unittest.main()
