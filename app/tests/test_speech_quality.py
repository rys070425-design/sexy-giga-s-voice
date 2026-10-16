import unittest
from types import SimpleNamespace as Obj
import threading
import numpy as np
from speech_quality import Segmenter, decoder_options, transcript_parts
from speaker_labels import SpeakerTimeline, UNKNOWN, validate_widget_url, group_words
from engine import VoiceService
from local_translation import translation_route, game_phrase_translation


class SpeechQualityTests(unittest.TestCase):
    def test_game_calls_are_exact_and_language_scoped(self):
        self.assertEqual(game_phrase_translation('Wait a second, I am healing.', 'en'),'잠깐만, 회복 중이야.')
        self.assertIsNone(game_phrase_translation('I am not healing.', 'en'))
        self.assertIsNone(game_phrase_translation('I am healing.', 'fr'))

    def test_translation_prefers_direct_installed_model(self):
        self.assertEqual(translation_route('fr','ko',{('fr','en'),('en','ko'),('fr','ko')}),[('fr','ko')])
        self.assertEqual(translation_route('fr','ko',{('fr','en'),('en','ko')}),[('fr','en'),('en','ko')])
        with self.assertRaises(ValueError):translation_route('fr','ko',{('fr','en')})

    def segmenter(self):
        seg = Segmenter()
        seg.vad.is_speech = lambda pcm, rate: pcm != bytes(len(pcm))
        return seg

    def test_cut_has_exact_audio_overlap(self):
        seg = self.segmenter()
        clips = seg.push(np.full(320*450, .3, np.float32)) + seg.flush()
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0].overlap, 0)
        self.assertAlmostEqual(clips[1].overlap, .6)
        self.assertAlmostEqual(clips[1].start, 7.4)
        np.testing.assert_array_equal(clips[0].audio[-9600:], clips[1].audio[:9600])
        self.assertEqual(len(clips[0].audio) + len(clips[1].audio) - 9600, 320*450)

    def test_last_short_call_survives_stop(self):
        seg = self.segmenter()
        self.assertEqual(seg.push(np.full(320*10,.3,np.float32)), [])
        self.assertEqual(len(seg.flush()),1)
        self.assertEqual(seg.flush(),[])

    def test_short_noise_is_rejected(self):
        seg = self.segmenter()
        clips = seg.push(np.r_[np.full(320,.3,np.float32),np.zeros(320*25,np.float32)])
        self.assertEqual(clips,[])

    def test_pause_ends_long_turn_early(self):
        seg = self.segmenter()
        clips = seg.push(np.r_[np.full(320*151,.3,np.float32),np.zeros(320*9,np.float32)])
        self.assertEqual(len(clips),1)
        self.assertLess(len(clips[0].audio)/16000,3.3)

    def test_overlapping_words_removed_without_text_deduplication(self):
        seg = Obj(no_speech_prob=.1,avg_logprob=-.3,words=[
            Obj(word=' Go',start=.1,end=.4), Obj(word=' go',start=.5,end=.8),
            Obj(word=' go',start=1.,end=1.3)])
        self.assertEqual([p[0] for p in transcript_parts([seg],.6)],[' go',' go'])

    def test_silence_hallucination_filter(self):
        seg=Obj(no_speech_prob=.9,avg_logprob=-1.5,words=None,text='Thanks',start=0,end=1)
        self.assertEqual(list(transcript_parts([seg])),[])

    def test_profile_language_and_quality_preserved(self):
        opts=decoder_options({'language':'pb'})
        self.assertEqual(opts['language'],'pt')
        self.assertEqual(opts['beam_size'],5)
        self.assertTrue(opts['word_timestamps'])
        self.assertTrue(opts['vad_filter'])
        self.assertNotIn('initial_prompt',opts)

    def test_three_workers_must_finish(self):
        svc=VoiceService(); svc._workers_remaining=3; svc.running=True
        evt=threading.Event(); stopped=[]; svc.stopped.connect(lambda:stopped.append(True))
        svc._worker_finished(evt); svc._worker_finished(evt)
        self.assertTrue(svc.running); self.assertEqual(stopped,[])
        svc._worker_finished(evt)
        self.assertFalse(svc.running); self.assertEqual(stopped,[True])


class SpeakerTests(unittest.TestCase):
    def timeline(self, people):
        timeline=SpeakerTimeline()
        for i in range(21):timeline.record(people, i*.1)
        return timeline

    def test_single_speaker(self):
        self.assertEqual(self.timeline(['민수']).resolve(.3,1.2),'민수')

    def test_never_assign_overlap_to_one_person(self):
        self.assertIn('동시 발화',self.timeline(['민수','Alice']).resolve(.3,1.2))

    def test_frozen_widget_expires(self):
        self.assertEqual(self.timeline(['민수']).resolve(3,4),UNKNOWN)

    def test_no_activity_stays_unknown(self):
        self.assertEqual(self.timeline([]).resolve(.3,1.2),UNKNOWN)

    def test_speaker_changes_split_words(self):
        timeline=SpeakerTimeline()
        for i in range(21):timeline.record(['Alice' if i<10 else 'Bob'], i*.1)
        groups=group_words([(' Hello',.2,.5),(' there',.6,.8),(' Yes',1.2,1.4)],timeline,0)
        self.assertEqual(groups,[('Alice','Hello there'),('Bob','Yes')])

    def test_widget_url_only_allows_official_voice_page(self):
        valid='https://streamkit.discord.com/overlay/voice/123456789012345678/234567890123456789'
        self.assertEqual(validate_widget_url(valid+'?hide_names=true'),valid)
        for url in [valid.replace('https:','http:'),valid.replace('discord.com','evil.com'),
                    'https://streamkit.discord.com/overlay',valid.replace('https://','https://user@')]:
            with self.assertRaises(ValueError):validate_widget_url(url)


if __name__=='__main__':unittest.main()
