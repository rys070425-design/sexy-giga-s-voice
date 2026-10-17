"""Conservative, local Discord nickname assistance. Session RAM only.

This verifies an enrolled voice; it does not separate overlapping audio or
discover people's names. Uncertain matches deliberately return no nickname.
"""
from collections import OrderedDict,deque
from pathlib import Path
from threading import RLock
import queue
import numpy as np
from speaker_labels import UNKNOWN

MODEL_NAME='3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx'
MODEL_SHA256='aa3cfc16963a10586a9393f5035d6d6b57e98d358b347f80c2a30bf4f00ceba2'
MODEL_BYTES=28281164
MODEL_URL='https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/'+MODEL_NAME
MODEL_PATH=Path(__file__).resolve().parent/'models'/'speaker'/MODEL_NAME


class VoiceProfiles:
    """Bounded, conservative cosine matches; never persist embeddings."""
    def __init__(self):self.entries=OrderedDict()

    def clear(self):self.entries.clear()

    def learn(self,name,vector,start,end):
        if not name or name==UNKNOWN or not np.isfinite(vector).all():return
        vector=np.asarray(vector,dtype=np.float32);norm=np.linalg.norm(vector)
        if norm<1e-6:return
        vector=vector/norm
        items=self.entries.setdefault(name,deque(maxlen=4))
        # Repeated/overlapping snapshots do not count as independent evidence.
        if items and start<items[-1][2]:return
        if items and max(float(vector@v) for v,_,_ in items)<.55:return
        items.append((vector,start,end));self.entries.move_to_end(name)
        while len(self.entries)>32:self.entries.popitem(last=False)

    def identify(self,vector,minimum=.70):
        candidates=[];vector=np.asarray(vector,dtype=np.float32)
        norm=np.linalg.norm(vector)
        if norm<1e-6 or not np.isfinite(norm):return ''
        vector=vector/norm
        for name,items in self.entries.items():
            if len(items)<2:continue
            centroid=np.mean([v for v,_,_ in items],axis=0);centroid/=max(1e-6,np.linalg.norm(centroid))
            candidates.append((float(vector@centroid),name))
        # One enrolment cannot distinguish that voice from everybody else.
        candidates.sort(reverse=True)
        if len(candidates)<2:return ''
        best,name=candidates[0]
        return name if best>=minimum and best-candidates[1][0]>=.18 else ''


class VoiceIdentity:
    def __init__(self,timeline,model_path=MODEL_PATH,extractor=None):
        self.timeline=timeline;self.model_path=Path(model_path);self.extractor=extractor
        self.pending=queue.Queue(maxsize=2);self.profiles=VoiceProfiles()
        self.results=OrderedDict();self.lock=RLock();self.epoch=timeline.epoch

    def _sync(self):
        epoch=self.timeline.epoch
        if epoch!=self.epoch:
            self.profiles.clear();self.results.clear();self.epoch=epoch
        return epoch

    def submit(self,key,audio,start,end,source,epoch=None):
        if source!='Discord' or end-start<2.0 or self.timeline.has_overlap(start,end):return
        with self.lock:
            current=self._sync()
            if epoch is not None and epoch!=current:return
            epoch=current
        # Keep the whole bounded ASR group. A matching tail must never assign
        # the earlier words of another speaker to that nickname.
        if len(audio)>160000:return
        samples=np.asarray(audio,np.float32).copy()
        start=end-len(samples)/16000
        task=(key,samples,start,end,epoch)
        try:self.pending.put_nowait(task)
        except queue.Full:
            try:self.pending.get_nowait()
            except queue.Empty:pass
            try:self.pending.put_nowait(task)
            except queue.Full:pass

    def result(self,key):
        with self.lock:
            self._sync()
            return self.results.pop(key,'')

    def _embedding(self,audio,minimum_voiced=1.2):
        # Skip mostly silent/music fragments. WebRTC VAD is already installed.
        import webrtcvad
        vad=webrtcvad.Vad(2);voiced=0
        for index in range(0,len(audio)-319,320):
            frame=(np.clip(audio[index:index+320],-1,1)*32767).astype('<i2').tobytes()
            voiced+=int(vad.is_speech(frame,16000))
        if voiced<int(minimum_voiced/.02):return None
        stream=self.extractor.create_stream();stream.accept_waveform(16000,audio);stream.input_finished()
        if not self.extractor.is_ready(stream):return None
        return np.asarray(self.extractor.compute(stream),np.float32)

    def run(self,stop,asr_done):
        try:
            if self.extractor is None:
                if not self.model_path.is_file():return
                import sherpa_onnx
                config=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.model_path),num_threads=1,provider='cpu',debug=False)
                if not config.validate():return
                self.extractor=sherpa_onnx.SpeakerEmbeddingExtractor(config)
            while not stop.is_set() or not asr_done.is_set():
                with self.lock:self._sync()
                try:key,audio,start,end,epoch=self.pending.get(timeout=.05)
                except queue.Empty:continue
                if epoch!=self.timeline.epoch:continue
                name=self.timeline.exclusive(start,end)
                if not name and self.timeline.has_overlap(start,end):continue
                vector=self._embedding(audio)
                if vector is None:continue
                with self.lock:
                    if self._sync()!=epoch:continue
                    if name:
                        self.profiles.learn(name,vector,start,end)
                        continue
                    match=self.profiles.identify(vector)
                # Native inference never holds the result/profile lock: the
                # translation worker must not wait for a speaker computation.
                if match and len(audio)>=64000:
                    halves=[self._embedding(part,minimum_voiced=.6) for part in np.array_split(audio,2)]
                    with self.lock:
                        if self._sync()!=epoch:continue
                        if all(v is not None and self.profiles.identify(v,minimum=.60)==match for v in halves):
                            self.results[key]=match
                with self.lock:
                    while len(self.results)>32:self.results.popitem(last=False)
        finally:
            with self.lock:
                self.profiles.clear();self.results.clear()
                while not self.pending.empty():
                    try:self.pending.get_nowait()
                    except queue.Empty:break
            self.extractor=None
