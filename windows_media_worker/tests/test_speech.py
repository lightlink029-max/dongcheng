import base64
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speech import synthesize


class SpeechTests(unittest.TestCase):
    def test_sherpa_tts_rejects_empty_configuration(self):
        with TemporaryDirectory() as folder, self.assertRaisesRegex(
            RuntimeError, "sherpa-onnx 尚未完整配置"
        ):
            synthesize({}, "sherpa", "hello", Path(folder) / "voice.wav")

    def test_volcengine_tts_writes_returned_audio(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "code": 3000, "data": base64.b64encode(b"wave-data").decode("ascii"),
        }
        with TemporaryDirectory() as folder, mock.patch("speech.requests.post", return_value=response) as post:
            output = Path(folder) / "voice.wav"
            synthesize({
                "volc_app_id": "app", "volc_token": "token", "volc_cluster": "cluster",
            }, "volcengine", "hello", output, "voice-id", 1.1, 0.8)
            self.assertEqual(output.read_bytes(), b"wave-data")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["audio"]["voice_type"], "voice-id")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer;token")


if __name__ == "__main__":
    unittest.main()
