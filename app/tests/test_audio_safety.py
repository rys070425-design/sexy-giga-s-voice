"""Safety: microphone capture must never be selected by any profile."""
import unittest
from types import SimpleNamespace
from core import select_output_loopback

class OutputOnlyTests(unittest.TestCase):
    def setUp(self):
        self.mic = SimpleNamespace(id="MIC", name="My microphone", isloopback=False)
        self.output = SimpleNamespace(id="SPEAKER", name="Discord output", isloopback=True)
        self.default = SimpleNamespace(id="SPEAKER")

    def test_default_chooses_output(self):
        self.assertIs(select_output_loopback([self.mic, self.output], "", self.default), self.output)

    def test_selected_output_chooses_output(self):
        self.assertIs(select_output_loopback([self.mic, self.output], "SPEAKER", self.default), self.output)

    def test_old_microphone_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "마이크 입력"):
            select_output_loopback([self.mic, self.output], "MIC", self.default)

    def test_missing_default_output_never_falls_back_to_microphone(self):
        with self.assertRaises(ValueError):
            select_output_loopback([self.mic], "", self.default)

    def test_invalid_previously_configured_device_is_rejected(self):
        with self.assertRaises(ValueError):
            select_output_loopback([self.mic, self.output], "UNKNOWN", self.default)

if __name__ == "__main__":
    unittest.main()
