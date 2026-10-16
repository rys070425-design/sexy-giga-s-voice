"""Readable display pacing, independent from recognition and translation speed."""
from dataclasses import dataclass
from difflib import SequenceMatcher
import time
from live_captions import DisplayOrder


@dataclass(frozen=True)
class CaptionCard:
    sequence: int
    text: str
    original: str
    label: str
    final: bool
    revision: int = 0
    part: int = 0

    @property
    def identity(self):
        return self.sequence,self.part


class ReadableCaptions:
    def __init__(self, interval=.8, previous_hold=2.8):
        self.order=DisplayOrder()
        self.interval=interval
        self.previous_hold=previous_hold
        self.current=self.previous=self.pending=None
        self.changed_at=self.previous_at=float('-inf')
        self.pending_at=0.
        self.repeats=0

    def offer(self, update, label, now=None):
        now=time.monotonic() if now is None else now
        # Never alternate between a foreign draft and its translation.
        text=update.translated or (update.original if update.language==update.target_language else '')
        if not text.strip():return False
        card=CaptionCard(update.sequence,text.strip(),update.original,label,
                         update.final and update.complete,update.revision,update.part)
        # A late final may correct the retained line without rewinding the
        # current sentence or extending the old line's reading time.
        if (self.previous and self.current and card.identity==self.previous.identity
                and card.identity<self.current.identity and card.final
                and card.revision>=self.previous.revision):
            changed=(card.text,card.label)!=(self.previous.text,self.previous.label)
            self.previous=card
            return changed
        if not self.order.accept(update):return False
        if self.pending and (self.pending.identity,self.pending.text)==(card.identity,card.text):
            self.repeats+=1
        else:
            if not self.pending or self.pending.identity!=card.identity:self.pending_at=now
            self.repeats=1
        self.pending=card
        return self.advance(now)

    def advance(self, now=None):
        now=time.monotonic() if now is None else now
        card=self.pending
        if card is None:return False
        old=self.current
        if old and (card.identity,card.text,card.label)==(old.identity,old.text,old.label):
            self.current=card;self.pending=None
            return False
        if old and now-self.changed_at<self.interval:return False
        if old and old.identity==card.identity and len(old.text)>8 and not card.final:
            similarity=SequenceMatcher(None,old.text,card.text,autojunk=False).ratio()
            if similarity<.5 and self.repeats<2 and now-self.pending_at<1.2:return False
        if old and old.identity!=card.identity and (self.previous is None or now-self.previous_at>=self.previous_hold):
            self.previous=old;self.previous_at=now
        self.current=card;self.pending=None;self.changed_at=now
        return True


def clean_caption_label(speaker, source='', override=''):
    source=override.strip() or source.strip()
    known=speaker and speaker!='화자 미확인'
    if source:
        return source+' · '+speaker if known and source=='Discord' else source
    return 'Discord · '+speaker if known else '오디오'


def wrap_measured(text, width, measure):
    """Wrap without eliding words; used to choose a two-line reading window."""
    text=' '.join(text.split())
    lines=[]
    while text:
        if measure(text)<=width:
            lines.append(text);break
        low,high=1,len(text)
        while low<high:
            middle=(low+high+1)//2
            if measure(text[:middle])<=width:low=middle
            else:high=middle-1
        cut=max(1,low)
        space=text.rfind(' ',0,cut+1)
        if space>=cut//2:cut=space
        lines.append(text[:cut].strip());text=text[cut:].lstrip()
    return lines
