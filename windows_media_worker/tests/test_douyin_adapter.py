import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from douyin_adapter import download_video


class DouyinAdapterTests(unittest.TestCase):
    def test_transient_detail_failure_rebuilds_session_and_retries(self):
        attempts = []

        async def fake_download(_url, output_dir, _cookies, _proxy):
            attempts.append(output_dir)
            if len(attempts) == 1:
                raise RuntimeError("Douyin Downloader 未能下载该视频，请更新抖音登录后重试")
            (output_dir / "1234567890123456789.mp4").write_bytes(b"video")
            return "1234567890123456789"

        with TemporaryDirectory() as folder, \
                mock.patch("douyin_adapter.load_cookies", return_value={"sessionid": "saved"}), \
                mock.patch("douyin_adapter._download", side_effect=fake_download), \
                mock.patch("douyin_adapter.time.sleep") as sleep:
            target = Path(folder) / "selected" / "video.mp4"
            result, video_id = download_video(
                "https://v.douyin.com/example/", target, "secrets.json",
                return_video_id=True,
            )
            downloaded = result.read_bytes()

        self.assertEqual(len(attempts), 2)
        sleep.assert_called_once_with(2)
        self.assertEqual(video_id, "1234567890123456789")
        self.assertEqual(downloaded, b"video")


if __name__ == "__main__":
    unittest.main()
