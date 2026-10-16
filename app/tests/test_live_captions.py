import unittest
import numpy as np
from live_captions import LatestSlot, DisplayOrder, CaptionUpdate
from speech_quality import Segmenter, decoder_options


class LiveCaptionTests(unittest.TestCase):
    def test_user_supplied_vocabulary_is_bounded_and_opt_in(self):
        self.assertNotIn('hotwords',decoder_options({}))
        self.assertEqual(decoder_options({'asr_hotwords':'  민수   아크  '})['hotwords'],'민수 아크')
        self.assertEqual(len(decoder_options({'asr_hotwords':'x'*500})['hotwords']),200)

    def segmenter(self):
        seg=Segmenter()
        seg.vad.is_speech=lambda pcm,rate:pcm!=bytes(len(pcm))
        return seg

    def test_continuous_speech_has_draft_before_final_and_preserves_audio(self):
        seg=self.segmenter()
        audio=np.full(16000*4,.2,np.float32)
        self.assertEqual(seg.push(audio[:19200]),[])
        draft=seg.preview()
        self.assertIsNotNone(draft)
        self.assertFalse(draft.final)
        self.assertEqual(seg.push(audio[19200:]),[])
        final=seg.flush()[0]
        self.assertTrue(final.final)
        self.assertEqual(draft.sequence,final.sequence)
        np.testing.assert_array_equal(final.audio,audio)

    def test_preview_does_not_force_a_premature_final_at_320ms(self):
        seg=self.segmenter()
        self.assertEqual(seg.push(np.full(16000,.2,np.float32)),[])
        self.assertEqual(seg.push(np.zeros(5120,np.float32)),[])
        self.assertEqual(len(seg.push(np.zeros(2560,np.float32))),1)

    def test_preview_work_is_one_latest_item(self):
        slot=LatestSlot()
        for i in range(100):slot.put(i)
        self.assertEqual(slot.take(),99)
        self.assertIsNone(slot.take())

    def update(self,sequence,revision,translated=''):
        return CaptionUpdate(sequence,revision,'speech',translated,'en','Test')

    def test_slow_translation_never_overwrites_new_sentence(self):
        order=DisplayOrder()
        self.assertTrue(order.accept(self.update(1,80)))
        self.assertTrue(order.accept(self.update(2,60)))
        self.assertFalse(order.accept(self.update(1,90,'old translation')))
        self.assertTrue(order.accept(self.update(2,60,'current translation')))

    def test_slow_translation_never_overwrites_new_revision(self):
        order=DisplayOrder()
        self.assertTrue(order.accept(self.update(1,60)))
        self.assertTrue(order.accept(self.update(1,100)))
        self.assertFalse(order.accept(self.update(1,60,'old draft')))

    def test_raw_same_revision_never_erases_existing_translation(self):
        order=DisplayOrder()
        self.assertTrue(order.accept(self.update(1,60,'translated')))
        self.assertFalse(order.accept(self.update(1,60)))

    def test_preview_does_not_keep_reissuing_same_audio(self):
        seg=self.segmenter()
        seg.push(np.full(19200,.2,np.float32))
        self.assertIsNotNone(seg.preview())
        self.assertIsNone(seg.preview())
        seg.push(np.full(3200,.2,np.float32))
        self.assertIsNone(seg.preview())
        seg.push(np.full(3200,.2,np.float32))
        self.assertIsNotNone(seg.preview())
