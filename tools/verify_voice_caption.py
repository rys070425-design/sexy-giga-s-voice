"""Real CAM++/NLLB/Qt integration with local two-speaker recordings.
Usage: runtime-python verify_voice_caption.py INSTALL_ROOT FIXTURES REPORT.json
FIXTURES needs accent-korean1.mp3 and accent-spanish1.mp3 from the documented
quality audit. No microphone, account, external audio upload or persisted
embeddings. This is a controlled test, not an actual Discord call.
"""
import sys,os,time,json,threading
from pathlib import Path
from unittest.mock import patch
import numpy as np
root=Path(sys.argv[1]).resolve();base=Path(sys.argv[2]).resolve();report_path=Path(sys.argv[3]).resolve();sys.path.insert(0,str(root))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['UVKR_DATA_DIR']=str(report_path.parent/'voice-caption-test-state')
from runtime_config import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from engine import VoiceService
from voice_identity import VoiceIdentity,MODEL_PATH
from live_captions import CaptionUpdate
from speaker_labels import UNKNOWN
from local_translation import LocalTranslator
from caption_presentation import ReadableCaptions,clean_caption_label
from main import SubtitleOverlay
from faster_whisper.audio import decode_audio
import sherpa_onnx
app=QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
service=VoiceService();assist=VoiceIdentity(service.timeline)
config=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODEL_PATH),num_threads=1,provider='cpu',debug=False)
assist.extractor=sherpa_onnx.SpeakerEmbeddingExtractor(config)
for name,filename in [('Alice','accent-korean1.mp3'),('Bob','accent-spanish1.mp3')]:
    audio=decode_audio(str(base/filename))
    for offset in (2,9):assist.profiles.learn(name,assist._embedding(audio[offset*16000:(offset+4)*16000]),offset,offset+4)
translator=LocalTranslator();translator.translate('','en','ko')
service.profile={'language':'en','target_language':'ko','translation_context':'general'};service.dictionary={};service.voice_identity=assist
service._workers_remaining=1;service.asr_done.set()
events=[];errors=[];service.live_caption.connect(events.append);service.error.connect(errors.append)
clip=decode_audio(str(base/'accent-spanish1.mp3'))[18*16000:22*16000]
stop=threading.Event();done=threading.Event();worker=threading.Thread(target=assist.run,args=(stop,done));worker.start()
try:
    key=(1,0,service.timeline.epoch);started=time.perf_counter();assist.submit(key,clip,18,22,'Discord')
    # Owned text, unrelated to enrolment sentences. No wait for speaker work.
    service.text_q.put(CaptionUpdate(1,100,"I will call you when I get there.",'','en',UNKNOWN,True,source='Discord',speaker_epoch=service.timeline.epoch))
    with patch('local_translation.LocalTranslator',return_value=translator):service._translate(service.stop_event)
    elapsed=time.perf_counter()-started
    assert not errors,errors
    assert events[-1].complete and events[-1].speaker=='Bob',events
    view=ReadableCaptions(interval=0);event=events[-1];view.offer(event,clean_caption_label(event.speaker,event.source))
    overlay=SubtitleOverlay();overlay.show_readable(view.current,None,{'overlay':True,'font':26,'background_opacity':42,'show_original':False});app.processEvents()
    assert 'Bob:' in overlay.label.text()+overlay.previous_label.text();overlay.grab().save(str(report_path.with_suffix('.png')));overlay.close()
finally:stop.set();done.set();worker.join(3)
assert not worker.is_alive() and not assist.profiles.entries
report={'result':'REAL_CAMPLUS_NLLB_QT_CAPTION_VERIFIED','speaker':'Bob','blocking_wait_for_speaker':False,'translation_and_name_seconds':round(elapsed,4),'actual_discord_call':False,'owned_caption_text':True,'audio_uploaded':False,'profiles_cleared':True}
report_path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
