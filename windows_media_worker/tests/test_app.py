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


if __name__ == "__main__":
    unittest.main()
