import unittest

from src.pipeline.agentic.conversation_resolver import resolve_conversation_references
from src.pipeline.agentic.query_understanding import parse_time_to_ms, understand_query


class AgenticQueryUnderstandingTests(unittest.TestCase):
    def test_timestamp_parser_returns_integer_milliseconds(self) -> None:
        parsed = parse_time_to_ms("What happens at 02:41:16 and after 30 seconds?")
        self.assertEqual(parsed[0]["target_ms"], 9_676_000)
        self.assertEqual(parsed[1]["target_ms"], 30_000)

    def test_visual_and_before_after_question_is_classified(self) -> None:
        result = understand_query(
            raw_query="Where did he draw the blue graph and what happened after that?"
        )
        self.assertIn("visual_memory", result["query_types"])
        self.assertIn("before_after", result["query_types"])
        self.assertTrue(result["requires_visual_search"])
        self.assertTrue(result["requires_multi_moment_reasoning"])

    def test_unknown_query_does_not_block_retrieval(self) -> None:
        result = understand_query(raw_query="mcp api")
        self.assertIn("unknown", result["query_types"])
        self.assertTrue(result["requires_transcript_search"])

    def test_follow_up_resolves_previous_citation(self) -> None:
        resolved = resolve_conversation_references(
            raw_query="What does he say after that?",
            conversation_context=[
                {
                    "query": "Where is MCP explained?",
                    "citations": [
                        {
                            "source_id": "chunk_000008",
                            "source_type": "semantic_chunk",
                            "start_ms": 299925,
                            "end_ms": 335965,
                        }
                    ],
                }
            ],
        )
        self.assertFalse(resolved["needs_clarification"])
        self.assertIn("previously cited moment", resolved["standalone_query"])
        self.assertEqual(
            resolved["resolved_references"]["previous_moment"]["source_id"],
            "chunk_000008",
        )
        understanding = understand_query(
            raw_query="What does he say after that?",
            standalone_query=resolved["standalone_query"],
            conversation_resolution=resolved,
        )
        self.assertFalse(understanding["is_ambiguous_without_context"])
        self.assertTrue(understanding["reference_resolved"])

    def test_unresolved_follow_up_requests_clarification(self) -> None:
        resolved = resolve_conversation_references(
            raw_query="What does that mean?",
            conversation_context=[],
        )
        self.assertTrue(resolved["needs_clarification"])
        self.assertFalse(resolved["reference_resolved"])
        self.assertIn("that", resolved["unresolved_references"])

        understanding = understand_query(
            raw_query="What does that mean?",
            standalone_query=resolved["standalone_query"],
            conversation_resolution=resolved,
        )
        self.assertTrue(understanding["is_ambiguous_without_context"])
        self.assertIn("follow_up", understanding["query_types"])


if __name__ == "__main__":
    unittest.main()
