from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..json_artifacts import read_json, write_json_atomic
from .contracts import RetrievalTrace, model_to_dict, parse_model


class TraceRepository:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def trace_dir(self, video_id: str) -> Path:
        return self.repo_root / "data" / "processed" / "retrieval_traces" / video_id

    def trace_path(self, video_id: str, trace_id: str) -> Path:
        return self.trace_dir(video_id) / f"{trace_id}.json"

    def save(self, video_id: str, trace: RetrievalTrace | dict[str, Any]) -> Path:
        if isinstance(trace, RetrievalTrace):
            payload = model_to_dict(trace)
        else:
            payload = dict(trace)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        trace_id = payload.get("trace_id")
        if not trace_id:
            raise ValueError("trace_id is required to save a retrieval trace")
        return write_json_atomic(self.trace_path(video_id, trace_id), payload)

    def load(self, video_id: str, trace_id: str) -> RetrievalTrace:
        payload = read_json(self.trace_path(video_id, trace_id))
        return parse_model(RetrievalTrace, payload)  # type: ignore[return-value]
