"""Real ASR/NLLB + controlled widget timeline, not a real Discord call."""
import sys,os,json
from pathlib import Path
root=Path(sys.argv[1]).resolve();fixture=Path(sys.argv[2]).resolve();report=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(root));os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['UVKR_DATA_DIR']=str(report.parent/'discord-pipeline-test-state')
from runtime_config import configure
configure()
from cuda_runtime import prepare_cuda
prepare_cuda()
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio
import ctranslate2
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from engine import VoiceService
from speech_quality import AudioClip
from caption_presentation import ReadableCaptions,clean_caption_label
from main import SubtitleOverlay
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
device='cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
model=WhisperModel(str(root/'models/large-v3-turbo'),device=device,compute_type='int8_float16' if device=='cuda' else 'int8',cpu_threads=4)
audio=decode_audio(str(fixture))[:56000]
rows=[];overlay=SubtitleOverlay()
for scenario in ('single','brief-ring-overlap','speaker-turn','sustained-overlap'):
    service=VoiceService();service.profile={'language':'en','target_language':'ko','hide_native':False,'beam_size':5,'translation_context':'general'}
    service.dictionary={};service._workers_remaining=2;service._load_model=lambda:model
    for i in range(51):
        names=['Alice']
        if scenario=='brief-ring-overlap' and i==10:names=['Alice','Bob']
        if scenario=='speaker-turn' and i>=17:names=['Bob']
        if scenario=='sustained-overlap':names=['Alice','Bob']
        service.timeline.record(names,100+i*.1);service.sources.record(['discord.exe'],100+i*.1)
    events=[];errors=[]
    service.live_caption.connect(events.append);service.error.connect(errors.append)
    service.audio_q.put(AudioClip(audio,start=100,sequence=1,revision=100));service.stop_event.set()
    service._recognize(service.stop_event);service._translate(service.stop_event)
    assert not errors,errors
    complete=[event for event in events if event.final and event.complete]
    assert complete and all(event.original and event.translated for event in complete)
    names={event.speaker for event in complete}
    if scenario in ('single','brief-ring-overlap'):assert names=={'Alice'},names
    if scenario=='speaker-turn':assert {'Alice','Bob'}<=names,names
    if scenario=='sustained-overlap':assert names=={'Alice / Bob'},names
    view=ReadableCaptions(interval=0)
    for event in complete:
        view.offer(event,clean_caption_label(event.speaker,event.source),now=event.revision)
        overlay.show_readable(view.current,view.previous,{'overlay':True,'font':26,'show_original':False})
        app.processEvents();overlay.grab()
        assert '동시 발화' not in overlay.label.text()+overlay.previous_label.text()
        if event.speaker!='화자 미확인':
            assert ': ' in overlay.label.text()+overlay.previous_label.text()
            assert not overlay.speaker_label.isVisible()
    rows.append({'scenario':scenario,'speaker_labels':sorted(names),'final_parts':len(complete),'all_translated':True,'source':'Discord'})
overlay.close()
result={'result':'REAL_ASR_TRANSLATION_WITH_CONTROLLED_SPEAKER_TIMELINE_VERIFIED','device':device,'real_discord_call':False,'scenarios':rows}
report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
