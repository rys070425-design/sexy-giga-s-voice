import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import VoiceService
from live_captions import CaptionUpdate


class TranslationStreamTests(unittest.TestCase):
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
