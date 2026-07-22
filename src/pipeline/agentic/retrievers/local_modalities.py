from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...json_artifacts import read_json
from ...media_manifest import load_manifest
from ..contracts import RetrievalStep, SourceType
from .base import RetrieverAdapter, make_candidate


class OCRRetriever(RetrieverAdapter):
    name = "ocr_sparse"

    def retrieve(self, *, video_id: str, step: RetrievalStep, query_understanding: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        path = Path(manifest["artifacts"].get("ocr_path", ""))
        if not path.is_file():
            return []
        terms = _terms(step.query) - {
            "text", "screen", "slide", "says", "say", "said", "written", "read", "show", "shown", "displayed"
        }
        rows = []
        for record in read_json(path).get("records", []):
            score = _text_score(terms, record.get("text", ""))
            if score <= 0:
                continue
            score = min(1.0, 0.75 * score + 0.25 * float(record.get("mean_confidence", 0.0)))
            rows.append((score, record))
        rows.sort(key=lambda item: (-item[0], int(item[1].get("timestamp_ms", item[1]["start_ms"]))))
        return [
            make_candidate(
                candidate_id=f"cand_ocr_{rank}", video_id=video_id, source_type=SourceType.OCR,
                source_id=row["ocr_id"], start_ms=row["start_ms"], end_ms=max(row["start_ms"] + 1, row["end_ms"]),
                parent_chunk_id=row.get("parent_chunk_id"), parent_event_id=row.get("parent_event_id"),
                text=row["text"], visual_summary=f"On-screen text: {row['text']}", ocr_text=[row["text"]],
                media_refs={"frames": [row["frame_id"]]}, retriever=step.retriever, rank=rank,
                raw_score=score, query_variant=step.query, versions={"pipeline": manifest["pipeline_version"]},
            )
            for rank, (score, row) in enumerate(rows[: step.top_k], start=1)
        ]


class SpeakerRetriever(RetrieverAdapter):
    name = "speaker"

    def retrieve(self, *, video_id: str, step: RetrievalStep, query_understanding: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        path = Path(manifest["artifacts"].get("speakers_path", ""))
        if not path.is_file():
            return []
        terms = _terms(step.query) - {"speaker", "say", "said", "says", "lecturer", "presenter", "talking"}
        rows = []
        for turn in read_json(path).get("turns", []):
            identity = f"{turn.get('speaker_id', '')} {turn.get('text', '')}"
            score = _text_score(terms, identity) if terms else 0.5
            if score <= 0:
                continue
            rows.append((score, turn))
        rows.sort(key=lambda item: (-item[0], item[1]["start_ms"]))
        return [
            make_candidate(
                candidate_id=f"cand_speaker_{rank}", video_id=video_id, source_type=SourceType.SPEAKER_TURN,
                source_id=turn["turn_id"], start_ms=turn["start_ms"], end_ms=turn["end_ms"],
                parent_chunk_id=turn.get("parent_chunk_id"), parent_event_id=turn.get("parent_event_id"),
                text=f"{turn['speaker_id']}: {turn.get('text', '')}", transcript=turn.get("text"),
                entities=[turn["speaker_id"]], media_refs={"speaker_id": turn["speaker_id"]},
                retriever=step.retriever, rank=rank, raw_score=score, query_variant=step.query,
                versions={"pipeline": manifest["pipeline_version"]},
            )
            for rank, (score, turn) in enumerate(rows[: step.top_k], start=1)
        ]


class AudioEventRetriever(RetrieverAdapter):
    name = "audio_event"

    def retrieve(self, *, video_id: str, step: RetrievalStep, query_understanding: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = load_manifest(repo_root=self.repo_root, video_id=video_id)
        path = Path(manifest["artifacts"].get("audio_events_path", ""))
        if not path.is_file():
            return []
        terms = _terms(step.query)
        synonyms = _audio_synonyms(terms)
        rows = []
        for event in read_json(path).get("events", []):
            label_text = event["label"].replace("_", " ")
            score = _text_score(synonyms, label_text)
            if score <= 0 and not ({"audio", "sound", "hear"} & terms):
                continue
            if score <= 0:
                score = 0.3
            score = min(1.0, 0.7 * score + 0.3 * float(event.get("confidence", 0.0)))
            rows.append((score, event))
        rows.sort(key=lambda item: (-item[0], item[1]["start_ms"]))
        return [
            make_candidate(
                candidate_id=f"cand_audio_{rank}", video_id=video_id, source_type=SourceType.AUDIO_EVENT,
                source_id=event["audio_event_id"], start_ms=event["start_ms"], end_ms=event["end_ms"],
                parent_chunk_id=event.get("parent_chunk_id"), parent_event_id=event.get("parent_event_id"),
                text=f"Audio event: {event['label'].replace('_', ' ')}.",
                media_refs={"audio_event": event["label"]}, retriever=step.retriever, rank=rank,
                raw_score=score, query_variant=step.query, versions={"pipeline": manifest["pipeline_version"]},
            )
            for rank, (score, event) in enumerate(rows[: step.top_k], start=1)
        ]


def _terms(text: str) -> set[str]:
    stop = {"what", "where", "when", "which", "does", "did", "the", "and", "from", "that", "this", "with", "about"}
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]{2,}", text) if term.lower() not in stop}


def _text_score(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    normalized = text.lower()
    overlap = sum(term in normalized for term in terms)
    phrase_bonus = 0.25 if " ".join(terms) in normalized else 0.0
    return min(1.0, overlap / len(terms) + phrase_bonus)


def _audio_synonyms(terms: set[str]) -> set[str]:
    expanded = set(terms)
    mapping = {
        "quiet": {"silence"}, "silent": {"silence"}, "pause": {"silence"},
        "music": {"music", "tonal"}, "song": {"music", "tonal"},
        "noise": {"background", "transient"}, "sound": {"background", "transient", "music"},
        "speaking": {"speech"}, "voice": {"speech"}, "talking": {"speech"},
    }
    for term in terms:
        expanded.update(mapping.get(term, set()))
    return expanded
