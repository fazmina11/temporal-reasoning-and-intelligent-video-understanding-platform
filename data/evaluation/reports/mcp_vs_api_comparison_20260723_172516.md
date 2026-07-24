# Evaluation Regression Comparison Report: mcp_vs_api

## Metadata

- **Video ID:** `mcp_vs_api`
- **Baseline Run:** Timestamp `2026-07-23T17:23:50.599594+00:00` (version `evaluation-runner-v1`)
- **Candidate Run:** Timestamp `2026-07-23T17:25:16.703270+00:00` (version `evaluation-runner-v1`)
- **Total Questions:** Baseline: 60 | Candidate: 60

## Metric Comparison Summary

| Metric | Baseline | Candidate | Delta | Status |
| --- | ---: | ---: | ---: | --- |
| Average Confidence | 0.8500 | 0.8500 | +0.0000 | **UNCHANGED** |
| Average Latency Ms | 0.00 ms | 0.00 ms | +0.00 ms | **REGRESSED** |
| Citation Presence Rate | 100.00% | 100.00% | +0.00% | **UNCHANGED** |
| Citation Validity Rate | 35.00% | 35.00% | +0.00% | **UNCHANGED** |
| Fallback Rate | 0.00% | 0.00% | +0.00% | **UNCHANGED** |
| Negative Question Abstention Rate | 0.00% | 0.00% | +0.00% | **UNCHANGED** |
| Outcome Accuracy | 66.67% | 66.67% | +0.00% | **UNCHANGED** |
| Required Term Coverage | 21.37% | 21.37% | +0.00% | **UNCHANGED** |
| Timestamp Hit Rate | 2.50% | 2.50% | +0.00% | **UNCHANGED** |
| Unsupported Claim Rate | 97.50% | 97.50% | +0.00% | **UNCHANGED** |

## Improved Metrics

_No improved metrics._

## Regressed Metrics

- **Average Latency Ms:** 0.0008 -> 0.0013 (+0.0005)

## Latency Delta

| Latency Metric | Baseline (ms) | Candidate (ms) | Delta (ms) | Status |
| --- | ---: | ---: | ---: | --- |
| Average Ms | 0.00 ms | 0.00 ms | +0.00 ms | **UNCHANGED** |
| Min Ms | 0.00 ms | 0.00 ms | +0.00 ms | **REGRESSED** |
| Max Ms | 0.00 ms | 0.01 ms | +0.00 ms | **REGRESSED** |
| P50 Ms | 0.00 ms | 0.00 ms | +0.00 ms | **UNCHANGED** |
| P90 Ms | 0.00 ms | 0.00 ms | +0.00 ms | **REGRESSED** |
| P95 Ms | 0.00 ms | 0.00 ms | +0.00 ms | **REGRESSED** |

## New Failures (Regressions)

_No new failures recorded._

## Resolved Failures (Improvements)

_No resolved failures recorded._
