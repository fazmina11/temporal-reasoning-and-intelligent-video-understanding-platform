import unittest
from datetime import datetime, timezone

from src.pipeline.evaluation.evaluate_ask import EvaluationResult, EvaluationRun
from src.pipeline.evaluation.metrics import (
    EvaluationMetrics,
    calculate_metrics,
    citation_validity_rate,
    timestamp_hit_rate,
)


def make_run() -> EvaluationRun:
    first = EvaluationResult(
        question_id="q_001", query="What is RAG?", expected_outcome="grounded_answer",
        predicted_outcome="grounded_answer", latency_ms=10.0,
        raw_response={"answer": "RAG uses retrieval."}, confidence=0.8,
        citations=[{"source_id": "chunk_001", "source_type": "semantic_chunk", "start_ms": 1500, "end_ms": 2500}],
        trace_metadata={"answer_quality": {"fallback_used": False}}, success=True,
        expected_start_ms_min=1000, expected_start_ms_max=3000,
        required_terms=["RAG", "retrieval"], forbidden_terms=["fine tuning"],
        expected_source_types=["semantic_chunk"],
    )
    second = EvaluationResult(
        question_id="q_002", query="General question", expected_outcome="unrelated_to_video",
        predicted_outcome="unrelated_to_video", latency_ms=20.0,
        raw_response={"answer": "I cannot answer from this video."}, confidence=0.6,
        success=True,
    )
    third = EvaluationResult(
        question_id="q_003", query="Explain concept", expected_outcome="grounded_answer",
        predicted_outcome="video_evidence_not_found", latency_ms=30.0,
        raw_response={"answer": "This is fine tuning."}, confidence=0.4,
        citations=[{"source_id": "bad", "source_type": "ocr"}],
        trace_metadata={"answer_quality": {"fallback_used": True}}, success=True,
        required_terms=["concept"], forbidden_terms=["fine tuning"],
        expected_source_types=["semantic_chunk"],
    )
    return EvaluationRun(
        video_id="video_001", run_timestamp=datetime.now(timezone.utc), runner_version="test",
        results=[first, second, third],
    )


class EvaluationMetricsTests(unittest.TestCase):
    def test_calculate_metrics(self) -> None:
        metrics = calculate_metrics(make_run())

        self.assertIsInstance(metrics, EvaluationMetrics)
        self.assertEqual(metrics.outcome_accuracy, 0.6667)
        self.assertEqual(metrics.timestamp_hit_rate, 1.0)
        self.assertEqual(metrics.citation_presence_rate, 1.0)
        self.assertEqual(metrics.citation_validity_rate, 0.5)
        self.assertEqual(metrics.required_term_coverage, 0.6667)
        self.assertEqual(metrics.unsupported_claim_rate, 0.5)
        self.assertEqual(metrics.negative_question_abstention_rate, 1.0)
        self.assertEqual(metrics.average_confidence, 0.6)
        self.assertEqual(metrics.average_latency_ms, 20.0)
        self.assertEqual(metrics.fallback_rate, 0.3333)

    def test_metrics_handle_empty_timestamp_and_citation_populations(self) -> None:
        result = EvaluationResult(
            question_id="q_001", query="Question", expected_outcome="unrelated_to_video",
            predicted_outcome="unrelated_to_video", latency_ms=0.0, success=True,
        )
        self.assertEqual(timestamp_hit_rate([result]), 0.0)
        self.assertEqual(citation_validity_rate([result]), 0.0)


if __name__ == "__main__":
    unittest.main()
