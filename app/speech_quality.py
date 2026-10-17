"""Local speech segmentation and deterministic decoder settings."""
from __future__ import annotations
from dataclasses import dataclass
import re
import numpy as np

SAMPLE_RATE = 16000
FRAME = 320


class SpeechPresence:
    """Check actual speech before decoding either drafts or final clips.

    WebRTC remains the cheap capture segmenter. Silero verifies its candidates
    without trimming their audio or moving word/speaker timestamps.
    """
    def __init__(self):
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        self.detect = get_speech_timestamps
        self.options = VadOptions(threshold=.5, min_speech_duration_ms=100,
                                  min_silence_duration_ms=250, speech_pad_ms=0)
        self.speech_seconds = 0.

    def warmup(self):
        self(np.zeros(SAMPLE_RATE // 2, np.float32))

    def __call__(self, audio):
        spans=self.detect(audio, self.options)
        self.speech_seconds=sum(span['end']-span['start'] for span in spans)/SAMPLE_RATE
        return bool(spans)


class DraftStability:
    """Very short fragments wait for their final; longer first drafts do not.

    This is based on text length, not a list of forbidden phrases. A real
    repeated acknowledgement and real short calls remain valid final speech.
    """
    def accept(self, clip, text):
        normalized = ' '.join(re.findall(r'\w+', text.casefold()))
        if not normalized:
            return False
        if clip.final:
            return True
        short = len(normalized.replace(' ', '')) <= 12 and len(normalized.split()) <= 2
        return not short


def ambiguous_fragment(segments, language_probability, speech_seconds):
    """Reject a weak two-word guess from a tiny acoustic fragment.

    All three independent uncertainties must coincide. Single-word calls,
    longer speech, and confident short phrases are unaffected. No phrase list.
    """
    if speech_seconds>=.3 or language_probability>=.75:return False
    words=[word for segment in segments for word in (getattr(segment,'words',None) or [])
           if re.search(r'\w',word.word)]
    if len(words)!=2:return False
    content=max(words,key=lambda word:len(re.sub(r'\W','',word.word)))
    return len(re.sub(r'\W','',content.word))>=3 and content.probability<.5


@dataclass
class AudioClip:
    audio: np.ndarray
    start: float = 0.0  # monotonic time in the capture worker; seconds in Segmenter
    overlap: float = 0.0
    sequence: int = 0
    revision: int = 0
    final: bool = True
    speaker_epoch: int = -1


class Segmenter:
    """Keep short calls, prefer pauses, and retain context across forced splits."""
    def __init__(self, level=1, preview_interval=0.4, preserve_context=False):
        import webrtcvad
        self.vad = webrtcvad.Vad(int(level))
        self.pending = np.empty(0, np.float32)
        self.pre, self.clip = [], []
        self.silence = self.voiced_frames = self.offset = 0
        self.speaking = False
        self.clip_start = 0
        self.overlap_frames = 0
        self.sequence = 0
        self.preview_interval = int(preview_interval * SAMPLE_RATE / FRAME)
        self.last_preview = 0
        self.pause_frames,self.long_pause_frames=(40,20) if preserve_context else (24,8)
        self.max_frames=500 if preserve_context else 400

    def _complete(self, forced=False):
        result = None
        new_frames = len(self.clip) - self.overlap_frames
        if self.voiced_frames >= 6 and new_frames >= 6:
            result = AudioClip(np.concatenate(self.clip), self.clip_start / SAMPLE_RATE,
                               self.overlap_frames * FRAME / SAMPLE_RATE,
                               self.sequence, len(self.clip), True)
        self.sequence += 1
        self.last_preview = 0
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
            # A preview keeps continuous speech visible without cutting its
            # context. General conversation retains up to 10 s; game calls
            # keep their 8 s limit. Draft cadence and pause rules are unchanged.
            pause = self.silence >= self.pause_frames or (len(self.clip) >= 150 and self.silence >= self.long_pause_frames)
            forced = len(self.clip) >= self.max_frames and not pause
            if pause or forced:
                clip = self._complete(forced)
                if clip is not None:
                    completed.append(clip)
        return completed

    def preview(self):
        """Replaceable snapshot; never consumes or cuts the final utterance."""
        fresh = len(self.clip) - self.overlap_frames
        if (not self.speaking or self.silence >= 8 or self.voiced_frames < 12 or
                fresh < 25 or fresh - self.last_preview < self.preview_interval):
            return None
        self.last_preview = fresh
        return AudioClip(np.concatenate(self.clip), self.clip_start / SAMPLE_RATE,
                         self.overlap_frames * FRAME / SAMPLE_RATE,
                         self.sequence, len(self.clip), False)

    def flush(self):
        """Preserve a last short phrase on an orderly stop."""
        if not self.clip:
            return []
        clip = self._complete()
        return [clip] if clip is not None else []


def make_segmenter(profile,preview_interval=.4):
    context=profile.get('translation_context','game' if '디스코드' in profile.get('name','') else 'general')
    return Segmenter(profile.get('vad',1),preview_interval,preserve_context=context=='general')


def decoder_options(profile):
    options = dict(beam_size=min(5, max(1, int(profile.get('beam_size', 5)))),
                   condition_on_previous_text=False, temperature=0.0,
                   word_timestamps=True, vad_filter=True,
                   vad_parameters=dict(threshold=0.35, min_speech_duration_ms=100,
                                       min_silence_duration_ms=250, speech_pad_ms=200))
    language = profile.get('language', 'auto')
    if language != 'auto':
        options['language'] = 'pt' if language == 'pb' else language
    # Only explicit user-supplied names/terms; never feed previous transcripts
    # or the entire translation glossary back into recognition.
    hotwords = ' '.join(str(profile.get('asr_hotwords', '')).split())[:200]
    if hotwords:
        options['hotwords'] = hotwords
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
