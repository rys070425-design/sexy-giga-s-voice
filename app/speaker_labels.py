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
        self._epoch = 0

    def clear(self):
        with self._lock:
            self._samples.clear()
            self._epoch += 1

    @property
    def epoch(self):
        with self._lock:return self._epoch

    def exclusive(self,start,end):
        """Strict training evidence, unlike the tolerant display resolver."""
        with self._lock:coverage,covered=self._coverage(list(self._samples),start,end)
        if end<=start or covered<(end-start)*.95:return ''
        singles=[names[0] for names,duration in coverage.items() if len(names)==1 and duration>0]
        if len(set(singles))!=1 or any(len(names)>1 and duration>0 for names,duration in coverage.items()):return ''
        name=singles[0]
        return name if coverage.get((name,),0)>=(end-start)*.95 else ''

    def has_overlap(self,start,end):
        with self._lock:coverage,_=self._coverage(list(self._samples),start,end)
        return any(len(names)>1 and duration>.02 for names,duration in coverage.items())

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
        coverage,covered=self._coverage(samples,start,end)
        total = end - start
        if covered < total * 0.6:
            return UNKNOWN
        singles = [(names[0], duration) for names, duration in coverage.items() if len(names) == 1]
        overlap=sum(duration for names,duration in coverage.items() if len(names)>1)
        if singles:
            name,duration=max(singles,key=lambda pair:pair[1])
            others=sum(value for person,value in singles if person!=name)
            if duration>=total*.6 and others<min(.05,total*.1) and overlap<=min(.16,total*.25):return name
        overlaps=[names for names,duration in coverage.items() if len(names)>1 and duration>0]
        if overlaps:
            # A short word can land entirely in a 100-ms widget-ring tail.
            # Use surrounding exclusive evidence only when the same person
            # speaks on BOTH sides; never choose an arbitrary active person.
            owner=self._brief_overlap_owner(samples,start,end,overlaps)
            if owner:return owner
            return ' / '.join(sorted({name for names in coverage for name in names}))
        return UNKNOWN

    @staticmethod
    def _coverage(samples,start,end):
        coverage={};covered=0.
        for index, (stamp, names) in enumerate(samples):
            next_stamp = samples[index + 1][0] if index + 1 < len(samples) else stamp + 0.25
            # A frozen browser or disconnected widget loses attribution quickly.
            finish = min(next_stamp, stamp + 0.35)
            duration = max(0.0, min(end, finish) - max(start, stamp))
            if duration:
                covered += duration
                coverage[names] = coverage.get(names, 0.0) + duration
        return coverage,covered

    @classmethod
    def _brief_overlap_owner(cls,samples,start,end,overlaps):
        # Cover the widget sample that intersects the word, including its tail.
        context_start,context_end=start-.2,end+.2
        context,covered=cls._coverage(samples,context_start,context_end)
        if covered<(context_end-context_start)*.8:return ''
        if sum(duration for names,duration in context.items() if len(names)>1)>.16:return ''
        before,_=cls._coverage(samples,context_start,start)
        after,_=cls._coverage(samples,end,context_end)
        candidates=set.intersection(*(set(names) for names in overlaps))
        matches=[name for name in candidates
                 if before.get((name,),0)>=.1 and after.get((name,),0)>=.1
                 and context.get((name,),0)>=(context_end-context_start)*.6
                 and not any(len(names)==1 and names[0]!=name and duration>.02
                             for names,duration in context.items())]
        return matches[0] if len(matches)==1 else ''


def group_words(parts, timeline, clip_start):
    return [(label,text) for label,text,_,_ in group_timed_words(parts,timeline,clip_start)]


def group_timed_words(parts,timeline,clip_start):
    groups = []
    for text, start, end in parts:
        label = timeline.resolve(clip_start + start, clip_start + end)
        if groups and groups[-1][0] == label:
            groups[-1][1] += text
            groups[-1][3] = end
        else:
            groups.append([label, text,start,end])
    return [(label,text.strip(),start,end) for label,text,start,end in groups if text.strip()]
