"""Local speech segmentation and deterministic decoder settings."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

SAMPLE_RATE = 16000
FRAME = 320


@dataclass
class AudioClip:
    audio: np.ndarray
    start: float = 0.0  # monotonic time in the capture worker; seconds in Segmenter
    overlap: float = 0.0


class Segmenter:
    """Keep short calls, prefer pauses, and retain context across forced splits."""
    def __init__(self, level=1):
        import webrtcvad
        self.vad = webrtcvad.Vad(int(level))
        self.pending = np.empty(0, np.float32)
        self.pre, self.clip = [], []
        self.silence = self.voiced_frames = self.offset = 0
        self.speaking = False
        self.clip_start = 0
        self.overlap_frames = 0

    def _complete(self, forced=False):
        result = None
        new_frames = len(self.clip) - self.overlap_frames
        if self.voiced_frames >= 6 and new_frames >= 6:
            result = AudioClip(np.concatenate(self.clip), self.clip_start / SAMPLE_RATE,
                               self.overlap_frames * FRAME / SAMPLE_RATE)
        if forced:
            self.clip = self.clip[-30:]  # 600 ms context for a cut word
            self.clip_start = self.offset - len(self.clip) * FRAME
            self.overlap_frames = len(self.clip)
            self.speaking = True
        else:
            self.pre = self.clip[-12:]
            self.clip = []
            self.overlap_frames = 0
            self.speaking = False
        self.silence = self.voiced_frames = 0
        return result

    def push(self, audio):
        self.pending = np.concatenate((self.pending, np.asarray(audio, dtype=np.float32)))
        completed = []
        while len(self.pending) >= FRAME:
            frame, self.pending = self.pending[:FRAME].copy(), self.pending[FRAME:]
            self.offset += FRAME
            pcm = (np.clip(frame, -1, 1) * 32767).astype('<i2').tobytes()
            voiced = self.vad.is_speech(pcm, SAMPLE_RATE)
            if not self.speaking:
                self.pre = (self.pre + [frame])[-12:]
                if not voiced:
                    continue
                self.clip, self.pre = self.pre, []
                self.clip_start = self.offset - len(self.clip) * FRAME
                self.speaking = True
                self.voiced_frames = 1
            else:
                self.clip.append(frame)
                self.voiced_frames += int(voiced)
                self.silence = 0 if voiced else self.silence + 1
            # 480 ms endpoint; long turns can end on a 160 ms natural pause.
            pause = self.silence >= 24 or (len(self.clip) >= 150 and self.silence >= 8)
            forced = len(self.clip) >= 400 and not pause
            if pause or forced:
                clip = self._complete(forced)
                if clip is not None:
                    completed.append(clip)
        return completed

    def flush(self):
        """Preserve a last short phrase on an orderly stop."""
        if not self.clip:
            return []
        clip = self._complete()
        return [clip] if clip is not None else []


def decoder_options(profile):
    options = dict(beam_size=min(5, max(1, int(profile.get('beam_size', 5)))),
                   condition_on_previous_text=False, temperature=0.0,
                   word_timestamps=True, vad_filter=True,
                   vad_parameters=dict(threshold=0.35, min_speech_duration_ms=100,
                                       min_silence_duration_ms=250, speech_pad_ms=200))
    language = profile.get('language', 'auto')
    if language != 'auto':
        options['language'] = 'pt' if language == 'pb' else language
    # Never prompt with previous transcripts or every glossary term: both can
    # make quiet/background audio produce invented game vocabulary.
    return options


def transcript_parts(segments, overlap=0.0):
    """Filter unlikely silence and remove only the *audio* overlap, not repeats."""
    for segment in segments:
        if (segment.no_speech_prob > 0.6 and segment.avg_logprob < -1.0):
            continue
        words = getattr(segment, 'words', None)
        if words:
            for word in words:
                if word.end > overlap + 0.04:
                    yield word.word, word.start, word.end
        elif segment.end > overlap + 0.04:
            yield segment.text, max(segment.start, overlap), segment.end
