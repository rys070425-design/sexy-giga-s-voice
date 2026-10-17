"""Ordered live captions and bounded, replaceable preview work."""
from dataclasses import dataclass
import threading


class LatestSlot:
    def __init__(self):
        self.lock = threading.Lock()
        self.item = None

    def put(self, value):
        with self.lock:
            self.item = value

    def take(self):
        with self.lock:
            result, self.item = self.item, None
            return result


@dataclass(frozen=True)
class CaptionUpdate:
    sequence: int
    revision: int
    original: str
    translated: str
    language: str
    speaker: str
    final: bool = False
    complete: bool = False
    source: str = ''
    target_language: str = 'ko'
    part: int = 0
    suppressed: bool = False
    speaker_epoch: int = -1
    retracted: bool = False


class DisplayOrder:
    """Do not let a slow translation replace more recent speech."""
    def __init__(self):
        self.key = (-1, -1, -1)

    def accept(self, update):
        key = (update.sequence, update.revision, 2 if update.suppressed or update.retracted else int(bool(update.translated)))
        if key < self.key:
            return False
        self.key = key
        return True
