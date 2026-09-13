from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vidsaver.config import ConfigError, load_config


def _write_toml(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class LoadConfigFileTests(unittest.TestCase):
    """Temp-dir reads: TOML parsing, ``--config``, ``--dir``, and search order."""

    def setUp(self) -> None:
        # Temporary directory, deleted after the test. chdir into an empty
        # cwd so ./config.toml is not the real project file. Restore cwd on
        # cleanup (Path.cwd() is captured here, before the chdir).
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        self.cwd_dir = self.root / "cwd"
        self.cwd_dir.mkdir()
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(self.cwd_dir)
        # Point search paths at the temp dir so the real project config.toml
        # is never picked up when --config is omitted.
        self.project_config = self.root / "project" / "config.toml"
        self.user_config = self.root / "user" / "config.toml"
        for name, path in (
            ("PROJECT_CONFIG_PATH", self.project_config),
            ("USER_CONFIG_PATH", self.user_config),
        ):
            search_patch = patch(f"vidsaver.config.{name}", path)
            search_patch.start()
            self.addCleanup(search_patch.stop)

    # --config (explicit path)

    def test_explicit_config_loads_video_dir(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/videos/a"\n')
        config = load_config(config_path=path)
        self.assertEqual(config.video_dir, Path("/videos/a"))
        self.assertEqual(config.config_path, path)

    def test_explicit_config_missing_raises(self) -> None:
        missing = self.root / "missing.toml"
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=missing)
        self.assertEqual(str(ctx.exception), f"Config file not found: {missing}")

    def test_explicit_config_ignores_search_paths(self) -> None:
        _write_toml(self.cwd_dir / "config.toml", 'video_dir = "/from-cwd"\n')
        explicit = _write_toml(self.root / "explicit.toml", 'video_dir = "/from-explicit"\n')
        config = load_config(config_path=explicit)
        self.assertEqual(config.video_dir, Path("/from-explicit"))

    # --dir

    def test_dir_overrides_file(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/from-file"\n')
        config = load_config(config_path=path, video_dir=Path("/from-cli"))
        self.assertEqual(config.video_dir, Path("/from-cli"))
        self.assertEqual(config.config_path, path)

    def test_dir_works_without_any_config_file(self) -> None:
        config = load_config(video_dir=Path("/only-cli"))
        self.assertEqual(config.video_dir, Path("/only-cli"))
        self.assertEqual(config.screens, "primary")
        self.assertIs(config.mute, True)
        self.assertIs(config.skip_ends, True)
        self.assertEqual(config.rotate_minutes, 15)
        self.assertIsNone(config.config_path)

    # screens

    def test_omitted_screens_defaults_to_primary(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/videos/a"\n')
        config = load_config(config_path=path)
        self.assertEqual(config.screens, "primary")

    def test_screens_primary_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nscreens = "primary"\n',
        )
        config = load_config(config_path=path)
        self.assertEqual(config.screens, "primary")

    def test_screens_all_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nscreens = "all"\n',
        )
        config = load_config(config_path=path)
        self.assertEqual(config.screens, "all")

    def test_screens_invalid_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nscreens = "current"\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f'screens in {path} must be "primary" or "all", not {"current"!r}.',
        )

    def test_screens_empty_string_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nscreens = ""\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f'screens in {path} must be "primary" or "all", not {""!r}.',
        )

    # mute

    def test_omitted_mute_defaults_to_true(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/videos/a"\n')
        config = load_config(config_path=path)
        self.assertIs(config.mute, True)

    def test_mute_true_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nmute = true\n',
        )
        config = load_config(config_path=path)
        self.assertIs(config.mute, True)

    def test_mute_false_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nmute = false\n',
        )
        config = load_config(config_path=path)
        self.assertIs(config.mute, False)

    def test_mute_invalid_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nmute = "yes"\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f"mute in {path} must be true or false, not {'yes'!r}.",
        )

    # skip_ends

    def test_omitted_skip_ends_defaults_to_true(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/videos/a"\n')
        config = load_config(config_path=path)
        self.assertIs(config.skip_ends, True)

    def test_skip_ends_true_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nskip_ends = true\n',
        )
        config = load_config(config_path=path)
        self.assertIs(config.skip_ends, True)

    def test_skip_ends_false_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nskip_ends = false\n',
        )
        config = load_config(config_path=path)
        self.assertIs(config.skip_ends, False)

    def test_skip_ends_invalid_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nskip_ends = "yes"\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f"skip_ends in {path} must be true or false, not {'yes'!r}.",
        )

    # rotate_minutes

    def test_omitted_rotate_minutes_defaults_to_15(self) -> None:
        path = _write_toml(self.root / "explicit.toml", 'video_dir = "/videos/a"\n')
        config = load_config(config_path=path)
        self.assertEqual(config.rotate_minutes, 15)

    def test_rotate_minutes_loads(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nrotate_minutes = 1.5\n',
        )
        config = load_config(config_path=path)
        self.assertEqual(config.rotate_minutes, 1.5)

    def test_rotate_minutes_zero_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nrotate_minutes = 0\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f"rotate_minutes in {path} must be greater than 0, not 0.",
        )

    def test_rotate_minutes_negative_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nrotate_minutes = -1\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f"rotate_minutes in {path} must be greater than 0, not -1.",
        )

    def test_rotate_minutes_invalid_raises(self) -> None:
        path = _write_toml(
            self.root / "explicit.toml",
            'video_dir = "/videos/a"\nrotate_minutes = "soon"\n',
        )
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertEqual(
            str(ctx.exception),
            f"rotate_minutes in {path} must be a number greater than 0, "
            f"not {'soon'!r}.",
        )

    # Missing video_dir, blank string, or invalid TOML

    def test_no_dir_and_no_config_raises(self) -> None:
        with self.assertRaises(ConfigError) as ctx:
            load_config()
        self.assertTrue(
            str(ctx.exception).startswith("No video folder set"),
            msg=str(ctx.exception),
        )

    def test_video_dir_empty_string_raises(self) -> None:
        path = _write_toml(self.root / "blank.toml", 'video_dir = ""\n')
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertTrue(
            str(ctx.exception).startswith(f"video_dir in {path} is an empty string"),
            msg=str(ctx.exception),
        )

    def test_invalid_toml_raises(self) -> None:
        path = _write_toml(self.root / "bad.toml", "video_dir =\n")
        with self.assertRaises(ConfigError) as ctx:
            load_config(config_path=path)
        self.assertTrue(
            str(ctx.exception).startswith(f"Invalid TOML in {path}: "),
            msg=str(ctx.exception),
        )

    # ~ expansion

    def test_tilde_in_video_dir_is_expanded(self) -> None:
        path = _write_toml(self.root / "home.toml", 'video_dir = "~/videos"\n')
        config = load_config(config_path=path)
        self.assertEqual(config.video_dir, Path.home() / "videos")

    # Search order (cwd, then project, then user)

    def test_cwd_config_wins_over_project_and_user(self) -> None:
        _write_toml(self.cwd_dir / "config.toml", 'video_dir = "/from-cwd"\n')
        _write_toml(self.project_config, 'video_dir = "/from-project"\n')
        _write_toml(self.user_config, 'video_dir = "/from-user"\n')
        config = load_config()
        self.assertEqual(config.video_dir, Path("/from-cwd"))
        self.assertEqual(config.config_path, self.cwd_dir / "config.toml")

    def test_project_config_used_when_cwd_missing(self) -> None:
        _write_toml(self.project_config, 'video_dir = "/from-project"\n')
        _write_toml(self.user_config, 'video_dir = "/from-user"\n')
        config = load_config()
        self.assertEqual(config.video_dir, Path("/from-project"))
        self.assertEqual(config.config_path, self.project_config)

    def test_user_config_used_when_local_missing(self) -> None:
        _write_toml(self.user_config, 'video_dir = "/from-user"\n')
        config = load_config()
        self.assertEqual(config.video_dir, Path("/from-user"))
        self.assertEqual(config.config_path, self.user_config)


if __name__ == "__main__":
    unittest.main()
