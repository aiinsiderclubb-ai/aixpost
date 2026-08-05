import tempfile
import unittest
from pathlib import Path

from bot.message_templates import MessageTemplateManager


class MessageTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "templates.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_expand_spintax_and_variables(self):
        manager = MessageTemplateManager(str(self.path))
        manager.templates = ["{Hello|Hi} {name} from {city|Berlin}!"]
        manager.default_variables["name"] = ["Alex"]

        message, _, used = manager.generate_message(0)

        self.assertTrue(message.startswith(("Hello", "Hi")))
        self.assertIn("Alex", message)
        self.assertGreaterEqual(used["anti_duplicate_score"], 0)

    def test_extract_variables_supports_single_and_double_braces(self):
        manager = MessageTemplateManager(str(self.path))
        variables = manager.get_template_variables("Hello {name} and {{city}}")
        self.assertIn("name", variables)
        self.assertIn("city", variables)


if __name__ == "__main__":
    unittest.main()
