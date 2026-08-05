import tempfile
import unittest
from pathlib import Path

from platform_runtime import RuntimeStore


class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "runtime.db"
        self.store = RuntimeStore(str(self.db_path))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_task_and_group_roundtrip(self):
        task_id = self.store.create_task(
            user_id=7,
            task_type="posting",
            title="Test posting",
            payload={"group_urls": ["https://facebook.com/groups/123"]},
        )
        self.store.append_task_event(task_id, "started", event_type="system")
        self.store.upsert_group_status(
            task_id,
            "https://facebook.com/groups/123",
            "Processing",
            group_name="Test Group",
            error_reason="",
        )
        self.store.update_task(task_id, status="running")

        task = self.store.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["payload"]["group_urls"], ["https://facebook.com/groups/123"])
        self.assertEqual(task["events"][0]["message"], "started")
        self.assertEqual(task["group_statuses"][0]["group_name"], "Test Group")

    def test_filter_and_template_metadata(self):
        self.store.save_filter(11, "German only", {"segment": "german"})
        self.store.sync_templates(11, ["Hello {name}", "Buy now {city}"])
        self.store.update_template_meta(11, "Hello {name}", title="Intro", folder="A/B", tags=["test", "warm"])

        filters = self.store.list_filters(11)
        templates = self.store.list_templates(11)

        self.assertEqual(filters[0]["name"], "German only")
        self.assertEqual(filters[0]["config"]["segment"], "german")
        self.assertIn(templates[0]["title"], {"Intro", "Hello {name}"})


if __name__ == "__main__":
    unittest.main()
