from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vidsaver.fingerprint import content_id_for
from vidsaver.state import Catalog, default_db_path


class DefaultDbPathTests(unittest.TestCase):
    def test_uses_xdg_state_home_when_set(self) -> None:
        with TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "state"
            with patch.dict(os.environ, {"XDG_STATE_HOME": str(xdg)}):
                self.assertEqual(
                    default_db_path(),
                    xdg / "vidsaver" / "vidsaver.sqlite",
                )

    def test_falls_back_to_local_state(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "XDG_STATE_HOME"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                default_db_path(),
                Path.home() / ".local" / "state" / "vidsaver" / "vidsaver.sqlite",
            )


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "vidsaver.sqlite"
        self.catalog = Catalog(self.db)
        self.addCleanup(self.catalog.close)

    def test_same_bytes_same_id(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"same")
        first = self.catalog._resolve(path)
        second = self.catalog._resolve(path)
        self.assertEqual(first, second)
        self.assertEqual(first, content_id_for(path))
        self.assertEqual(len(self.catalog.rows()), 1)

    def test_rename_keeps_one_content_id(self) -> None:
        src = self.root / "old.mp4"
        src.write_bytes(b"payload")
        content_id = self.catalog._resolve(src)
        dest = self.root / "new.mp4"
        src.rename(dest)
        self.assertEqual(self.catalog._resolve(dest), content_id)
        self.assertEqual(len(self.catalog.rows()), 1)

    def test_copy_keeps_one_content_id(self) -> None:
        src = self.root / "a.mp4"
        dest = self.root / "b.mp4"
        src.write_bytes(b"payload")
        dest.write_bytes(b"payload")
        self.assertEqual(self.catalog._resolve(src), self.catalog._resolve(dest))
        self.assertEqual(len(self.catalog.rows()), 1)

    def test_different_bytes_new_row(self) -> None:
        first = self.root / "a.mp4"
        second = self.root / "b.mp4"
        first.write_bytes(b"alpha")
        second.write_bytes(b"bravo")
        self.assertNotEqual(
            self.catalog._resolve(first),
            self.catalog._resolve(second),
        )
        self.assertEqual(len(self.catalog.rows()), 2)

    def test_reencode_adds_a_new_id_and_keeps_the_old(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"original")
        old_id = self.catalog._resolve(path)
        path.write_bytes(b"re-encoded")
        new_id = self.catalog._resolve(path)
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(
            {row.content_id for row in self.catalog.rows()},
            {old_id, new_id},
        )
