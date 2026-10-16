import os, sys, json, time, types, re, importlib.util
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly, butter, sosfilt
base=Path(__file__).resolve().parent
source=base.parent/'app'
runtime=Path(sys.argv[1]).resolve()
fixtures=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(source))
os.environ['HF_HUB_OFFLINE']='1'
os.environ['ARGOS_PACKAGES_DIR']=str(runtime/'translation_models')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module
old_speech=load('old_speech',base/'baseline_v052'/'speech_quality.py')
import speech_quality as new_speech
sys.modules['speech_quality']=old_speech
old_engine=load('old_engine',base/'baseline_v052'/'engine.py')
sys.modules['speech_quality']=new_speech
import engine as new_engine
from live_captions import DisplayOrder
from cuda_runtime import prepare_cuda
prepare_cuda()
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
from PySide6.QtCore import QCoreApplication
import core
core.HOME=base/'isolated-state'
app=QCoreApplication([])
model=WhisperModel(str(runtime/'models'/'large-v3-turbo'),device='cuda',compute_type='int8_float16',cpu_threads=4)
segs,_=model.transcribe(np.zeros(16000,np.float32),language='en',beam_size=1,vad_filter=False);list(segs)
refs={
 'ko':'적들이 우리 기지로 밀고 들어오고 있어요. 오른쪽으로 돌아서 공격하세요. 잠깐 기다려 주세요. 지금 회복하고 있어요.',
 'en':'They are pushing our base. Watch the right side. Wait a second, I am healing. We need to defend the entrance together.'}
def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]
def error(text,language):
    norm=lambda t:re.sub(r'[^\w]','',t.casefold()) if language=='ko' else re.findall(r'\w+',t.casefold())
    a,b=norm(refs[language]),norm(text)
    return round(distance(a,b)/len(a),4)
results=[]
for lang in refs:
    audio=decode_audio(str(fixtures/f'speech-{lang}.wav'))
    for version,mod,speech in [('0.5.2',old_engine,old_speech),('0.6',new_engine,new_speech)]:
        service=mod.VoiceService()
        def fake_model(self):self.resolved_device='cuda';return model
        service._load_model=types.MethodType(fake_model,service)
        start=[];final=[];first=[];raw=[];errors=[];live=[];order=DisplayOrder()
        def caption(*parts):
            final.append(parts)
            if not first:first.append(time.monotonic()-start[0])
        def update(event):
            if order.accept(event):
                live.append(dict(time=round(time.monotonic()-start[0],3),original=event.original,translated=event.translated,final=event.final))
                if not raw:raw.append(time.monotonic()-start[0])
                if event.translated and not first:first.append(time.monotonic()-start[0])
        service.attributed_caption.connect(caption)
        if version=='0.6':service.live_caption.connect(update)
        service.error.connect(errors.append)
        def capture(self,stop):
            try:
                assert self.ready.wait(30)
                seg=speech.Segmenter(1)
                start.append(time.monotonic())
                signal=np.r_[audio,np.zeros(16000,np.float32)]
                for i in range(0,len(signal),800):
                    delay=start[0]+(i+800)/16000-time.monotonic()
                    if delay>0:time.sleep(delay)
                    self.timeline.record(['테스트'],time.monotonic())
                    for clip in seg.push(signal[i:i+800]):
                        clip.start+=start[0];self._enqueue(self.audio_q,clip,'test')
                    if version=='0.6':
                        clip=seg.preview()
                        if clip is not None:clip.start+=start[0];self.preview_audio.put(clip)
                for clip in seg.flush():clip.start+=start[0];self._enqueue(self.audio_q,clip,'test')
                stop.set()
            except Exception as exc:errors.append(str(exc));stop.set()
            finally:self._worker_finished(stop)
        service._capture=types.MethodType(capture,service)
        service.start(dict(model='large-v3-turbo',device='cuda',language=lang,beam_size=5,translation_context='game'),{})
        deadline=time.monotonic()+60
        while service.running and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
        app.processEvents()
        assert not service.running and not errors,errors
        assert final,version
        text=' '.join(p[0] for p in final)
        row=dict(kind='realtime',version=version,language=lang,first_original=round(raw[0],3) if raw else None,first_korean=round(first[0],3),error_rate=error(text,lang),final_text=text,events=live)
        print(json.dumps({k:v for k,v in row.items() if k!='events'},ensure_ascii=False),flush=True);results.append(row)
rng=np.random.default_rng(20261017)
for lang in refs:
    audio=decode_audio(str(fixtures/f'speech-{lang}.wav'));rms=float(np.sqrt(np.mean(audio**2)))
    muffled=sosfilt(butter(4,[180,1700],fs=16000,btype='bandpass',output='sos'),audio).astype(np.float32)
    fast=resample_poly(muffled,20,27).astype(np.float32)
    cases=[('normal',audio),('quiet',audio*.0316),('fast',resample_poly(audio,20,29).astype(np.float32)),('muffled-fast-noisy',(fast+rng.normal(0,rms/np.sqrt(10),len(fast))).astype(np.float32))]
    for name,signal in cases:
        for version,speech in [('0.5.2',old_speech),('0.6',new_speech)]:
            seg=speech.Segmenter(1);clips=[]
            padded=np.r_[signal,np.zeros(16000,np.float32)]
            for i in range(0,len(padded),800):clips+=seg.push(padded[i:i+800])
            clips+=seg.flush();texts=[];started=time.perf_counter()
            for clip in clips:
                segs,_=model.transcribe(clip.audio,**speech.decoder_options({'language':lang,'beam_size':5}))
                texts.append(''.join(p[0] for p in speech.transcript_parts(segs,clip.overlap)).strip())
            text=' '.join(texts)
            row=dict(kind='quality',version=version,language=lang,case=name,clips=len(clips),seconds=round(time.perf_counter()-started,3),error_rate=error(text,lang),text=text)
            print(json.dumps(row,ensure_ascii=False),flush=True);results.append(row)
(base/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('EVALUATION_COMPLETE',flush=True)
