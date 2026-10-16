"""Read-only Windows playback-session labels aligned to captured audio."""
from collections import deque
from threading import RLock
import time
import re

BROWSERS={'chrome.exe':'chrome','msedge.exe':'edge','firefox.exe':'firefox','brave.exe':'brave','opera.exe':'opera'}
NAMES={'discord.exe':'Discord','discordptb.exe':'Discord','discordcanary.exe':'Discord',
       'chrome.exe':'Chrome','msedge.exe':'Edge','firefox.exe':'Firefox','brave.exe':'Brave','opera.exe':'Opera',
       'vlc.exe':'VLC','spotify.exe':'Spotify','system':'Windows'}

def site_label(host):
    host=str(host).strip().lower().rstrip('.')
    if len(host)>253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host):return ''
    if host=='youtube.com' or host.endswith('.youtube.com') or host=='youtu.be':return 'YouTube'
    if host=='twitch.tv' or host.endswith('.twitch.tv'):return 'Twitch'
    return host.removeprefix('www.')

class SourceTracker:
    def __init__(self):
        self.lock=RLock();self.samples=deque();self.web={}
    def set_sites(self,browser,hosts,now=None):
        if browser not in ('chrome','edge'):raise ValueError('Unsupported browser')
        labels=tuple(sorted({site_label(host) for host in hosts if site_label(host)}))[:8]
        with self.lock:self.web[browser]=(time.monotonic() if now is None else now,labels)
    def record(self,process_names,now=None):
        now=time.monotonic() if now is None else now
        labels=set()
        with self.lock:
            for process in set(process_names):
                process=process.lower();browser=BROWSERS.get(process)
                stamp,sites=self.web.get(browser,(-1000,()))
                if browser and now-stamp<=40 and sites:labels.update(sites)
                else:labels.add(NAMES.get(process,process.removesuffix('.exe')[:40]))
            labels=sorted(labels)
            label=('여러 소리 · '+' + '.join(labels)) if len(labels)>1 else (labels[0] if labels else '')
            self.samples.append((now,label[:140]))
            while self.samples and self.samples[0][0]<now-180:self.samples.popleft()
    def resolve(self,start,end):
        with self.lock:samples=list(self.samples)
        scores={}
        for i,(stamp,label) in enumerate(samples):
            if not label:continue
            until=min(samples[i+1][0] if i+1<len(samples) else stamp+.3,stamp+.6)
            duration=max(0,min(end,until)-max(start,stamp))
            scores[label]=scores.get(label,0)+duration
        if not scores:return ''
        label,coverage=max(scores.items(),key=lambda item:item[1])
        return label if coverage>=min(.15,max(.02,(end-start)*.15)) else ''

class WindowsAudioProbe:
    def __init__(self,audio_id=''):
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize();self.com=comtypes
        try:
            if audio_id:self.device=AudioUtilities.CreateDevice(AudioUtilities.GetDeviceEnumerator().GetDevice(audio_id))
            else:self.device=AudioUtilities.GetSpeakers()
        except Exception:
            comtypes.CoUninitialize();raise
    def scan(self):
        import psutil
        from pycaw.api.audiopolicy import IAudioSessionControl2
        from pycaw.api.endpointvolume import IAudioMeterInformation
        from pycaw.api.audioclient import ISimpleAudioVolume
        sessions=self.device.AudioSessionManager.GetSessionEnumerator();names=set()
        for index in range(sessions.GetCount()):
            try:
                control=sessions.GetSession(index).QueryInterface(IAudioSessionControl2)
                volume=control.QueryInterface(ISimpleAudioVolume)
                if volume.GetMute() or volume.GetMasterVolume()<=0:continue
                if control.QueryInterface(IAudioMeterInformation).GetPeakValue()<.0005:continue
                pid=control.GetProcessId()
                names.add(psutil.Process(pid).name().lower() if pid else 'system')
            except Exception:continue
        return names
    def close(self):
        self.device=None;self.com.CoUninitialize()
