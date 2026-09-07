import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_library import (
    SHERPA_KOKORO_EN_VOICES,
    VOLCENGINE_TTS_2_ENGLISH_VOICES,
    default_voice_profiles,
    load_voice_profiles,
    save_voice_profiles,
)


class VoiceLibraryTests(unittest.TestCase):
    def test_installed_kokoro_english_voices_are_available(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            current = root / "vits-piper-en_US-lessac-medium" / "model.onnx"
            kokoro = root / "kokoro-en-v0_19" / "model.onnx"
            current.parent.mkdir()
            kokoro.parent.mkdir()
            current.touch()
            kokoro.touch()
            profiles = default_voice_profiles(str(current))
        kokoro_profiles = [
            item for item in profiles if item["source"] == "Sherpa Kokoro 英文模型"
        ]
        self.assertEqual(len(kokoro_profiles), len(SHERPA_KOKORO_EN_VOICES))
        self.assertEqual({item["voice_id"] for item in kokoro_profiles}, {str(i) for i in range(11)})

    def test_each_provider_default_voice_is_available(self):
        profiles = default_voice_profiles(r"D:\models\vits-zh.onnx")
        by_provider = {}
        for profile in profiles:
            by_provider.setdefault(profile["provider"], []).append(profile)

        self.assertNotIn("windows", by_provider)
        self.assertEqual(by_provider["sherpa"][0]["voice_id"], "0")
        self.assertEqual(by_provider["sherpa"][0]["source"], "Sherpa 本地模型")
        self.assertEqual(by_provider["volcengine"][0]["voice_id"], "zh_female_vv_uranus_bigtts")
        self.assertGreaterEqual(len(by_provider["volcengine"]), 10)
        self.assertTrue(all(
            item["model_id"] == "seed-tts-2.0"
            for item in by_provider["volcengine"]
        ))
        self.assertTrue(all(item["source_url"] for item in profiles))
        self.assertTrue(all(not item["editable"] for item in profiles))

    def test_official_tts_2_english_voices_are_available(self):
        self.assertEqual(len(VOLCENGINE_TTS_2_ENGLISH_VOICES), 84)
        voice_ids = [item[1] for item in VOLCENGINE_TTS_2_ENGLISH_VOICES]
        self.assertEqual(len(voice_ids), len(set(voice_ids)))
        self.assertIn("ICL_uranus_en_male_michael_tob", voice_ids)
        self.assertIn("en_female_skye_uranus_bigtts", voice_ids)
        profiles = default_voice_profiles()
        available_ids = {item["voice_id"] for item in profiles}
        self.assertTrue(set(voice_ids).issubset(available_ids))

    def test_profiles_round_trip_with_source(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "voices.json"
            profiles = [{
                "id": "voice-1", "name": "English Female", "provider": "volcengine",
                "voice_id": "BV001", "source": "Volcengine account",
                "source_url": "https://example.com/voices",
                "model_id": "seed-tts-2.0", "language": "English",
                "description": "General purpose",
            }]
            save_voice_profiles(path, profiles)
            self.assertEqual(load_voice_profiles(path), profiles)

    def test_invalid_library_is_ignored(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "voices.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(load_voice_profiles(path), [])


if __name__ == "__main__":
    unittest.main()
