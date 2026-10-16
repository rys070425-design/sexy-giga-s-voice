import builtins
import unittest
from unittest.mock import patch
from local_translation import LocalTranslator
from language_packs import install_translation_models


class OptionalTranslationTests(unittest.TestCase):
    def test_default_translation_does_not_import_legacy_stack(self):
        original_import=builtins.__import__
        def guarded_import(name,*args,**kwargs):
            if name.split('.')[0] in ('argostranslate','stanza','torch'):
                raise AssertionError('Default captions imported '+name)
            return original_import(name,*args,**kwargs)
        with patch('quality_translation.QualityTranslator') as quality,patch('builtins.__import__',side_effect=guarded_import):
            quality.return_value.languages={'en','ko'}
            quality.return_value.supports.return_value=True
            quality.return_value.translate.return_value='도움이 필요해요.'
            translator=LocalTranslator()
            self.assertTrue(translator.supports('en','ko'))
            self.assertEqual(translator.translate('I need help.','en','ko'),'도움이 필요해요.')
            self.assertEqual(translator.translate('Hello.','en','en'),'Hello.')

    def test_missing_legacy_dependency_has_clear_unsupported_route(self):
        original_import=builtins.__import__
        def guarded_import(name,*args,**kwargs):
            if name.startswith('argostranslate'):raise ModuleNotFoundError(name)
            return original_import(name,*args,**kwargs)
        with patch('quality_translation.QualityTranslator') as quality,patch('builtins.__import__',side_effect=guarded_import):
            quality.return_value.languages=set()
            quality.return_value.supports.return_value=False
            translator=LocalTranslator()
            self.assertFalse(translator.supports('en','ko'))
            with self.assertRaisesRegex(ValueError,'번역 모델'):
                translator.translate('Hello.','en','ko')

    def test_missing_shared_model_is_repaired_without_argos(self):
        with patch('quality_translation.supported_languages',side_effect=[set(),{'en','es'}]),patch('model_assets.install_quality_model') as install:
            self.assertEqual(install_translation_models('en',target='es'),[])
            install.assert_called_once()
