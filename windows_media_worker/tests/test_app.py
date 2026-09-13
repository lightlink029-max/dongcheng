import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import MediaWorkerApp


class SelectionFolderTests(unittest.TestCase):
    def test_selected_download_opens_its_containing_folder(self):
        with TemporaryDirectory() as folder:
            video = Path(folder) / "downloaded" / "video.mp4"
            video.parent.mkdir()
            video.touch()

            result = MediaWorkerApp._selection_folder(
                {"id": 3}, [{"local_path": str(video)}], Path(folder) / "jobs",
            )

            self.assertEqual(result, video.parent.resolve())

    def test_project_download_folder_is_used_without_a_downloaded_selection(self):
        with TemporaryDirectory() as folder:
            work_dir = Path(folder) / "jobs"

            result = MediaWorkerApp._selection_folder(
                {"id": 3}, [{"local_path": ""}], work_dir,
            )

            self.assertEqual(result, work_dir.resolve() / "3" / "selected-videos")

    def test_mix_source_prefers_ready_cleaned_copy(self):
        with TemporaryDirectory() as folder:
            original = Path(folder) / "original.mp4"
            cleaned = Path(folder) / "cleaned.mp4"
            original.touch()
            cleaned.touch()

            result = MediaWorkerApp._mix_source_path({
                "local_path": str(original),
                "subtitle_cleaned_path": str(cleaned),
                "subtitle_cleanup_status": "ready",
            })

            self.assertEqual(result, cleaned)

    def test_mix_source_keeps_original_until_cleanup_is_ready(self):
        with TemporaryDirectory() as folder:
            original = Path(folder) / "original.mp4"
            cleaned = Path(folder) / "cleaned.mp4"
            original.touch()
            cleaned.touch()

            result = MediaWorkerApp._mix_source_path({
                "local_path": str(original),
                "subtitle_cleaned_path": str(cleaned),
                "subtitle_cleanup_status": "processing",
            })

            self.assertEqual(result, original)

    def test_mix_source_prefers_ready_processed_clip(self):
        with TemporaryDirectory() as folder:
            original = Path(folder) / "original.mp4"
            cleaned = Path(folder) / "cleaned.mp4"
            processed = Path(folder) / "processed.mp4"
            for path in (original, cleaned, processed):
                path.touch()

            result = MediaWorkerApp._mix_source_path({
                "local_path": str(original),
                "subtitle_cleaned_path": str(cleaned),
                "subtitle_cleanup_status": "ready",
                "processed_path": str(processed),
                "processing_status": "ready",
            })

            self.assertEqual(result, processed)

    def test_project_voice_signature_changes_with_voice(self):
        first = MediaWorkerApp._voice_signature({
            "tts_provider": "sherpa", "tts_voice": "voice-a",
            "tts_model_id": "model", "tts_speed": 1.0, "tts_volume": 1.0,
        })
        second = MediaWorkerApp._voice_signature({
            "tts_provider": "sherpa", "tts_voice": "voice-b",
            "tts_model_id": "model", "tts_speed": 1.0, "tts_volume": 1.0,
        })
        self.assertNotEqual(first, second)

    def test_plan_summary_keeps_only_two_compact_lines(self):
        summary = MediaWorkerApp._compact_plan_summary(
            "第一行\n" + ("第二行内容" * 30) + "\n第三行完整画面证据"
        )

        lines = summary.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertLessEqual(len(lines[1]), 72)
        self.assertTrue(lines[1].endswith("…"))

    def test_source_material_state_matches_the_visible_workflow(self):
        self.assertEqual(
            MediaWorkerApp._source_material_state({"status": "selected"})[0],
            "pending_download",
        )
        self.assertEqual(
            MediaWorkerApp._source_material_state({
                "status": "downloaded", "subtitle_cleanup_policy": "clean",
                "subtitle_cleanup_status": "pending",
            })[0],
            "pending_cleanup",
        )
        self.assertEqual(
            MediaWorkerApp._source_material_state({
                "status": "downloaded", "processing_status": "processing",
            })[0],
            "processing",
        )
        self.assertEqual(
            MediaWorkerApp._source_material_state({
                "status": "downloaded", "processing_status": "failed",
            })[0],
            "failed",
        )
        with TemporaryDirectory() as folder:
            processed = Path(folder) / "shot.mp4"
            processed.touch()
            self.assertEqual(
                MediaWorkerApp._source_material_state({
                    "status": "downloaded", "processing_status": "ready",
                    "processed_path": str(processed),
                })[0],
                "ready",
            )

    def test_production_material_state_identifies_the_next_action(self):
        self.assertEqual(
            MediaWorkerApp._production_material_state({
                "status": "downloaded", "clip_type": "unknown",
            })[0],
            "unclassified",
        )
        self.assertEqual(
            MediaWorkerApp._production_material_state({
                "status": "downloaded", "clip_type": "talking_face",
                "subtitle_cleanup_policy": "clean", "subtitle_cleanup_status": "pending",
            })[0],
            "pending_cleanup",
        )
        self.assertEqual(
            MediaWorkerApp._production_material_state({
                "status": "downloaded", "clip_type": "no_face",
                "subtitle_cleanup_policy": "skip",
            })[0],
            "pending_generation",
        )


if __name__ == "__main__":
    unittest.main()
