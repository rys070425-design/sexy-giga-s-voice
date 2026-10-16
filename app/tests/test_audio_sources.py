import unittest
from audio_sources import SourceTracker,site_label

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
    def test_multiple_sound_sources_are_explicit(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['discord.exe','chrome.exe'],i*.2)
        label=source.resolve(.1,1)
        self.assertIn('여러 소리',label);self.assertIn('Discord',label);self.assertIn('YouTube',label)
    def test_stale_extension_falls_back_to_browser(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        for i in range(10):source.record(['chrome.exe'],50+i*.2)
        self.assertEqual(source.resolve(50.1,51),'Chrome')
    def test_no_activity_has_no_claimed_source(self):
        source=SourceTracker();source.set_sites('chrome',['youtube.com'],0)
        source.record([],0)
        self.assertEqual(source.resolve(0,.3),'')
