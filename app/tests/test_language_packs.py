import sys
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from language_packs import (LANGUAGES, create_manifest, validate_manifest, write_pack, read_pack,
                            save_terms_without_overwrite, combine_terms, find_route,
                            installed_for_language,install_translation_models)

class LanguagePacksTests(unittest.TestCase):
    def test_catalog(self):
        self.assertGreaterEqual(len(LANGUAGES), 16)
        for code in LANGUAGES:
            self.assertEqual(validate_manifest(create_manifest(code))["code"], code)

    def test_archive_read_write_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "english.uvkrpack"
            write_pack(p, "en")
            self.assertEqual(read_pack(p)["language"], "영어")
            with self.assertRaises(ValueError):
                validate_manifest({**create_manifest("en"), "code": "xyz"})
            with self.assertRaises(ValueError):
                validate_manifest({**create_manifest("en"), "terms": {"x": 123}})

    def test_user_terms_never_clobbered(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = create_manifest("en")
            save_terms_without_overwrite(data, base)
            f = base / "installed_pack_terms" / "en.json"
            user = json.loads(f.read_text(encoding="utf-8"))
            user["rn"] = "right this moment"
            f.write_text(json.dumps(user), encoding="utf-8")
            save_terms_without_overwrite(data, base)
            self.assertEqual(combine_terms({}, "en", base)["rn"], "right this moment")
            self.assertEqual(combine_terms({"rn": "user preference"}, "en", base)["rn"], "user preference")

    def test_route(self):
        self.assertEqual(find_route("en", set(), {("en", "ko")}), [("en", "ko")])
        self.assertEqual(find_route("es", set(), {("es", "en"), ("en", "ko")}), [("es", "en"), ("en", "ko")])
        self.assertEqual(find_route("es", {("es", "en"), ("en", "ko")}, {("es", "ko")}), [])
        self.assertEqual(find_route("es", {("en", "ko")}, {("es", "en")}), [("es", "en")])
        self.assertEqual(find_route("es", set(), {("es", "fr"), ("fr", "ko")}), None)
        self.assertEqual(find_route("ko", set(), set()), [])

    def test_selected_output_language_controls_model_direction(self):
        self.assertEqual(find_route('en',set(),{('en','es')},'es'),[('en','es')])
        self.assertEqual(find_route('en',{('en','ko')},set(),'es'),None)
        self.assertEqual(find_route('ko',set(),{('ko','en'),('en','fr')},'fr'),[('ko','en'),('en','fr')])
        self.assertEqual(find_route('en',set(),set(),'en'),[])
        self.assertEqual(find_route('pb',set(),set(),'pt'),[])
        manifest=create_manifest('en','es')
        self.assertEqual(validate_manifest(manifest)['translation_target'],'es')

    def test_shared_model_avoids_redundant_argos_download(self):
        with patch('quality_translation.supported_languages',return_value={'en','es'}),patch('language_packs.get_installed_pairs',side_effect=AssertionError('No fallback needed')):
            self.assertTrue(installed_for_language('en','es'))
            self.assertEqual(install_translation_models('en',target='es'),[])

if __name__ == "__main__":
    unittest.main()
