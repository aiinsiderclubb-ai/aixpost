import unittest

from bot.geo_classifier import GeoClassifier


class GeoClassifierTests(unittest.TestCase):
    def test_detects_country_from_group_name(self):
        self.assertEqual(
            GeoClassifier.classify_group("Работа в Берлине для украинцев"),
            "germany",
        )
        self.assertEqual(
            GeoClassifier.classify_group("Jobs in Zurich Switzerland"),
            "switzerland",
        )

    def test_batch_adds_country_fields(self):
        groups = GeoClassifier.classify_groups_batch([
            {"name": "Warszawa praca", "url": "https://facebook.com/groups/1"},
            {"name": "Unknown community", "url": "https://facebook.com/groups/2"},
        ])
        self.assertEqual(groups[0]["country_tag"], "poland")
        self.assertEqual(groups[1]["country_tag"], "unknown")
        self.assertIn("country_name", groups[0])


if __name__ == "__main__":
    unittest.main()
