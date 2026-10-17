import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import VoiceService
from live_captions import CaptionUpdate


class TranslationStreamTests(unittest.TestCase):
    def test_native_translation_kernels_warm_before_ready(self):
        calls=[]
        class Translator:
            packages={}
            def supports(self,a,b):return True
            def translate(self,text,source,target):calls.append((text,source,target));return ''
        service=VoiceService();service.profile={'language':'auto','target_language':'en'}
        service.dictionary={};service._workers_remaining=1;service.asr_done.set()
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=Translator()):service._translate(service.stop_event)
        self.assertEqual(calls,[('1','ko','en')]);self.assertTrue(service.translator_ready.is_set())

    def test_voice_hint_only_fills_current_unknown_discord_speaker(self):
        from types import SimpleNamespace
        class Translator:
            packages={}
            def translate(self,text,source,target='ko'):return '번역' if text else ''
        for source,speaker,epoch,expected in [('Discord','화자 미확인',0,'Alice'),
                ('YouTube','화자 미확인',0,'화자 미확인'),('Discord','Bob',0,'Bob'),
                ('Discord','화자 미확인',-1,'화자 미확인')]:
            service=VoiceService();service.profile={'language':'en','translation_context':'general'}
            service.dictionary={};service._workers_remaining=1;service.asr_done.set()
            calls=[];service.voice_identity=SimpleNamespace(result=lambda key:(calls.append(key) or 'Alice'))
            service.text_q.put(CaptionUpdate(1,100,'Hello.','','en',speaker,True,source=source,speaker_epoch=epoch))
            events=[];captions=[];service.live_caption.connect(events.append);service.attributed_caption.connect(lambda *p:captions.append(p))
            with tempfile.TemporaryDirectory() as directory:
                with patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=Translator()):service._translate(service.stop_event)
            self.assertEqual(events[-1].speaker,expected);self.assertEqual(captions[-1][-1],expected)
            self.assertEqual(bool(calls),expected=='Alice')

    def test_spanish_output_uses_requested_direction_and_no_korean_phrase(self):
        calls=[]
        class Translator:
            packages={}
            def translate(self,text,source,target='ko'):
                calls.append((text,source,target));return 'Necesito ayuda.'
        service=VoiceService();service.profile={'language':'en','target_language':'es','translation_context':'game'}
        service.dictionary={};service._workers_remaining=1;service.asr_done.set()
        service.text_q.put(CaptionUpdate(0,100,'I need healing.','','en','시험',True,target_language='es'))
        captions=[];service.attributed_caption.connect(lambda *p:captions.append(p))
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=Translator()):
                service._translate(service.stop_event)
        self.assertEqual(calls,[('I need healing.','en','es')])
        self.assertEqual(captions[0][1],'Necesito ayuda.')

    def test_english_captions_do_not_use_saved_korean_or_game_translation(self):
        class Translator:
            packages={}
            def translate(self,*args):raise AssertionError('English captions need no translation model')
        service=VoiceService();service.profile={'language':'en','target_language':'en','translation_context':'game'}
        service.dictionary={};service._workers_remaining=1;service.asr_done.set()
        service.text_q.put(CaptionUpdate(0,100,'I need healing.','','en','시험',True))
        captions=[];service.attributed_caption.connect(lambda *p:captions.append(p))
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=Translator()),patch('core.read_phrase_memory',return_value={'en:i need healing.':'잘못된 한국어'}):
                service._translate(service.stop_event)
        self.assertEqual(captions[0][1],'I need healing.')

    def test_cache_does_not_drop_repeated_spoken_calls(self):
        class Translator:
            packages={}
            calls=0
            def translate(self,text,source,target='ko'):
                self.calls+=1
                return '도움이 필요해.'
        translator=Translator()
        service=VoiceService()
        service.profile={'language':'en','translation_context':'general'}
        service.dictionary={}
        service._workers_remaining=1
        service.asr_done.set()
        for sequence in range(2):
            service.text_q.put(CaptionUpdate(sequence,100,'I need help.','','en','시험',True))
        captions=[]
        service.attributed_caption.connect(lambda *parts:captions.append(parts))
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.HOME',Path(directory)),patch('local_translation.LocalTranslator',return_value=translator):
                service._translate(service.stop_event)
        self.assertEqual(translator.calls,1)
        self.assertEqual(len(captions),2)
        self.assertEqual([c[0] for c in captions],['I need help.','I need help.'])
