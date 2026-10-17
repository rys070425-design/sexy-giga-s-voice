import threading,time,unittest
from pathlib import Path
import numpy as np
from speaker_labels import SpeakerTimeline,UNKNOWN,group_timed_words
from voice_identity import VoiceProfiles,VoiceIdentity

class VoiceIdentityTests(unittest.TestCase):
    def test_abstains_without_two_independent_enrolments_and_other_person(self):
        p=VoiceProfiles();a=np.array([1.,0.,0.]);b=np.array([0.,1.,0.])
        p.learn('Alice',a,0,4);p.learn('Alice',a,2,6)
        self.assertEqual(len(p.entries['Alice']),1)
        p.learn('Alice',a,5,9)
        self.assertEqual(p.identify(a),'')
        p.learn('Bob',b,10,14);p.learn('Bob',b,15,19)
        self.assertEqual(p.identify(a),'Alice');self.assertEqual(p.identify(b),'Bob')
        self.assertEqual(p.identify(np.array([1.,1.,0.])),'')
        self.assertEqual(p.identify(np.array([0.,0.,1.])),'')

    def test_rejects_conflicting_enrolment_and_bounds_memory(self):
        p=VoiceProfiles();p.learn('Alice',np.array([1.,0.]),0,4)
        p.learn('Alice',np.array([0.,1.]),5,9)
        self.assertEqual(len(p.entries['Alice']),1)
        for i in range(40):p.learn(str(i),np.array([1.,0.]),10,14)
        self.assertEqual(len(p.entries),32)

    def test_strict_training_requires_current_singleton_evidence(self):
        t=SpeakerTimeline()
        for i in range(40):t.record(['Alice'],i*.1)
        self.assertEqual(t.exclusive(.1,3.9),'Alice')
        self.assertEqual(t.exclusive(.1,5),'')
        t.record(['Alice','Bob'],4)
        self.assertEqual(t.exclusive(.1,4.2),'')
        self.assertTrue(t.has_overlap(4,4.2))
        before=t.epoch;t.clear();self.assertGreater(t.epoch,before)

    def test_only_discord_and_nonoverlap_audio_enters_bounded_queue(self):
        t=SpeakerTimeline();assist=VoiceIdentity(t);audio=np.ones(64000,np.float32)
        assist.submit((1,0,0),audio,0,4,'YouTube');self.assertTrue(assist.pending.empty())
        t.record(['Alice','Bob'],0)
        assist.submit((1,0,0),audio,0,4,'Discord');self.assertTrue(assist.pending.empty())
        t.clear()
        for i in range(8):assist.submit((i,0,0),audio,0,4,'Discord')
        self.assertEqual(assist.pending.qsize(),2)

    def test_channel_change_erases_names_and_late_results(self):
        t=SpeakerTimeline();assist=VoiceIdentity(t)
        assist.profiles.learn('Alice',np.array([1.,0.]),0,4)
        assist.results[(1,0,0)]='Alice';t.clear()
        self.assertEqual(assist.result((1,0,0)),'');self.assertFalse(assist.profiles.entries)
        assist.submit((1,0,0),np.ones(64000,np.float32),0,4,'Discord',epoch=0)
        self.assertTrue(assist.pending.empty())

    def test_worker_stop_erases_session_memory(self):
        t=SpeakerTimeline();assist=VoiceIdentity(t,extractor=object())
        assist.profiles.learn('Alice',np.array([1.,0.]),0,4)
        stop=threading.Event();done=threading.Event();done.set()
        thread=threading.Thread(target=assist.run,args=(stop,done));thread.start();stop.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertFalse(assist.profiles.entries)

    def test_result_lookup_never_waits_for_native_inference(self):
        timeline=SpeakerTimeline();assist=VoiceIdentity(timeline,extractor=object())
        entered=threading.Event();release=threading.Event();stop=threading.Event();done=threading.Event()
        def slow(audio):entered.set();release.wait(2);return np.array([1.,0.],np.float32)
        assist._embedding=slow
        assist.submit((0,0,0),np.ones(64000,np.float32),0,4,'Discord')
        thread=threading.Thread(target=assist.run,args=(stop,done));thread.start()
        self.assertTrue(entered.wait(2));started=time.perf_counter()
        self.assertEqual(assist.result((0,0,0)),'')
        self.assertLess(time.perf_counter()-started,.05)
        stop.set();done.set();release.set();thread.join(3);self.assertFalse(thread.is_alive())

    def test_word_spans_stay_with_each_person(self):
        t=SpeakerTimeline();t.record(['Alice'],0);t.record(['Bob'],.3)
        groups=group_timed_words([(' Hello',.01,.2),(' there',.31,.5)],t,0)
        self.assertEqual(groups,[('Alice','Hello',.01,.2),('Bob','there',.31,.5)])
