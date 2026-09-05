from __future__ import annotations

import random
import unittest
from collections import deque
from pathlib import Path

from vidsaver.shuffle import get_shuffled_playlist


def _library(n: int) -> list[Path]:
    return [Path(f"/videos/{i}.mp4") for i in range(n)]


class ShuffledPlaylistTests(unittest.TestCase):
    def test_empty_library_returns_empty(self) -> None:
        self.assertEqual(get_shuffled_playlist([]), [])

    def test_length_is_passes_times_library(self) -> None:
        videos = _library(3)
        self.assertEqual(len(get_shuffled_playlist(videos, passes=5, rng=random.Random(1))), 15)

    def test_each_pick_is_legal_or_the_cooldown_exception(self) -> None:
        cooldown = 2
        for n in (1, 2, 3, 4, 5):
            videos = _library(n)
            for seed in (0, 1, 7, 99):
                with self.subTest(n=n, seed=seed):
                    seq = get_shuffled_playlist(videos, passes=8, rng=random.Random(seed))
                    remaining: list[Path] = []
                    recent: deque[Path] = deque(maxlen=cooldown)
                    for index, pick in enumerate(seq):
                        if not remaining:
                            remaining = list(videos)
                        candidates = [path for path in remaining if path not in recent]
                        if not candidates:
                            candidates = list(remaining)
                        self.assertIn(pick, candidates, msg=f"index={index}")
                        remaining.remove(pick)
                        recent.append(pick)


if __name__ == "__main__":
    unittest.main()
