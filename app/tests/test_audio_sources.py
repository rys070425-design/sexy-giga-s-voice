import unittest
from audio_sources import SourceTracker,site_label,audible_session,WindowsAudioProbe
from unittest.mock import patch
from types import SimpleNamespace
import sys

class SourceTests(unittest.TestCase):
    def test_youtube_uses_exact_domain(self):
        self.assertEqual(site_label('www.youtube.com'),'YouTube')
        self.assertEqual(site_label('youtube.com.evil.test'),'youtube.com.evil.test')
        self.assertEqual(site_label('https://youtube.com/path'),'')
    def test_playing_browser_uses_reported_site(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['chrome.exe'],i*.2)
        self.assertEqual(source.resolve(.1,1),'YouTube')
    def test_browser_site_is_not_assigned_to_discord(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['discord.exe'],i*.2)
        self.assertEqual(source.resolve(.1,1),'Discord')
    def test_multiple_sound_sources_do_not_claim_a_speaker(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['discord.exe','chrome.exe'],i*.2)
        label=source.resolve(.1,1)
        self.assertEqual(label,'')
    def test_stale_extension_falls_back_to_browser(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['chrome.exe'],50+i*.2)
        self.assertEqual(source.resolve(50.1,51),'Chrome')
    def test_no_activity_has_no_claimed_source(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        source.record([],0)
        self.assertEqual(source.resolve(0,.3),'')
    def test_switching_apps_does_not_claim_whole_clip_is_one_source(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['discord.exe' if i<5 else 'chrome.exe'],i*.2)
        label=source.resolve(0,2)
        self.assertEqual(label,'')
    def test_brief_notification_does_not_replace_main_source(self):
        source=SourceTracker()
        for i in range(20):source.record(['discord.exe' if i==5 else 'chrome.exe'],i*.2)
        self.assertEqual(source.resolve(0,4),'Chrome')

    def test_unknown_runtime_name_is_not_shown_or_ignored_as_competing_audio(self):
        for names in (['python.exe'],['pythonw.exe'],['chrome.exe','python.exe'],['random-helper.exe']):
            source=SourceTracker()
            for i in range(10):source.record(names,i*.2)
            self.assertEqual(source.resolve(0,2),'')

    def test_multiple_audible_browser_sites_use_browser_only(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com','example.com'],0)
        for i in range(10):source.record(['chrome.exe'],i*.2)
        self.assertEqual(source.resolve(0,2),'Chrome')

    def test_site_hint_alone_never_creates_an_audio_source(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record([],i*.2)
        self.assertEqual(source.resolve(0,2),'')

    def test_old_source_does_not_leak_into_later_silence(self):
        source=SourceTracker();source.record(['chrome.exe'],0);source.record([], .2)
        self.assertEqual(source.resolve(.5,1),'')

    def test_active_session_is_not_enough_without_peak_and_ownership_checks(self):
        good=dict(state=1,muted=False,volume=1.,peak=.05,pid=42,ignored_pids={7,8})
        self.assertTrue(audible_session(**good))
        for changes in ({'state':0},{'state':2},{'muted':True},{'volume':0},{'peak':0},{'peak':.0005},{'peak':float('nan')},{'pid':7},{'pid':8},{'pid':0}):
            self.assertFalse(audible_session(**(good|changes)),changes)

    @unittest.skipUnless(sys.platform=='win32','Windows COM session interfaces')
    def test_probe_filters_open_silent_muted_and_own_capture_sessions(self):
        class Control:
            def __init__(self,pid,state=1,peak=.1,muted=False,volume=1):
                self.pid,self.state,self.peak,self.muted,self.volume=pid,state,peak,muted,volume
            def QueryInterface(self,*args):return self
            def GetProcessId(self):return self.pid
            def GetState(self):return self.state
            def GetMute(self):return self.muted
            def GetMasterVolume(self):return self.volume
            def GetPeakValue(self):return self.peak
        controls=[Control(7),Control(8),Control(9,state=0),Control(10,peak=0),Control(11,muted=True),Control(12,volume=0),Control(13,peak=.0005),Control(42)]
        sessions=SimpleNamespace(GetCount=lambda:len(controls),GetSession=lambda index:controls[index])
        probe=WindowsAudioProbe.__new__(WindowsAudioProbe);probe.own_pid=7
        probe.device=SimpleNamespace(AudioSessionManager=SimpleNamespace(GetSessionEnumerator=lambda:sessions))
        def process(pid):return SimpleNamespace(children=lambda **kw:[SimpleNamespace(pid=8)],name=lambda:'chrome.exe' if pid==42 else 'python.exe')
        with patch('psutil.Process',side_effect=process):self.assertEqual(probe.scan(),{'chrome.exe'})
