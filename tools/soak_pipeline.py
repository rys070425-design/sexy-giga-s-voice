"""Bounded real-time synthetic-input soak and repeated clean shutdown test."""
import sys,time,json,types,gc
from pathlib import Path
from collections import deque
import numpy as np
from scipy.signal import resample_poly
import psutil
runtime,fixtures,report=map(lambda value:Path(value).resolve(),sys.argv[1:4])
seconds=int(sys.argv[4]) if len(sys.argv)>4 else 120
sys.path.insert(0,str(runtime))
from runtime_config import configure
configure()
import core
core.HOME=report.parent/'isolated-soak-state'
from PySide6.QtCore import QCoreApplication
from faster_whisper.audio import decode_audio
from engine import VoiceService
from speech_quality import Segmenter
from caption_presentation import ReadableCaptions
app=QCoreApplication([])
audio=decode_audio(str(fixtures/'speech-en.wav'))
rng=np.random.default_rng(20261017)
process=psutil.Process();summaries=[]
for cycle in range(3):
    service=VoiceService();presentation=ReadableCaptions()
    errors=[];overloads=[];recent=deque(maxlen=10);samples=[];counts={'complete':0,'preview':0,'redraw':0}
    origin=[];last_sample=0
    service.error.connect(errors.append)
    service.status.connect(lambda text:overloads.append(text) if '대기열 초과' in text or '건너뜁니다' in text else None)
    def caption(event):
        counts['complete' if event.final and event.complete else 'preview']+=1
        if event.final and event.complete:recent.append((event.original,event.translated))
        if presentation.offer(event,'시험 음성'):counts['redraw']+=1
    service.live_caption.connect(caption)
    def capture(self,stop):
        try:
            assert self.ready.wait(30) and self.translator_ready.wait(30)
            origin.append(time.monotonic());segmenter=Segmenter(1);offset=0;turn=0
            while offset/16000<seconds and not stop.is_set():
                speed=[(1,1),(20,23),(4,5)][turn%3]
                signal=resample_poly(audio,*speed).astype(np.float32)*[1.,.4,.15][turn%3]
                if turn%4==3:
                    noise=float(np.sqrt(np.mean(signal**2)))/np.sqrt(31.6)
                    signal+=rng.normal(0,noise,len(signal)).astype(np.float32)
                signal=np.r_[signal,np.zeros(16000,np.float32)]
                for index in range(0,len(signal),800):
                    if stop.is_set():break
                    delay=origin[0]+(offset+800)/16000-time.monotonic()
                    if delay>0:time.sleep(delay)
                    self.timeline.record(['시험 화자'],time.monotonic())
                    for clip in segmenter.push(signal[index:index+800]):
                        clip.start+=origin[0];self._enqueue(self.audio_q,clip,'test')
                    preview=segmenter.preview()
                    if preview is not None:preview.start+=origin[0];self.preview_audio.put(preview)
                    offset+=800
                turn+=1
            for clip in segmenter.flush():clip.start+=origin[0];self._enqueue(self.audio_q,clip,'test')
            stop.set()
        except Exception as exc:errors.append(str(exc));stop.set()
        finally:self._worker_finished(stop)
    service._capture=types.MethodType(capture,service)
    started=time.monotonic()
    service.start(dict(model='large-v3-turbo',device='cuda',language='en',target_language='ko',
                       beam_size=5,translation_context='general'),{})
    while service.running and time.monotonic()-started<seconds+90:
        app.processEvents()
        if presentation.advance():counts['redraw']+=1
        now=time.monotonic()
        if now-last_sample>=10:
            samples.append(dict(seconds=round(now-started,1),rss_mb=round(process.memory_info().rss/1048576,1),
                                audio_waiting=service.audio_q.qsize(),translation_waiting=service.text_q.qsize()))
            last_sample=now
        time.sleep(.01)
    app.processEvents()
    # stopped is emitted at the end of the final worker; allow its signal
    # emission to return before asserting OS-thread termination.
    if not service.running:
        for thread in service.threads:thread.join(timeout=2)
    if service.running or any(thread.is_alive() for thread in service.threads):
        import faulthandler
        with report.with_suffix('.failure.txt').open('w',encoding='utf-8') as output:
            output.write(json.dumps(dict(running=service.running,counts=counts,errors=errors,
                workers={thread.name:thread.is_alive() for thread in service.threads}),ensure_ascii=False)+'\n')
            faulthandler.dump_traceback(file=output)
    assert not service.running and all(not thread.is_alive() for thread in service.threads),'Workers did not finish'
    assert not errors and not overloads,(errors,overloads)
    assert counts['complete']>=10,counts
    gc.collect()
    row=dict(cycle=cycle+1,elapsed=round(time.monotonic()-started,1),counts=counts,
             post_stop_rss_mb=round(process.memory_info().rss/1048576,1),samples=samples,recent=list(recent))
    summaries.append(row)
    report.write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in row.items() if key not in ('samples','recent')},ensure_ascii=False),flush=True)
print('PIPELINE_SOAK_VERIFIED',flush=True)
