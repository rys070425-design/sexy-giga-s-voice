import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from speech_quality import AudioClip, SpeechPresence, DraftStability, ambiguous_fragment
from live_captions import CaptionUpdate
from caption_presentation import ReadableCaptions
from engine import VoiceService


class PresenceTests(unittest.TestCase):
    def test_gate_uses_speech_model_without_trimming_audio(self):
        gate=SpeechPresence();audio=np.zeros(8000,np.float32)
        gate.detect=Mock(return_value=[]);self.assertFalse(gate(audio))
        self.assertIs(gate.detect.call_args.args[0],audio)
        self.assertEqual(gate.options.speech_pad_ms,0)
        gate.detect.return_value=[{'start':100,'end':3000}];self.assertTrue(gate(audio))

    def test_unstable_short_draft_waits_but_real_final_thanks_survives(self):
        stable=DraftStability()
        self.assertFalse(stable.accept(AudioClip(None,sequence=1,revision=25,final=False),'Thank you.'))
        self.assertFalse(stable.accept(AudioClip(None,sequence=1,revision=45,final=False),'Thank you!'))
        self.assertFalse(stable.accept(AudioClip(None,sequence=2,revision=25,final=False),'Thank you.'))
        self.assertTrue(stable.accept(AudioClip(None,sequence=2,revision=30,final=True),'Thank you.'))

    def test_draft_needs_new_audio_not_same_callback_twice(self):
        stable=DraftStability();clip=AudioClip(None,sequence=1,revision=25,final=False)
        self.assertFalse(stable.accept(clip,'Go!'));self.assertFalse(stable.accept(clip,'Go!'))
        self.assertTrue(stable.accept(AudioClip(None,sequence=1,revision=26,final=True),'Go!'))

    def test_longer_first_draft_has_no_added_hold(self):
        self.assertTrue(DraftStability().accept(AudioClip(None,revision=25,final=False),'Please call me when you arrive.'))

    def test_punctuation_only_final_is_not_speech_text(self):
        self.assertFalse(DraftStability().accept(AudioClip(None,final=True),'...'))

    def test_weak_fragment_requires_all_three_uncertainties(self):
        segment=SimpleNamespace(words=[SimpleNamespace(word=' short',probability=.3),SimpleNamespace(word=' word',probability=.99)])
        self.assertTrue(ambiguous_fragment([segment],.65,.224))
        self.assertFalse(ambiguous_fragment([segment],.9,.224))
        self.assertFalse(ambiguous_fragment([segment],.65,.6))
        segment.words[0].probability=.9;self.assertFalse(ambiguous_fragment([segment],.65,.224))

    def test_single_word_calls_are_not_rejected_as_weak_two_word_guesses(self):
        segment=SimpleNamespace(words=[SimpleNamespace(word=' Help!',probability=.3)])
        self.assertFalse(ambiguous_fragment([segment],.4,.2))

    def test_retraction_keeps_other_sentence_and_blocks_delayed_translation(self):
        view=ReadableCaptions(interval=0)
        previous=CaptionUpdate(1,25,'real','실제 문장','en','',True,True)
        bad=CaptionUpdate(2,25,'Thank you','고마워요','en','')
        view.offer(previous,'',0);view.offer(bad,'',1)
        rejected=CaptionUpdate(2,70,'','','','',True,True,retracted=True)
        self.assertTrue(view.retract(rejected));self.assertEqual(view.current.text,'실제 문장')
        self.assertFalse(view.offer(bad,'',2))
        # A real new utterance can repeat the same words.
        self.assertTrue(view.offer(CaptionUpdate(3,40,'Thank you','고마워요','en','',True,True),'',3))

    def test_old_retraction_never_clears_new_sentence(self):
        view=ReadableCaptions(interval=0);view.offer(CaptionUpdate(5,50,'real','새 문장','en','',True,True),'',0)
        self.assertFalse(view.retract(CaptionUpdate(2,100,'','','','',True,True,retracted=True)))
        self.assertEqual(view.current.text,'새 문장')

    def test_nonspeech_is_not_decoded_and_final_retracts_pending_draft(self):
        service=VoiceService();service.profile={'language':'auto'};service._workers_remaining=1
        model=Mock();service._load_model=lambda:model
        service.audio_q.put(AudioClip(np.zeros(16000,np.float32),sequence=7,revision=70));service.stop_event.set()
        events=[];errors=[];service.live_caption.connect(events.append);service.error.connect(errors.append)
        with patch('engine.SpeechPresence') as presence:
            presence.return_value.return_value=False;service._recognize(service.stop_event)
        self.assertEqual(errors,[]);model.transcribe.assert_not_called()
        self.assertEqual(len(events),1);self.assertTrue(events[0].retracted);self.assertEqual(service.finalized_sequence,7)

    def test_speech_with_empty_final_also_retracts_draft(self):
        service=VoiceService();service.profile={'language':'auto'};service._workers_remaining=1
        model=Mock();model.transcribe.return_value=(iter([]),SimpleNamespace(language='en'))
        service._load_model=lambda:model
        service.audio_q.put(AudioClip(np.zeros(16000,np.float32),sequence=8,revision=80));service.stop_event.set()
        events=[];service.live_caption.connect(events.append)
        with patch('engine.SpeechPresence') as presence:
            presence.return_value.return_value=True;presence.return_value.speech_seconds=1.
            service._recognize(service.stop_event)
        self.assertEqual(len(events),1);self.assertTrue(events[0].retracted)


if __name__=='__main__':unittest.main()
