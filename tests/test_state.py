from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vidsaver.fingerprint import content_id_for
from vidsaver.state import Catalog, Offsets, default_db_path


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

    def test_sync_maps_resolved_paths(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"sync-me")
        ids = self.catalog.sync([path])
        self.assertEqual(ids[path.resolve()], content_id_for(path))

    def test_offset_defaults_to_zero_and_round_trips(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"offset")
        content_id = self.catalog._resolve(path)
        self.assertEqual(self.catalog.get_offset(content_id), 0.0)
        self.assertIsNone(self.catalog.rows()[0].playback_at)
        self.catalog.set_offset(content_id, 12.5)
        self.assertEqual(self.catalog.get_offset(content_id), 12.5)
        row = self.catalog.rows()[0]
        self.assertEqual(row.offset_sec, 12.5)
        self.assertIsNotNone(row.playback_at)

    def test_reencode_does_not_copy_offset_to_new_id(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"original")
        old_id = self.catalog._resolve(path)
        self.catalog.set_offset(old_id, 9.0)
        path.write_bytes(b"re-encoded")
        new_id = self.catalog._resolve(path)
        self.assertEqual(self.catalog.get_offset(old_id), 9.0)
        self.assertEqual(self.catalog.get_offset(new_id), 0.0)

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

    def test_stats_start_at_zero_and_accumulate(self) -> None:
        path = self.root / "clip.mp4"
        path.write_bytes(b"stats")
        content_id = self.catalog._resolve(path)
        stats = self.catalog.get_stats(content_id)
        assert stats is not None
        self.assertEqual(stats.clip_count, 0)
        self.assertEqual(stats.watched_sec, 0.0)
        self.assertIsNone(self.catalog.rows()[0].duration_sec)
        self.catalog.add_stats(content_id, 15.0, clips=1)
        self.catalog.add_stats(content_id, 10.0, clips=0)
        self.catalog.set_duration(content_id, 46.0)
        stats = self.catalog.get_stats(content_id)
        assert stats is not None
        self.assertEqual(stats.clip_count, 1)
        self.assertEqual(stats.watched_sec, 25.0)
        self.assertEqual(self.catalog.rows()[0].duration_sec, 46.0)


class OffsetsTests(unittest.TestCase):
    def test_sync_loads_existing_offset(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "clip.mp4"
            path.write_bytes(b"offset")
            db = root / "vidsaver.sqlite"
            with Catalog(db) as catalog:
                offsets = Offsets(catalog)
                offsets.sync([path])
                offsets.set_offset(path, 12.5)
            with Catalog(db) as catalog:
                offsets = Offsets(catalog)
                offsets.sync([path])
                self.assertEqual(offsets.get_offset(path), 12.5)

    def test_with_catalog_writes_db(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "clip.mp4"
            path.write_bytes(b"offset")
            with Catalog(root / "vidsaver.sqlite") as catalog:
                offsets = Offsets(catalog)
                offsets.sync([path])
                offsets.set_offset(path, 12.5)
                self.assertEqual(offsets.get_offset(path), 12.5)
                self.assertEqual(catalog.rows()[0].offset_sec, 12.5)

    def test_set_offset_tallies_a_new_video_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a.mp4"
            second = root / "b.mp4"
            first.write_bytes(b"aaa")
            second.write_bytes(b"bbb")
            with Catalog(root / "vidsaver.sqlite") as catalog:
                offsets = Offsets(catalog)
                offsets.sync([first, second])
                offsets.set_duration(first, 46.0)
                offsets.set_offset(first, 10.0)
                offsets.set_offset(first, 25.0)
                offsets.set_duration(second, 20.0)
                offsets.set_offset(second, 8.0)
                a_stats = catalog.get_stats(content_id_for(first))
                b_stats = catalog.get_stats(content_id_for(second))
                assert a_stats is not None and b_stats is not None
                self.assertEqual(a_stats.clip_count, 1)
                self.assertEqual(a_stats.watched_sec, 25.0)
                self.assertEqual(
                    next(
                        row.duration_sec
                        for row in catalog.rows()
                        if row.content_id == content_id_for(first)
                    ),
                    46.0,
                )
                self.assertEqual(b_stats.clip_count, 1)
                self.assertEqual(b_stats.watched_sec, 8.0)

    def test_unknown_path_does_not_write_db(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "clip.mp4"
            path.write_bytes(b"offset")
            with Catalog(root / "vidsaver.sqlite") as catalog:
                offsets = Offsets(catalog)
                offsets.sync([path])
                offsets.set_offset(root / "missing.mp4", 9.0)
                self.assertEqual(catalog.rows()[0].offset_sec, 0.0)
                self.assertEqual(offsets.get_offset(root / "missing.mp4"), 0.0)
