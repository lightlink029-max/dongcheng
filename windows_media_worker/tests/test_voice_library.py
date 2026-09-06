import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_library import load_voice_profiles, save_voice_profiles


class VoiceLibraryTests(unittest.TestCase):
    def test_profiles_round_trip_with_source(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "voices.json"
            profiles = [{
                "id": "voice-1", "name": "English Female", "provider": "volcengine",
                "voice_id": "BV001", "source": "Volcengine account",
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
