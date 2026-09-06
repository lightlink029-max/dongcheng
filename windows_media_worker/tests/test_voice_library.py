import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_library import default_voice_profiles, load_voice_profiles, save_voice_profiles


class VoiceLibraryTests(unittest.TestCase):
    def test_each_provider_default_voice_is_available(self):
        profiles = default_voice_profiles(r"D:\models\vits-zh.onnx")
        by_provider = {}
        for profile in profiles:
            by_provider.setdefault(profile["provider"], []).append(profile)

        self.assertNotIn("windows", by_provider)
        self.assertEqual(by_provider["sherpa"][0]["voice_id"], "0")
        self.assertEqual(by_provider["sherpa"][0]["source"], "Sherpa 本地模型")
        self.assertEqual(by_provider["volcengine"][0]["voice_id"], "zh_female_vv_uranus_bigtts")
        self.assertTrue(all(item["source_url"] for item in profiles))
        self.assertTrue(all(not item["editable"] for item in profiles))

    def test_profiles_round_trip_with_source(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "voices.json"
            profiles = [{
                "id": "voice-1", "name": "English Female", "provider": "volcengine",
                "voice_id": "BV001", "source": "Volcengine account",
                "source_url": "https://example.com/voices",
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
