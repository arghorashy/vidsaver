from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vidsaver.playlist import PlaylistError, VIDEO_EXTENSIONS, scan


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


class ScanPlaylistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)

    # Missing or unreadable folder

    def test_missing_folder_raises(self) -> None:
        missing = self.root / "nope"
        with self.assertRaises(PlaylistError) as ctx:
            scan(missing)
        self.assertIn("does not exist", str(ctx.exception))
        self.assertIn(str(missing), str(ctx.exception))

    def test_file_instead_of_folder_raises(self) -> None:
        path = _touch(self.root / "not-a-dir")
        with self.assertRaises(PlaylistError) as ctx:
            scan(path)
        self.assertIn("not a directory", str(ctx.exception))

    def test_no_matching_videos_raises(self) -> None:
        _touch(self.root / "notes.txt")
        with self.assertRaises(PlaylistError) as ctx:
            scan(self.root)
        self.assertIn("No video files found", str(ctx.exception))

    # Extensions

    def test_known_extensions_are_included(self) -> None:
        names = [f"clip{ext}" for ext in VIDEO_EXTENSIONS]
        for name in names:
            _touch(self.root / name)
        videos = scan(self.root)
        self.assertCountEqual([path.name for path in videos], names)

    def test_unknown_extension_is_ignored(self) -> None:
        _touch(self.root / "keep.mp4")
        _touch(self.root / "skip.txt")
        _touch(self.root / "skip.mp4.bak")
        videos = scan(self.root)
        self.assertEqual([path.name for path in videos], ["keep.mp4"])

    def test_extension_match_is_case_insensitive(self) -> None:
        _touch(self.root / "Clip.MP4")
        videos = scan(self.root)
        self.assertEqual([path.name for path in videos], ["Clip.MP4"])

    def test_does_not_recurse_into_subfolders(self) -> None:
        _touch(self.root / "top.mp4")
        _touch(self.root / "nested" / "hidden.mp4")
        videos = scan(self.root)
        self.assertEqual([path.name for path in videos], ["top.mp4"])
