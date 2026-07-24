import unittest

from src.pipeline.memory_recovery.contracts import FeatureType, MemoryFeature, MemoryQuery
from src.pipeline.memory_recovery.memory_parser import parse_memory_query


class MemoryQueryParserPhaseN11Tests(unittest.TestCase):
    def test_object_detection(self) -> None:
        query = "There was a table and a diagram with a circle and an arrow in the browser window."
        parsed = parse_memory_query(query)

        self.assertIsInstance(parsed, MemoryQuery)
        self.assertTrue(parsed.is_memory_query)
        self.assertIn("table", parsed.objects)
        self.assertIn("diagram", parsed.objects)
        self.assertIn("circle", parsed.objects)
        self.assertIn("arrow", parsed.objects)
        self.assertIn("browser", parsed.objects)
        self.assertIn("window", parsed.objects)

    def test_color_detection(self) -> None:
        query = "I remember a blue and yellow chart next to a green slide."
        parsed = parse_memory_query(query)

        self.assertTrue(parsed.is_memory_query)
        self.assertIn("blue", parsed.colors)
        self.assertIn("yellow", parsed.colors)
        self.assertIn("green", parsed.colors)

    def test_action_detection(self) -> None:
        query = "He drew two arrows and explained the code."
        parsed = parse_memory_query(query)

        self.assertTrue(parsed.is_memory_query)
        self.assertIn("drew", parsed.actions)
        self.assertIn("explained", parsed.actions)

    def test_temporal_detection(self) -> None:
        query = "After APIs he explained MCP earlier in the beginning."
        parsed = parse_memory_query(query)

        self.assertTrue(parsed.is_memory_query)
        self.assertIn("after", parsed.temporal_clues)
        self.assertIn("earlier", parsed.temporal_clues)
        self.assertIn("beginning", parsed.temporal_clues)

    def test_spatial_detection(self) -> None:
        query = "There was a red circle at the top left and two boxes in the center."
        parsed = parse_memory_query(query)

        self.assertTrue(parsed.is_memory_query)
        self.assertIn("top left", parsed.spatial_clues)
        self.assertIn("two", parsed.spatial_clues)
        self.assertIn("center", parsed.spatial_clues)

    def test_text_detection(self) -> None:
        query = 'There was a slide with "Docker" titled APIs.'
        parsed = parse_memory_query(query)

        self.assertTrue(parsed.is_memory_query)
        self.assertIn("Docker", parsed.text_clues)
        self.assertIn("APIs", parsed.text_clues)

    def test_normal_factual_question(self) -> None:
        query = "What is MCP?"
        parsed = parse_memory_query(query)

        self.assertEqual(parsed.original_query, "What is MCP?")
        self.assertFalse(parsed.is_memory_query)

    def test_memory_questions(self) -> None:
        queries = [
            "I remember there was a blue graph.",
            "There was a slide with Docker.",
            "He drew two arrows.",
            "After APIs he explained MCP.",
            "Earlier there was a table.",
        ]
        for q in queries:
            parsed = parse_memory_query(q)
            self.assertTrue(parsed.is_memory_query, msg=f"Failed memory classification for '{q}'")
            self.assertIsInstance(parsed.features, list)
            self.assertGreater(len(parsed.features), 0)

    def test_empty_query(self) -> None:
        parsed = parse_memory_query("")
        self.assertEqual(parsed.original_query, "")
        self.assertEqual(parsed.features, [])
        self.assertFalse(parsed.is_memory_query)

        parsed_spaces = parse_memory_query("   ")
        self.assertEqual(parsed_spaces.original_query, "")
        self.assertEqual(parsed_spaces.features, [])
        self.assertFalse(parsed_spaces.is_memory_query)

    def test_multiple_features_and_source(self) -> None:
        query = "I remember a blue graph at the top left."
        parsed = parse_memory_query(query)

        self.assertEqual(parsed.original_query, query)
        self.assertTrue(parsed.is_memory_query)

        for feat in parsed.features:
            self.assertIsInstance(feat, MemoryFeature)
            self.assertEqual(feat.source, "rule_based")
            self.assertEqual(feat.confidence, 1.0)

        feature_types = {f.feature_type for f in parsed.features}
        self.assertIn(FeatureType.COLOR, feature_types)
        self.assertIn(FeatureType.OBJECT, feature_types)
        self.assertIn(FeatureType.SPATIAL_CLUE, feature_types)

    def test_invalid_type_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            parse_memory_query(12345)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
