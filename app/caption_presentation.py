"""Readable display pacing, independent from recognition and translation speed."""
from dataclasses import dataclass
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
    speaker: str = ''

    @property
    def display_text(self):
        return self.speaker+': '+self.text if self.speaker else self.text

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
        self.suppressed_revisions={}

    def is_suppressed(self,update):
        return update.revision<=self.suppressed_revisions.get(update.sequence,-1)

    def offer(self, update, label, now=None):
        now=time.monotonic() if now is None else now
        if update.retracted:return self.retract(update)
        if update.suppressed:return self.suppress(update)
        if self.is_suppressed(update):return False
        # Never alternate between a foreign draft and its translation.
        text=update.translated or (update.original if update.language==update.target_language else '')
        if not text.strip():return False
        card=CaptionCard(update.sequence,text.strip(),update.original,label,
                         update.final and update.complete,update.revision,update.part,
                         update.speaker if update.source=='Discord' and label=='Discord · '+update.speaker else '')
        # A late final may correct the retained line without rewinding the
        # current sentence or extending the old line's reading time.
        if (self.previous and self.current and card.identity==self.previous.identity
                and card.identity<self.current.identity and card.final
                and card.revision>=self.previous.revision):
            changed=(card.text,card.label)!=(self.previous.text,self.previous.label)
            self.previous=card
            return changed
        if not self.order.accept(update):return False
        self.pending=card
        return self.advance(now)

    def retract(self, update):
        # Reject delayed translations of this discarded audio, while retaining
        # unrelated real sentences and allowing a later utterance to repeat it.
        self.suppressed_revisions[update.sequence]=max(update.revision,self.suppressed_revisions.get(update.sequence,-1))
        if len(self.suppressed_revisions)>128:
            del self.suppressed_revisions[min(self.suppressed_revisions)]
        self.order.accept(update)
        changed=False
        if self.pending and self.pending.sequence==update.sequence:self.pending=None
        if self.previous and self.previous.sequence==update.sequence:
            self.previous=None;changed=True
        if self.current and self.current.sequence==update.sequence:
            self.current,self.previous=self.previous,None;changed=True
        return changed

    def suppress(self,update):
        self.suppressed_revisions[update.sequence]=max(update.revision,self.suppressed_revisions.get(update.sequence,-1))
        if len(self.suppressed_revisions)>128:
            del self.suppressed_revisions[min(self.suppressed_revisions)]
        if not self.order.accept(update):return False
        changed=bool(self.current or self.previous or self.pending)
        self.current=self.previous=self.pending=None
        return changed

    def advance(self, now=None):
        now=time.monotonic() if now is None else now
        card=self.pending
        if card is None:return False
        old=self.current
        if old and (card.identity,card.text,card.label)==(old.identity,old.text,old.label):
            self.current=card;self.pending=None
            return False
        same_sentence=old and old.identity==card.identity
        # Correct an existing sentence as soon as its final arrives. During
        # speech, only append to the visible wording; never repeatedly replace
        # the beginning as an incremental translation changes its grammar.
        if old and now-self.changed_at<self.interval and not (same_sentence and card.final):return False
        if same_sentence and not card.final:
            stem=old.text.rstrip(' .,!?:;…。，！？：；')
            if not stem or not card.text.startswith(stem):return False
        if old and old.identity!=card.identity and (self.previous is None or now-self.previous_at>=self.previous_hold):
            self.previous=old;self.previous_at=now
        self.current=card;self.pending=None;self.changed_at=now
        return True


def clean_caption_label(speaker, source='', override=''):
    source=override.strip() or source.strip()
    known=speaker and speaker!='화자 미확인'
    if source:
        return source+' · '+speaker if known and source=='Discord' else source
    return ''


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
