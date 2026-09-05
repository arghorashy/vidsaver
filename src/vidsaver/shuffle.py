"""Shuffle a folder of videos for screensaver playback.

Intent: each pass shows every file once, in random order, so nothing
repeats until the whole folder has played. Across passes, the last two
files are held back so the clip that just ended is not the next one
(unless the folder is so small there is no other choice).

mpv takes a static playlist and loops it. This module cannot reshuffle
while mpv is running, so ``get_shuffled_playlist`` precomputes several passes
and hands mpv that long list before it starts.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Sequence
from pathlib import Path

COOLDOWN = 2
# Full-folder shuffles packed into the playlist mpv receives at launch.
PASSES = 32


class _ShuffleBag:
    """Random order without replacement, plus a short cooldown after a pass."""

    def __init__(
        self,
        videos: Sequence[Path],
        *,
        cooldown: int = COOLDOWN,
        rng: random.Random | None = None,
    ) -> None:
        self._all = list(videos)
        self._queue: deque[Path] = deque()
        self._recent: deque[Path] = deque(maxlen=cooldown)
        self._rng = random.Random() if rng is None else rng

    def next(self) -> Path:
        if not self._queue:
            self._refill()
        pick = self._queue.popleft()
        self._recent.append(pick)
        return pick

    def _refill(self) -> None:
        eligible = [path for path in self._all if path not in self._recent]
        if not eligible:
            order = list(self._all)
            self._rng.shuffle(order)
            self._queue = deque(order)
            return
        self._rng.shuffle(eligible)
        # Last two play after the rest, older first, so the video that
        # just ended is not the next one (needed when there are 3 files).
        eligible.extend(self._recent)
        self._queue = deque(eligible)


def get_shuffled_playlist(
    videos: Sequence[Path],
    *,
    passes: int = PASSES,
    rng: random.Random | None = None,
) -> list[Path]:
    """Build the playlist mpv will play, before mpv starts.

    Draws ``len(videos) * passes`` items (default: 32 passes). Each pass
    is one full trip through the folder. mpv then loops this frozen list;
    it does not call back for a new shuffle.
    """
    if not videos:
        return []
    bag = _ShuffleBag(videos, rng=rng)
    return [bag.next() for _ in range(len(videos) * passes)]
