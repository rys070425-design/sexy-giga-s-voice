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
    message = 'Discord 통화방의 채널 링크 또는 공식 Streamkit Voice Widget 주소를 붙여넣어 주세요.'
    try:
        url = urlsplit(value.strip())
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
            raise ValueError(message)
        if url.hostname in ('discord.com', 'canary.discord.com', 'ptb.discord.com', 'discordapp.com'):
            match = re.fullmatch(r'/channels/(\d{15,22})/(\d{15,22})/?', url.path)
            if not match:
                raise ValueError(message + ' 개인 메시지나 초대 링크는 사용할 수 없습니다.')
            return 'https://streamkit.discord.com/overlay/voice/' + '/'.join(match.groups())
        if (url.hostname != 'streamkit.discord.com' or
                not re.fullmatch(r'/overlay/voice/\d{15,22}/\d{15,22}/?', url.path)):
            raise ValueError(message)
    except ValueError as exc:
        if str(exc).startswith('Discord '):
            raise
        raise ValueError(message) from None
    # Force names to remain visible and show all users (including widget owner).
    return urlunsplit(('https', 'streamkit.discord.com', url.path.rstrip('/'), '', ''))


def widget_connection_status(value, setup=False):
    """Return (channel_ready, explanation) without mistaking an open socket for approval."""
    if not isinstance(value, dict) or not value.get('connected'):
        return False, 'Discord PC 앱 연결 대기 · PC 앱을 켜고 공식 연결 화면에서 승인해 주세요.'
    rpc = value.get('rpc')
    if not isinstance(rpc, dict):
        return False, '연결 상태 확인 중 · 공식 연결 화면을 다시 열어 주세요.'
    error = rpc.get('error')
    if error:
        code = rpc.get('code')
        detail = f' (코드 {code})' if isinstance(code, int) else ''
        if error in ('AUTHORIZE', 'AUTHENTICATE'):
            return False, 'Discord 연결 승인 실패' + detail + ' · Discord의 권한 승인 창을 확인해 주세요.'
        return False, '통화방 정보를 읽지 못했습니다' + detail + ' · 현재 참여한 음성 채널의 링크인지 확인해 주세요.'
    if not rpc.get('authorized'):
        return False, 'Discord PC 앱 접속됨 · 아직 연결 승인이 완료되지 않았습니다.'
    if setup:
        return False, 'Discord 연결 승인 완료 · 통화방의 채널 링크를 붙여넣고 닉네임 연결 시작을 누르세요.'
    if not rpc.get('channel'):
        return False, 'Discord 연결 승인 완료 · 통화방 정보를 불러오는 중입니다.'
    return True, ''


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
