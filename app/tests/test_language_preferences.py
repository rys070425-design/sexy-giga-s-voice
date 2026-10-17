import copy,json,threading,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import numpy as np
from language_preferences import language_choices,apply_install_language,same_language
from live_captions import CaptionUpdate
from caption_presentation import ReadableCaptions
from speech_quality import AudioClip
from engine import VoiceService

class LanguagePreferencesTests(unittest.TestCase):
    def test_installer_choices_match_packs_and_apply_all_profiles(self):
        from language_packs import LANGUAGES
        self.assertEqual({code for _,code in language_choices()},set(LANGUAGES))
        settings={'profiles':[{'name':'My profile','language':'en'},{'target_language':'ko'}]}
        apply_install_language(settings,'ja')
        self.assertEqual(settings['ui_language'],'ja')
        self.assertEqual(settings['default_caption_language'],'ja')
        self.assertEqual(settings['profiles'][0]['name'],'My profile')
        for profile in settings['profiles']:
            self.assertEqual((profile['language'],profile['target_language'],profile['hide_native']),('auto','ja',True))
        self.assertTrue(same_language('pb','pt'))
        self.assertFalse(same_language('ko','en'))

    def test_native_audio_never_iterates_lazy_decoder_or_queues_text(self):
        for detected,target in [('ko','ko'),('en','en'),('pt','pb')]:
            service=VoiceService();service._workers_remaining=1
            service.profile={'language':'en','target_language':target,'hide_native':True}
            options=[];events=[];errors=[]
            def fail_decode():
                raise AssertionError('Native audio entered text decoding')
                yield
            def transcribe(audio,**kwargs):
                options.append(kwargs)
                return fail_decode(),SimpleNamespace(language=detected)
            service._load_model=lambda:SimpleNamespace(transcribe=transcribe)
            service.audio_q.put(AudioClip(np.zeros(16000,np.float32),sequence=5,revision=100))
            service.live_caption.connect(events.append);service.error.connect(errors.append)
            service.stop_event.set();service._recognize(service.stop_event)
            self.assertEqual(errors,[])
            self.assertEqual(len(events),1)
            self.assertTrue(events[0].suppressed)
            self.assertEqual((events[0].original,events[0].translated),('',''))
            self.assertTrue(service.text_q.empty())
            self.assertIsNone(service.preview_text.take())
            self.assertNotIn('language',options[0])

    def test_translation_filter_precedes_glossary_memory_and_translation(self):
        service=VoiceService();service._workers_remaining=1
        service.profile={'language':'pt','target_language':'pb','hide_native':True}
        service.dictionary={};service.asr_done.set()
        service.text_q.put(CaptionUpdate(1,100,'native secret','','pt','name',True))
        translator=Mock();translator.model_label='test';translator.supports.return_value=False
        events=[];captions=[];errors=[]
        service.live_caption.connect(events.append);service.attributed_caption.connect(lambda *a:captions.append(a));service.error.connect(errors.append)
        with tempfile.TemporaryDirectory() as directory,patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=translator),patch('language_packs.combine_terms',side_effect=AssertionError('native glossary work')):
            service._translate(service.stop_event)
        self.assertEqual(errors,[]);self.assertEqual(captions,[])
        translator.translate.assert_not_called()
        self.assertEqual((events[0].original,events[0].translated,events[0].suppressed),('','',True))

    def test_suppression_bars_delayed_result_but_new_revision_recovers(self):
        view=ReadableCaptions(interval=0)
        foreign=CaptionUpdate(3,40,'hello','안녕','en','',True,True)
        self.assertTrue(view.offer(foreign,'Audio',now=0))
        self.assertTrue(view.suppress(CaptionUpdate(3,50,'','','ko','',True,True,suppressed=True)))
        self.assertFalse(view.offer(foreign,'Audio',now=1))
        self.assertTrue(view.is_suppressed(foreign))
        recovery=CaptionUpdate(3,60,'hello again','다시 안녕','en','',True,True)
        self.assertTrue(view.offer(recovery,'Audio',now=2))
        view.suppress(CaptionUpdate(2,100,'','','ko','',True,True,suppressed=True))
        self.assertEqual(view.current.text,'다시 안녕')

    def test_english_output_prepares_foreign_translation_before_listening(self):
        translator=Mock();translator.model_label='test';translator.supports.return_value=True
        service=VoiceService();service._workers_remaining=1;service.dictionary={}
        service.profile={'language':'auto','target_language':'en','hide_native':True}
        service.asr_done.set()
        service.text_q.put(CaptionUpdate(1,100,'English native','','en','',True,target_language='en'))
        with tempfile.TemporaryDirectory() as directory,patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=translator):
            service._translate(service.stop_event)
        translator.translate.assert_called_once_with('','ko','en')

    def test_localization_preserves_native_names_placeholders_and_user_data(self):
        from ui_i18n import translate,catalog
        self.assertEqual(translate('한국어',code='en'),'한국어')
        self.assertEqual(translate('실시간 자막',code='en'),'Live captions')
        self.assertEqual(translate('실시간 자막',code='ko'),'실시간 자막')
        self.assertEqual(translate('게임 감지 · 미설치 프로필 전환',code='en'),'Game detected · Switching to profile 미설치')
        data=catalog()
        self.assertEqual(len(data['languages']),25)
        import re
        for code,messages in data['messages'].items():
            for source,value in messages.items():
                self.assertEqual(set(re.findall(r'\{\d+\}',source)),set(re.findall(r'\{\d+\}',value)),(code,source,value))
