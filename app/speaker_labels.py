"""Time-aligned speaker hints from Discord's official voice widget.

This is activity correlation, not per-person audio separation. Unknown/overlap
labels are deliberate: mixed audio must not be confidently blamed on one user.
"""
from __future__ import annotations
from collections import deque
from threading import RLock
import time
from urllib.parse import urlsplit, urlunsplit
import re

UNKNOWN = '화자 미확인'


def validate_widget_url(value):
    url = urlsplit(value.strip())
    if (url.scheme != 'https' or url.hostname != 'streamkit.discord.com'
            or url.username or url.password or url.port not in (None, 443)
            or not re.fullmatch(r'/overlay/voice/\d{15,22}/\d{15,22}/?', url.path)):
        raise ValueError('Discord Streamkit의 Voice Widget 주소를 붙여넣어 주세요.')
    # Force names to remain visible and show all users (including widget owner).
    return urlunsplit(('https', 'streamkit.discord.com', url.path.rstrip('/'), '', ''))


class SpeakerTimeline:
    def __init__(self):
        self._samples = deque()
        self._lock = RLock()

    def clear(self):
        with self._lock:
            self._samples.clear()

    def record(self, people, timestamp=None):
        now = time.monotonic() if timestamp is None else timestamp
        names = tuple(sorted({str(p)[:80].replace('\n', ' ') for p in people if str(p).strip()}))
        with self._lock:
            self._samples.append((now, names))
            while self._samples and self._samples[0][0] < now - 180:
                self._samples.popleft()

    def resolve(self, start, end):
        if end <= start:
            end = start + 0.02
        with self._lock:
            samples = list(self._samples)
        coverage = {}
        covered = 0.0
        for index, (stamp, names) in enumerate(samples):
            next_stamp = samples[index + 1][0] if index + 1 < len(samples) else stamp + 0.25
            # A frozen browser or disconnected widget loses attribution quickly.
            finish = min(next_stamp, stamp + 0.35)
            duration = max(0.0, min(end, finish) - max(start, stamp))
            if duration:
                covered += duration
                coverage[names] = coverage.get(names, 0.0) + duration
        total = end - start
        if covered < total * 0.6:
            return UNKNOWN
        overlaps = [(names, duration) for names, duration in coverage.items()
                    if len(names) > 1 and duration >= min(0.08, total * 0.25)]
        if overlaps:
            names = sorted({n for pair, _ in overlaps for n in pair})
            return '동시 발화 · ' + ' / '.join(names)
        singles = [(names[0], duration) for names, duration in coverage.items() if len(names) == 1]
        if not singles:
            return UNKNOWN
        name, duration = max(singles, key=lambda pair: pair[1])
        return name if duration >= total * 0.6 else UNKNOWN


def group_words(parts, timeline, clip_start):
    groups = []
    for text, start, end in parts:
        label = timeline.resolve(clip_start + start, clip_start + end)
        if groups and groups[-1][0] == label:
            groups[-1][1] += text
        else:
            groups.append([label, text])
    return [(label, text.strip()) for label, text in groups if text.strip()]
