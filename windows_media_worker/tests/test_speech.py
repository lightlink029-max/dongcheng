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

    def test_sherpa_kokoro_uses_model_local_files(self):
        with TemporaryDirectory() as folder, mock.patch("speech.subprocess.run") as run:
            root = Path(folder)
            executable = root / "sherpa-onnx-offline-tts.exe"
            model_dir = root / "kokoro-en-v0_19"
            data_dir = model_dir / "espeak-ng-data"
            data_dir.mkdir(parents=True)
            executable.touch()
            for name in ("model.onnx", "tokens.txt", "voices.bin"):
                (model_dir / name).touch()
            output = root / "voice.wav"
            synthesize({
                "sherpa_command": str(executable),
                "sherpa_model": str(model_dir / "model.onnx"),
                "sherpa_tokens": "wrong-tokens",
                "sherpa_data_dir": "wrong-data",
            }, "sherpa", "hello", output, "7")
            command = run.call_args.args[0]
            self.assertIn("--kokoro-model=" + str(model_dir / "model.onnx"), command)
            self.assertIn("--kokoro-voices=" + str(model_dir / "voices.bin"), command)
            self.assertIn("--kokoro-tokens=" + str(model_dir / "tokens.txt"), command)
            self.assertIn("--sid=7", command)

    def test_volcengine_v3_tts_writes_streamed_audio(self):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {"X-Tt-Logid": "test-log-id"}
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

    def test_volcengine_no_audio_reports_resource_voice_and_log_id(self):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {"X-Tt-Logid": "log-123"}
        response.iter_lines.return_value = [
            'data: {"code": 20000000, "message": "OK", "data": null}',
        ]
        with TemporaryDirectory() as folder, mock.patch("speech.requests.post", return_value=response):
            with self.assertRaisesRegex(
                RuntimeError,
                "Resource ID=seed-tts-2.0；音色 ID=en_voice；Log ID=log-123",
            ):
                synthesize({
                    "volc_api_key": "api-key", "volc_resource_id": "seed-tts-2.0",
                }, "volcengine", "hello", Path(folder) / "voice.wav", "en_voice")

    def test_volcengine_accepts_string_success_code(self):
        response = mock.Mock()
        response.status_code = 200
        response.headers = {}
        response.iter_lines.return_value = [
            "data: " + json.dumps({
                "code": "0", "data": base64.b64encode(b"audio").decode("ascii"),
            }),
            'data: {"code": "20000000", "message": "OK", "data": null}',
        ]
        with TemporaryDirectory() as folder, mock.patch("speech.requests.post", return_value=response):
            result = synthesize({
                "volc_api_key": "api-key", "volc_resource_id": "seed-tts-2.0",
            }, "volcengine", "hello", Path(folder) / "voice.wav", "en_voice")
            self.assertEqual(result.read_bytes(), b"audio")

    def test_volcengine_requires_new_api_key(self):
        with TemporaryDirectory() as folder, self.assertRaisesRegex(
            RuntimeError, "新版 API Key"
        ):
            synthesize({}, "volcengine", "hello", Path(folder) / "voice.wav")


if __name__ == "__main__":
    unittest.main()
