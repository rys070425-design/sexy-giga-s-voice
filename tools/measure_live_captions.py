"""Feed owned speech fixtures in real time; measure actual visible updates.

Usage: installed-python measure_live_captions.py INSTALL_ROOT FIXTURES REPORT.json [--device cpu|cuda] [--model NAME --model-dir PATH]
Model warmup precedes the timing origin. No microphone or account is used.
"""
import os,sys,time,types,json,argparse
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
parser=argparse.ArgumentParser()
parser.add_argument('runtime',type=Path)
parser.add_argument('fixtures',type=Path)
parser.add_argument('report',type=Path)
parser.add_argument('--device',choices=('cpu','cuda'),default='cuda')
parser.add_argument('--model',default='large-v3-turbo')
parser.add_argument('--model-dir',type=Path)
args=parser.parse_args()
runtime,fixtures,report=(path.resolve() for path in (args.runtime,args.fixtures,args.report))
device=args.device
sys.path.insert(0,str(runtime))
from runtime_config import configure
configure()
os.environ['HF_HUB_OFFLINE']='1'
os.environ['QT_QPA_PLATFORM']='offscreen'
from cuda_runtime import prepare_cuda
prepare_cuda()
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from engine import VoiceService
from speech_quality import make_segmenter
from caption_presentation import ReadableCaptions
import core
from main import SubtitleOverlay,STYLESHEET
core.HOME=report.parent/'isolated-latency-state'
app=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
app.setStyleSheet(STYLESHEET)
overlay=SubtitleOverlay()
display_profile=dict(font=26,background_opacity=42,show_original=False,overlay=True)
model=WhisperModel(str(args.model_dir or runtime/'models'/args.model),device=device,
                   compute_type='int8_float16' if device=='cuda' else 'int8',cpu_threads=4)
segments,_=model.transcribe(np.zeros(16000,np.float32),language='en',beam_size=1)
list(segments)
results=[]
for language,mode,target,kind in [('en','en','ko','normal'),('en','auto','ko','normal'),
        ('ko','ko','ko','normal'),('ko','auto','ko','normal'),
        ('en','en','ko','fast'),('en','en','ko','noisy'),('en','en','en','normal')]:
    audio=decode_audio(str(fixtures/f'speech-{language}.wav'))[:48000]
    if kind=='fast':audio=resample_poly(audio,4,5).astype(np.float32)
    if kind=='noisy':
        rng=np.random.default_rng(20261017)
        audio=(audio+rng.normal(0,float(np.sqrt(np.mean(audio**2)))/np.sqrt(10),len(audio))).astype(np.float32)
    service=VoiceService();presentation=ReadableCaptions();errors=[];events=[];visible=[];origin=[]
    def render():
        overlay.show_readable(presentation.current,presentation.previous,display_profile)
        overlay.grab()  # Complete actual offscreen Qt layout and paint.
        visible.append(dict(seconds=round(time.monotonic()-origin[0],3),
                            decision_seconds=round(presentation.changed_at-origin[0],3),text=presentation.current.text))
    def load(self):self.resolved_device=device;return model
    service._load_model=types.MethodType(load,service)
    def update(event):
        now=time.monotonic();events.append(dict(seconds=round(now-origin[0],3),text=event.translated,final=event.final,complete=event.complete))
        if presentation.offer(event,'YouTube',now):
            render()
    service.live_caption.connect(update);service.error.connect(errors.append)
    def capture(self,stop):
        try:
            assert self.ready.wait(30) and self.translator_ready.wait(30)
            origin.append(time.monotonic());segmenter=make_segmenter({'vad':1,'translation_context':'general'},.4 if device=='cuda' else 1.2)
            signal=np.r_[audio,np.zeros(16000,np.float32)]
            for offset in range(0,len(signal),800):
                delay=origin[0]+(offset+800)/16000-time.monotonic()
                if delay>0:time.sleep(delay)
                self.timeline.record([],time.monotonic())
                for clip in segmenter.push(signal[offset:offset+800]):
                    clip.start+=origin[0];self._enqueue(self.audio_q,clip,'test')
                preview=segmenter.preview()
                if preview is not None:preview.start+=origin[0];self.preview_audio.put(preview)
            for clip in segmenter.flush():clip.start+=origin[0];self._enqueue(self.audio_q,clip,'test')
            stop.set()
        except Exception as exc:errors.append(str(exc));stop.set()
        finally:self._worker_finished(stop)
    service._capture=types.MethodType(capture,service)
    service.start(dict(model=args.model,device=device,language=mode,target_language=target,
                       beam_size=5,translation_context='general'),{})
    deadline=time.monotonic()+(120 if device=='cpu' else 45)
    while service.running and time.monotonic()<deadline:
        app.processEvents()
        if origin and presentation.advance():render()
        time.sleep(.005)
    app.processEvents()
    assert not service.running and not errors,errors
    for thread in service.threads:
        thread.join(2)
        assert not thread.is_alive(),thread.name
    assert visible and any(event['final'] and event['complete'] for event in events),events
    gaps=[round(b['seconds']-a['seconds'],3) for a,b in zip(visible,visible[1:])]
    # Late corrections to the retained line do not change current text and are
    # not present in this single-utterance fixture.
    decisions=[round(b['decision_seconds']-a['decision_seconds'],3) for a,b in zip(visible,visible[1:])]
    # Cold paint can take longer than later paints. Completion timestamps
    # therefore differ slightly from the guaranteed display-decision pacing.
    assert all(gap>=.79 for gap in decisions),decisions
    row=dict(model=args.model,device=device,language=language,mode=mode,target=target,kind=kind,first_visible=visible[0]['seconds'],
             visible_updates=len(visible),minimum_update_gap=min(gaps) if gaps else None,
             minimum_decision_gap=min(decisions) if decisions else None,
             visible=visible,events=events)
    results.append(row)
    overlay.hide()
    print(json.dumps({key:value for key,value in row.items() if key not in ('visible','events')},ensure_ascii=False),flush=True)
report.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('READABLE_LATENCY_VERIFIED',flush=True)
