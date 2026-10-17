import unittest
from dataclasses import replace
from caption_presentation import ReadableCaptions,clean_caption_label,wrap_measured
from live_captions import CaptionUpdate

def update(seq,rev,text,final=False,language='ko'):
    return CaptionUpdate(seq,rev,text,text if language=='ko' else '',language,'화자 미확인',final,final)

class PresentationTests(unittest.TestCase):
    def test_discord_speaker_is_inline_without_assigning_other_apps(self):
        model=ReadableCaptions(interval=0)
        event=CaptionUpdate(1,100,'Hello','안녕하세요.','en','민수',True,True,'Discord')
        model.offer(event,'Discord · 민수',0)
        self.assertEqual(model.current.display_text,'민수: 안녕하세요.')
        model.offer(replace(event,sequence=2,source='YouTube'),'YouTube',1)
        self.assertEqual(model.current.speaker,'')
        self.assertEqual(model.current.display_text,'안녕하세요.')
    def test_english_captions_can_show_without_korean_translation(self):
        model=ReadableCaptions()
        event=CaptionUpdate(0,25,'Hello there','','en','화자 미확인',target_language='en')
        self.assertTrue(model.offer(event,'YouTube',0))
        self.assertEqual(model.current.text,'Hello there')
    def test_first_translation_has_no_extra_delay(self):
        model=ReadableCaptions()
        self.assertTrue(model.offer(update(0,25,'안녕하세요'),'YouTube',0))
        self.assertEqual(model.current.text,'안녕하세요')
    def test_fast_revisions_are_coalesced(self):
        model=ReadableCaptions()
        model.offer(update(0,25,'처음'),'YouTube',0)
        self.assertFalse(model.offer(update(0,45,'처음 말'),'YouTube',.2))
        self.assertFalse(model.offer(update(0,65,'처음 말 뒤에'),'YouTube',.4))
        self.assertEqual(model.current.text,'처음')
        self.assertTrue(model.advance(.8))
        self.assertEqual(model.current.text,'처음 말 뒤에')
    def test_foreign_raw_does_not_replace_translation(self):
        model=ReadableCaptions()
        model.offer(update(0,25,'번역문'),'YouTube',0)
        self.assertFalse(model.offer(update(0,45,'foreign',language='en'),'YouTube',1))
        self.assertEqual(model.current.text,'번역문')
    def test_duplicate_text_does_not_redraw(self):
        model=ReadableCaptions();model.offer(update(0,25,'같은 말'),'YouTube',0)
        self.assertFalse(model.offer(update(0,45,'같은 말'),'YouTube',1))
    def test_untranslated_draft_does_not_discard_inflight_translation(self):
        model=ReadableCaptions()
        model.offer(update(0,25,'번역문'),'YouTube',0)
        model.offer(update(1,45,'foreign',language='en'),'YouTube',.2)
        self.assertTrue(model.offer(update(0,35,'번역문 이어서'),'YouTube',1))
        self.assertEqual(model.current.text,'번역문 이어서')
    def test_late_final_corrects_previous_without_rewinding_or_reholding(self):
        model=ReadableCaptions()
        model.offer(update(0,25,'이전 임시 문장'),'YouTube',0)
        model.offer(update(1,25,'현재 문장'),'YouTube',1)
        previous_at=model.previous_at
        self.assertTrue(model.offer(update(0,90,'이전 확정 문장',True),'YouTube',1.2))
        self.assertEqual(model.current.text,'현재 문장')
        self.assertEqual(model.previous.text,'이전 확정 문장')
        self.assertEqual(model.previous_at,previous_at)
        self.assertFalse(model.offer(update(0,30,'뒤늦은 임시 문장'),'YouTube',2))
        self.assertFalse(model.offer(update(0,80,'오래된 확정 문장',True),'YouTube',2))
        self.assertEqual(model.previous.text,'이전 확정 문장')
    def test_previous_sentence_stays_when_speech_is_fast(self):
        model=ReadableCaptions()
        model.offer(update(0,25,'첫 문장',True),'YouTube',0)
        model.offer(update(1,25,'둘째 문장'),'YouTube',1)
        self.assertEqual(model.previous.text,'첫 문장')
        model.offer(update(2,25,'셋째 문장'),'YouTube',2)
        self.assertEqual(model.previous.text,'첫 문장')
        self.assertEqual(model.current.text,'셋째 문장')
    def test_final_is_not_delayed_forever(self):
        model=ReadableCaptions();model.offer(update(0,25,'길게 잘못 들은 문장입니다'),'YouTube',0)
        model.offer(update(0,45,'완전히 다른 확정 결과',True),'YouTube',.2)
        self.assertTrue(model.advance(.8))
        self.assertTrue(model.current.final)
    def test_old_translation_cannot_rewind(self):
        model=ReadableCaptions();model.offer(update(2,45,'최근'),'YouTube',0)
        self.assertFalse(model.offer(update(1,90,'과거',True),'YouTube',2))
        self.assertEqual(model.current.text,'최근')
    def test_speaker_groups_in_one_clip_are_separate_reading_lines(self):
        model=ReadableCaptions()
        first=update(0,100,'먼저 말한 사람',True)
        second=replace(update(0,101,'다음 말한 사람',True),part=1)
        model.offer(first,'Discord · A',0)
        model.offer(second,'Discord · B',1)
        self.assertEqual(model.previous.text,'먼저 말한 사람')
        self.assertEqual(model.current.text,'다음 말한 사람')
        self.assertTrue(model.offer(replace(first,translated='앞 문장 정정',revision=102),'Discord · A',1.2))
        self.assertEqual(model.previous.text,'앞 문장 정정')
        self.assertEqual(model.current.label,'Discord · B')
    def test_clean_labels_have_no_unknown_status(self):
        self.assertEqual(clean_caption_label('화자 미확인','YouTube'),'YouTube')
        self.assertEqual(clean_caption_label('민수','Discord'),'Discord · 민수')
        self.assertEqual(clean_caption_label('민수','YouTube'),'YouTube')
        self.assertEqual(clean_caption_label('민수','여러 소리 · Discord + YouTube'),
                         '여러 소리 · Discord + YouTube')
        self.assertEqual(clean_caption_label('화자 미확인'),'')
        self.assertEqual(clean_caption_label('민수'),'')
        self.assertEqual(clean_caption_label('민수','Discord','example.com'),'example.com')
    def test_wrap_does_not_elide_content(self):
        lines=wrap_measured('가나다라마바사아자차',4,len)
        self.assertEqual(''.join(lines),'가나다라마바사아자차')
        self.assertTrue(all(len(line)<=4 for line in lines))
