"""Output-loopback capture, local ASR, and independent local translation."""
from __future__ import annotations
import queue
import threading
import time
from dataclasses import replace
from collections import OrderedDict
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from PySide6.QtCore import QObject, Signal
from speech_quality import SAMPLE_RATE, FRAME, Segmenter, AudioClip, decoder_options, transcript_parts
from speaker_labels import SpeakerTimeline, group_words
from live_captions import LatestSlot, CaptionUpdate


class VoiceService(QObject):
    caption = Signal(str, str, str)
    attributed_caption = Signal(str, str, str, str)
    live_caption = Signal(object)
    status = Signal(str)
    error = Signal(str)
    stopped = Signal()

    def __init__(self, timeline=None):
        super().__init__()
        self.timeline = timeline if timeline is not None else SpeakerTimeline()
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.translator_ready = threading.Event()
        self.asr_done = threading.Event()
        self.audio_q = queue.Queue(maxsize=12)
        self.text_q = queue.Queue(maxsize=24)
        self.threads = []
        self.running = False
        self.preview_audio = LatestSlot()
        self.preview_text = LatestSlot()
        self.finalized_sequence = -1
        self._finish_lock = threading.Lock()
        self._workers_remaining = 0

    def _worker_finished(self, current_stop):
        with self._finish_lock:
            self._workers_remaining -= 1
            if self._workers_remaining == 0:
                current_stop.set()
                self.running = False
                self.stopped.emit()

    def start(self, profile, dictionary):
        if self.running:
            return
        self.running = True
        self._workers_remaining = 3
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.translator_ready = threading.Event()
        self.asr_done = threading.Event()
        current_stop = self.stop_event
        self.audio_q = queue.Queue(maxsize=12)
        self.text_q = queue.Queue(maxsize=24)
        self.preview_audio = LatestSlot()
        self.preview_text = LatestSlot()
        self.finalized_sequence = -1
        self.profile, self.dictionary = dict(profile), dict(dictionary)
        self.threads = [threading.Thread(target=fn, args=(current_stop,), daemon=True, name=name)
                        for fn, name in [(self._capture, 'audio-capture'),
                                         (self._recognize, 'speech-recognition'),
                                         (self._translate, 'local-translation')]]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        self.status.emit('중지 요청됨 · 마지막 문장 처리 중')

    def _enqueue(self, target, item, kind):
        if target.full():
            try:
                target.get_nowait()
                self.status.emit(kind + ' 처리 지연 · 오래된 대기 문장 1개를 건너뜁니다. GPU/모델 설정을 확인하세요.')
            except queue.Empty:
                pass
        try:
            target.put_nowait(item)
        except queue.Full:
            self.status.emit(kind + ' 대기열 초과 · 문장이 누락되었습니다.')

    def _capture(self, current_stop):
        try:
            while not self.ready.wait(0.1):
                if current_stop.is_set():
                    return
            if current_stop.is_set():
                return
            import soundcard as sc
            from core import select_output_loopback
            mic = select_output_loopback(sc.all_microphones(include_loopback=True),
                                         self.profile.get('audio_id', ''), sc.default_speaker())
            self.status.emit(f'출력 소리 수집 중: {mic.name}')
            interval = 0.4 if self.resolved_device == 'cuda' else 1.2
            segmenter = Segmenter(self.profile.get('vad', 1), interval)
            with mic.recorder(samplerate=48000, channels=2, blocksize=2400) as recorder:
                origin = None
                while not current_stop.is_set():
                    raw = recorder.record(numframes=2400)
                    if raw is None or len(raw) == 0:
                        continue
                    if origin is None:
                        origin = time.monotonic() - len(raw) / 48000
                    mono = np.asarray(raw, dtype=np.float32)
                    if mono.ndim > 1:
                        mono = mono.mean(axis=1)
                    down = resample_poly(np.nan_to_num(mono), 1, 3).astype(np.float32)
                    for clip in segmenter.push(down):
                        clip.start += origin
                        self._enqueue(self.audio_q, clip, '음성 인식')
                    if self.profile.get('live_preview', True):
                        clip = segmenter.preview()
                        if clip is not None:
                            clip.start += origin
                            self.preview_audio.put(clip)
                if origin is not None:
                    for clip in segmenter.flush():
                        clip.start += origin
                        self._enqueue(self.audio_q, clip, '음성 인식')
        except Exception as exc:
            self.error.emit('소리 수집 오류: ' + str(exc))
            current_stop.set()
        finally:
            self._worker_finished(current_stop)

    def _load_model(self):
        from cuda_runtime import prepare_cuda
        prepare_cuda()
        import ctranslate2
        from faster_whisper import WhisperModel
        device = self.profile.get('device', 'auto')
        if device == 'auto':
            device = 'cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
        name = self.profile.get('model', 'large-v3-turbo')
        self.resolved_device = device
        bundled = Path(__file__).resolve().parent / 'models' / name
        model_ref = str(bundled) if (bundled / 'model.bin').is_file() else name
        compute = 'int8_float16' if device == 'cuda' else 'int8'
        self.status.emit(f'음성 모델 준비: {name} · {device} · {compute}')
        model = WhisperModel(model_ref, device=device, compute_type=compute,
                             cpu_threads=4, num_workers=1)
        # Run native GPU kernels before capture, so the first real utterance
        # does not pay lazy CUDA initialization and allocation costs.
        self.status.emit('음성 모델 예열 중 · 첫 자막 지연을 줄이는 중')
        warmup, _ = model.transcribe(np.zeros(SAMPLE_RATE, np.float32), language='en',
                                    beam_size=1, vad_filter=False, word_timestamps=False)
        list(warmup)
        self.status.emit(f'음성 모델 준비 완료: {name} · {device} · 정밀도 {self.profile.get("beam_size", 5)}')
        return model

    def _recognize(self, current_stop):
        try:
            model = self._load_model()
            self.ready.set()
            while not current_stop.is_set() or self._capture_alive() or not self.audio_q.empty():
                try:
                    clip = self.audio_q.get(timeout=0.03)
                except queue.Empty:
                    if current_stop.is_set():
                        continue
                    clip = self.preview_audio.take()
                    if clip is None or clip.sequence <= self.finalized_sequence:
                        continue
                options = decoder_options(self.profile)
                if not clip.final:
                    # Fast, replaceable drafts; the full utterance still uses
                    # the selected beam and precise word/speaker alignment.
                    options.update(beam_size=1, word_timestamps=False, vad_filter=False)
                    options['max_new_tokens'] = max(24, min(160, int(len(clip.audio) / SAMPLE_RATE * 24)))
                    options.pop('vad_parameters', None)
                segments, info = model.transcribe(clip.audio, **options)
                if not clip.final:
                    segments = [s for s in segments if s.avg_logprob >= -1.0 and s.no_speech_prob < 0.6]
                parts = list(transcript_parts(segments, clip.overlap))
                if clip.final:
                    self.finalized_sequence = clip.sequence
                    groups = group_words(parts, self.timeline, clip.start)
                else:
                    text = ''.join(p[0] for p in parts).strip()
                    label = self.timeline.resolve(clip.start + clip.overlap,
                                                  clip.start + len(clip.audio) / SAMPLE_RATE)
                    groups = [(label, text)] if text else []
                for index, (label, text) in enumerate(groups):
                    update = CaptionUpdate(clip.sequence, clip.revision + index, text,
                                           text if info.language == 'ko' else '',
                                           info.language, label, clip.final)
                    self.live_caption.emit(update)
                    if clip.final:
                        self._enqueue(self.text_q, update, '번역')
                    else:
                        self.preview_text.put(update)
        except Exception as exc:
            self.error.emit('음성 인식 오류: ' + str(exc) + ' · GPU·CUDA 진단 또는 CPU 설정을 확인하세요.')
            current_stop.set()
        finally:
            self.asr_done.set()
            self._worker_finished(current_stop)

    def _capture_alive(self):
        return bool(self.threads and self.threads[0].is_alive())

    def _translate(self, current_stop):
        try:
            from core import expand_terms, HOME, normalized_phrase, read_phrase_memory
            from language_packs import combine_terms, installed_for_language
            from local_translation import LocalTranslator, game_phrase_translation
            translator = LocalTranslator()
            language = self.profile.get('language', 'auto')
            source = 'en' if language == 'auto' else ('pt' if language == 'pb' else language)
            if source != 'ko' and (source, 'ko') in translator.packages:
                # Load the native translator in parallel with Whisper startup,
                # rather than delaying the first actual foreign sentence.
                translator.translate('', source, 'ko')
            self.translator_ready.set()
            phrase_memory = read_phrase_memory(HOME / 'phrase_memory.json')
            terms = {}
            translations = OrderedDict()
            while not self.asr_done.is_set() or not self.text_q.empty():
                try:
                    update = self.text_q.get(timeout=0.03)
                except queue.Empty:
                    update = self.preview_text.take()
                    if update is None or update.sequence <= self.finalized_sequence:
                        continue
                transcript, source_lang, label = update.original, update.language, update.speaker
                lang = self.profile.get('language', 'auto')
                if source_lang == 'pt' and (lang == 'pb' or (lang == 'auto' and
                        installed_for_language('pb') and not installed_for_language('pt'))):
                    source_lang = 'pb'
                if source_lang not in terms:
                    terms[source_lang] = combine_terms(self.dictionary, source_lang, HOME)
                expanded = expand_terms(transcript, terms[source_lang])
                remembered = phrase_memory.get(source_lang + ':' + normalized_phrase(transcript),
                             phrase_memory.get('auto:' + normalized_phrase(transcript)))
                context = self.profile.get('translation_context',
                          'game' if '디스코드' in self.profile.get('name', '') else 'general')
                curated = game_phrase_translation(transcript, source_lang) if context == 'game' else None
                if remembered is not None:
                    translated = remembered
                elif curated is not None:
                    translated = curated
                elif source_lang == 'ko':
                    translated = transcript
                elif (source_lang, expanded) in translations:
                    translated = translations[source_lang, expanded]
                    translations.move_to_end((source_lang, expanded))
                else:
                    try:
                        translated = translator.translate(expanded,
                                      'pt' if source_lang == 'pb' else source_lang, 'ko')
                        translations[source_lang, expanded] = translated
                        while len(translations) > 128:
                            translations.popitem(last=False)
                    except Exception as exc:
                        translated = '[번역 불가] ' + transcript
                        self.status.emit('번역 실패 (' + source_lang + '→ko): ' + str(exc)[:180])
                # Draft work is bounded to one latest item. A completed old
                # draft must never overwrite its final sentence.
                if update.final or update.sequence > self.finalized_sequence:
                    self.live_caption.emit(replace(update, translated=translated, language=source_lang, complete=True))
                if update.final:
                    self.caption.emit(transcript, translated, source_lang)
                    self.attributed_caption.emit(transcript, translated, source_lang, label)
        except Exception as exc:
            self.error.emit('번역 처리 오류: ' + str(exc))
            current_stop.set()
        finally:
            self._worker_finished(current_stop)
