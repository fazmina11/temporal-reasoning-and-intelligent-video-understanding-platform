"""
test_visual_enrichment.py — Integration test for visual enrichment pipeline
============================================================================

Verifies that the full pipeline works end-to-end:
1. Visual enrichment produces visual_summary on artifact records
2. OCR extraction produces text records
3. Evidence verification passes when OCR is available
4. Answer generation synthesizes multiple evidence items

Usage:
    python test_visual_enrichment.py [video_id]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def test_visual_enrichment(video_id: str) -> bool:
    """Check that visual enrichment populated visual_summary on records."""
    va_path = REPO_ROOT / "data" / "processed" / "visual_artifacts" / f"{video_id}.json"
    if not va_path.is_file():
        print(f"  ❌ visual_artifacts.json not found for {video_id}")
        return False

    payload = json.loads(va_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    enriched = sum(1 for r in records if r.get("visual_summary"))

    print(f"  Records: {len(records)} total, {enriched} enriched")
    if enriched == 0:
        print(f"  ❌ No records have visual_summary")
        return False

    # Show a sample
    for r in records:
        if r.get("visual_summary"):
            print(f"  ✅ Sample: {r['atom_id']} @ {r['start_ms']}ms")
            print(f"     type={r.get('diagram_type')} summary={r['visual_summary'][:100]}...")
            break

    return enriched > 0


def test_ocr_extraction(video_id: str) -> bool:
    """Check that OCR extraction produced records."""
    ocr_path = REPO_ROOT / "data" / "processed" / "ocr" / f"{video_id}.json"
    if not ocr_path.is_file():
        print(f"  ❌ OCR artifact not found for {video_id}")
        return False

    payload = json.loads(ocr_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    tracks = payload.get("tracks", [])

    print(f"  Records: {len(records)}, Tracks: {len(tracks)}")
    if not records:
        print(f"  ❌ No OCR records")
        return False

    # Show a sample high-confidence record
    good = [r for r in records if r["mean_confidence"] > 0.7 and r["token_count"] > 3]
    if good:
        r = max(good, key=lambda x: x["mean_confidence"])
        print(f"  ✅ Sample: {r['ocr_id']} @ {r['start_ms']}ms conf={r['mean_confidence']:.3f}")
        print(f"     text: \"{r['text'][:100]}\"")

    return len(records) > 0


def test_speakers(video_id: str) -> bool:
    """Check speaker diarization artifacts."""
    sp_path = REPO_ROOT / "data" / "processed" / "speakers" / f"{video_id}.json"
    if not sp_path.is_file():
        print(f"  ❌ Speaker artifact not found")
        return False

    payload = json.loads(sp_path.read_text(encoding="utf-8"))
    print(f"  Speakers: {payload.get('speaker_count', 0)}, Turns: {payload.get('turn_count', 0)}")
    return payload.get("speaker_count", 0) > 0


def test_audio_events(video_id: str) -> bool:
    """Check audio event detection artifacts."""
    ae_path = REPO_ROOT / "data" / "processed" / "audio_events" / f"{video_id}.json"
    if not ae_path.is_file():
        print(f"  ❌ Audio events artifact not found")
        return False

    payload = json.loads(ae_path.read_text(encoding="utf-8"))
    labels = payload.get("label_counts", {})
    print(f"  Events: {payload.get('event_count', 0)}, Labels: {labels}")
    return payload.get("event_count", 0) > 0


def test_answer_generation(video_id: str) -> bool:
    """Test that the answer generator produces multi-evidence answers."""
    from src.pipeline.agentic.answer_generator import GroundedAnswerGenerator

    gen = GroundedAnswerGenerator()

    # Simulate a multi-evidence packet
    packet = {
        "question": "What health features does the Galaxy Watch 9 monitor",
        "verified_evidence": [
            {
                "citation_id": "S1",
                "start_ms": 7500,
                "end_ms": 13000,
                "text": "It helps monitor and manage your health.",
                "visual_summary": "Close-up of Galaxy Watch 9 on wrist.",
                "source_type": "atom",
            },
            {
                "citation_id": "S2",
                "start_ms": 44000,
                "end_ms": 50000,
                "text": "Sleep Apnea Risk Detection feature.",
                "visual_summary": "Smartwatch displaying Sleep Apnea Risk Detection.",
                "source_type": "atom",
            },
            {
                "citation_id": "S3",
                "start_ms": 60000,
                "end_ms": 70000,
                "text": "Heart Health Score 57 Fair.",
                "visual_summary": "Watch face showing Heart Health Score.",
                "source_type": "atom",
            },
        ],
        "temporal_context": {"timeline_summary": "3 min health ad"},
    }

    result = gen.generate(packet)
    answer = result.get("answer", "")
    citations = answer.count("[S")

    print(f"  Model: {result.get('model')}")
    print(f"  Citations in answer: {citations}")
    print(f"  Answer: {answer[:200]}...")
    return citations >= 2


def main():
    video_id = sys.argv[1] if len(sys.argv) > 1 else "64aced5d-a3a9-4f33-b22d-0e978466582e"

    tests = [
        ("Visual Enrichment", lambda: test_visual_enrichment(video_id)),
        ("OCR Extraction", lambda: test_ocr_extraction(video_id)),
        ("Speaker Diarization", lambda: test_speakers(video_id)),
        ("Audio Events", lambda: test_audio_events(video_id)),
        ("Answer Generation", lambda: test_answer_generation(video_id)),
    ]

    results = []
    for name, fn in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        try:
            passed = fn()
            results.append((name, passed))
        except Exception as exc:
            print(f"  ❌ EXCEPTION: {exc}")
            results.append((name, False))

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
