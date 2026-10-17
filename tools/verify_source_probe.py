"""Real Windows COM session + own loopback capture smoke test; no stored audio."""
import sys,time,json,os
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from runtime_config import configure
configure()
from audio_sources import WindowsAudioProbe,SourceTracker
from core import select_output_loopback
from pycaw.api.audiopolicy import IAudioSessionControl2
import soundcard as sc
probe=WindowsAudioProbe();tracker=SourceTracker();counts=[];own_seen=False
def inspect():
    global own_seen
    session_list=probe.device.AudioSessionManager.GetSessionEnumerator()
    own_seen|=any(session_list.GetSession(i).QueryInterface(IAudioSessionControl2).GetProcessId()==os.getpid() for i in range(session_list.GetCount()))
    names=probe.scan();now=time.monotonic();tracker.record(names,now)
    label=tracker.resolve(now-.1,now+.1)
    assert 'python' not in label.lower() and ' + ' not in label
    counts.append(len(names))
try:
    inspect()
    device=select_output_loopback(sc.all_microphones(include_loopback=True),'',sc.default_speaker())
    with device.recorder(samplerate=16000) as recorder:
        for i in range(6):
            recorder.record(numframes=3200)  # Discard immediately, never save/play.
            inspect()
    inspect()
finally:probe.close()
report={'result':'REAL_WINDOWS_SOURCE_PROBE_AND_LOOPBACK_VERIFIED','scan_count':len(counts),'own_render_session_seen':own_seen,'filtered_candidate_counts':counts,'no_audio_saved_or_played':True,'no_runtime_or_app_list_label':True,'scope':'COM/loopback smoke test; deterministic simultaneous-source cases are unit tests'}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
