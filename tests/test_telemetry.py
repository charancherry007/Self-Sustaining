"""Unit tests for telemetry, metrics tracking, and console logging."""

from __future__ import annotations

import io
import sys

from market_analyzer.telemetry import (
    ApiMetricsTracker,
    get_telemetry_summary,
    log_api_error,
    log_api_request,
    log_api_response,
)


def test_api_metrics_tracker_computes_running_average() -> None:
    tracker = ApiMetricsTracker("TestService")
    assert tracker.total_requests == 0
    assert tracker.average_duration_seconds == 0.0

    # 1st call: 1.0s
    avg1 = tracker.record_success(1.0)
    assert avg1 == 1.0
    assert tracker.successful_requests == 1
    assert tracker.total_requests == 1
    assert tracker.last_duration_seconds == 1.0

    # 2nd call: 3.0s -> avg = 2.0s
    avg2 = tracker.record_success(3.0)
    assert avg2 == 2.0
    assert tracker.successful_requests == 2
    assert tracker.total_requests == 2
    assert tracker.last_duration_seconds == 3.0

    # Failure call: 0.5s -> avg remains 2.0s over successes, total requests increments
    avg3 = tracker.record_failure(0.5)
    assert avg3 == 2.0
    assert tracker.total_requests == 3
    assert tracker.failed_requests == 1
    assert tracker.last_duration_seconds == 0.5


def test_log_functions_emit_output() -> None:
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        log_api_request("TestAPI", "GET /time_series", "symbol=EUR/USD")
        log_api_response("TestAPI", "GET /time_series", 1.25, 200, "50 candles")
        log_api_error("TestAPI", "GET /time_series", 0.85, "HTTP 429")
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "-> SENDING: GET /time_series (symbol=EUR/USD)" in output
    assert "<- RECEIVED: GET /time_series | HTTP 200 in 1.25s (1250ms)" in output
    assert "!! ERROR: GET /time_series after 0.85s | HTTP 429" in output


def test_get_telemetry_summary() -> None:
    summary = get_telemetry_summary()
    assert "biquote" in summary
    assert "openrouter_ai" in summary
    assert "average_duration_seconds" in summary["biquote"]
    assert "average_duration_seconds" in summary["openrouter_ai"]
