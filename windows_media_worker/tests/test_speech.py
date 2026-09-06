import base64
import json
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

    def test_volcengine_v3_tts_writes_streamed_audio(self):
        response = mock.Mock()
        response.status_code = 200
        response.iter_lines.return_value = [
            "event: 352",
            "data: " + json.dumps({
                "code": 20000000,
                "data": base64.b64encode(b"audio-").decode("ascii"),
            }),
            "data: " + json.dumps({
                "code": 20000000,
                "data": base64.b64encode(b"data").decode("ascii"),
            }),
        ]
        with TemporaryDirectory() as folder, mock.patch("speech.requests.post", return_value=response) as post:
            output = Path(folder) / "voice.wav"
            result = synthesize({
                "volc_api_key": "api-key", "volc_resource_id": "seed-tts-2.0",
            }, "volcengine", "hello", output, "voice-id", 1.1, 0.8)
            self.assertEqual(result.suffix, ".mp3")
            self.assertEqual(result.read_bytes(), b"audio-data")
        payload = post.call_args.kwargs["json"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(payload["req_params"]["speaker"], "voice-id")
        self.assertEqual(payload["req_params"]["audio_params"]["speech_rate"], 10)
        self.assertEqual(headers["X-Api-Key"], "api-key")
        self.assertEqual(headers["X-Api-Resource-Id"], "seed-tts-2.0")
        self.assertTrue(post.call_args.kwargs["stream"])
        response.close.assert_called_once()

    def test_volcengine_requires_new_api_key(self):
        with TemporaryDirectory() as folder, self.assertRaisesRegex(
            RuntimeError, "新版 API Key"
        ):
            synthesize({}, "volcengine", "hello", Path(folder) / "voice.wav")


if __name__ == "__main__":
    unittest.main()
