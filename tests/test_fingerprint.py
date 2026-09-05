from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vidsaver.fingerprint import SAMPLE_BYTES, FingerprintError, content_id_for


class ContentIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)

    def test_same_bytes_same_id(self) -> None:
        a = self.root / "a.mp4"
        b = self.root / "b.mp4"
        a.write_bytes(b"hello")
        b.write_bytes(b"hello")
        self.assertEqual(content_id_for(a), content_id_for(b))

    def test_different_bytes_different_id(self) -> None:
        a = self.root / "a.mp4"
        b = self.root / "b.mp4"
        a.write_bytes(b"hello")
        b.write_bytes(b"world")
        self.assertNotEqual(content_id_for(a), content_id_for(b))

    def test_id_includes_size(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"x" * 20)
        self.assertTrue(content_id_for(path).startswith("20:"))

    def test_head_and_tail_are_both_sampled(self) -> None:
        a = self.root / "a.mp4"
        b = self.root / "b.mp4"
        size = SAMPLE_BYTES * 3
        a.write_bytes(b"A" * size)
        body = bytearray(b"A" * size)
        body[-1] = ord("B")
        b.write_bytes(bytes(body))
        self.assertNotEqual(content_id_for(a), content_id_for(b))

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FingerprintError):
            content_id_for(self.root / "missing.mp4")
