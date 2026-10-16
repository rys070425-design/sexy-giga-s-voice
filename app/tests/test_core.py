import json
import tempfile
import unittest
from pathlib import Path
from core import expand_terms, init_files, merge_glossary, update_due, valid_remote_dictionary


class CoreTests(unittest.TestCase):
    def test_dictionary_expansion(self):
        self.assertEqual(expand_terms("need stego rn, ngl", {"rn":"right now", "ngl":"honestly", "stego":"stegosaurus"}),
                         "need stegosaurus right now, honestly")
        self.assertEqual(expand_terms("arnold", {"rn":"right now"}), "arnold")

    def test_disk_and_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg, terms = init_files(Path(temp))
            self.assertEqual(cfg["profiles"][0]["name"], "디스코드 · 게임")
            self.assertIn("rn", merge_glossary(terms, "ARK"))
            self.assertIn("soaking", merge_glossary(terms, "ARK"))
            self.assertTrue((Path(temp) / "glossary.json").exists())

    def test_update_due(self):
        self.assertFalse(update_due({"schedule":"daily", "url":""}, 100000))
        self.assertTrue(update_due({"schedule":"daily", "url":"https://a", "last_checked":0}, 100000))
        self.assertFalse(update_due({"schedule":"daily", "url":"https://a", "last_checked":90000}, 100000))

    def test_dictionary_validation(self):
        self.assertTrue(valid_remote_dictionary({"global":{"rn":"right now"},"games":{"FPS":{"ult":"ultimate"}}}))
        self.assertFalse(valid_remote_dictionary({"global":[], "games":{}}))
        self.assertFalse(valid_remote_dictionary({"global":{},"games":{"bad":[]}}))


if __name__ == '__main__':
    unittest.main()
