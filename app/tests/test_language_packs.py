import sys
import json
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from language_packs import (LANGUAGES, create_manifest, validate_manifest, write_pack, read_pack,
                            save_terms_without_overwrite, combine_terms, find_route)

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

if __name__ == "__main__":
    unittest.main()
