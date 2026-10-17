import unittest
from translation_input import prepare_translation_text

class TranslationInputTests(unittest.TestCase):
    def test_unambiguous_verb_forms_preserve_negation(self):
        text="I'm not leaving. They're here. We've waited. You'll hear it. I should've asked."
        self.assertEqual(prepare_translation_text(text,'en'),"I am not leaving. They are here. We have waited. You will hear it. I should've asked.")

    def test_ambiguous_forms_and_negatives_remain_intact(self):
        text="I'd known. He's left. It's ready. John's car. I didn't tell her. I won't go."
        self.assertEqual(prepare_translation_text(text,'en'),text)

    def test_boundaries_urls_addresses_and_other_languages(self):
        text="YOU’LL see https://example.org/we'll and we're@example.com."
        self.assertEqual(prepare_translation_text(text,'en'),"YOU WILL see https://example.org/we'll and we're@example.com.")
        self.assertEqual(prepare_translation_text("I'm here",'ko'),"I'm here")
        self.assertEqual(prepare_translation_text("AcmeI'm not a pronoun",'en'),"AcmeI'm not a pronoun")
