"""Public exports for the video QA evaluation package."""

from importlib import import_module
from typing import Any

__all__ = [
    "AskPipelineAdapter",
    "BASELINE_SCHEMA_VERSION",
    "DefaultAskPipelineAdapter",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationRunner",
    "LocalAskPipelineAdapter",
    "QADataset",
    "QAItem",
    "QAValidationError",
    "build_arg_parser",
    "compare_and_write_reports",
    "compare_reports",
    "generate_json_report",
    "generate_markdown_comparison",
    "generate_markdown_report",
    "main",
    "run_evaluation_workflow",
    "write_reports",
    "freeze_baseline",
]

_EXPORT_MODULES = {
    "BASELINE_SCHEMA_VERSION": ".baseline_manager",
    "AskPipelineAdapter": ".evaluate_ask",
    "DefaultAskPipelineAdapter": ".evaluate_ask",
    "EvaluationResult": ".evaluate_ask",
    "EvaluationRun": ".evaluate_ask",
    "EvaluationRunner": ".evaluate_ask",
    "LocalAskPipelineAdapter": ".evaluate_ask",
    "build_arg_parser": ".evaluate_ask",
    "main": ".evaluate_ask",
    "run_evaluation_workflow": ".evaluate_ask",
    "QADataset": ".qa_schema",
    "QAItem": ".qa_schema",
    "QAValidationError": ".qa_schema",
    "compare_and_write_reports": ".regression_compare",
    "compare_reports": ".regression_compare",
    "generate_markdown_comparison": ".regression_compare",
    "generate_json_report": ".report_writer",
    "generate_markdown_report": ".report_writer",
    "write_reports": ".report_writer",
    "freeze_baseline": ".baseline_manager",
}


def __getattr__(name: str) -> Any:
    """Load heavier evaluation modules only when their package export is used."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


