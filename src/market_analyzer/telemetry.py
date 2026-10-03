"""Console and latency telemetry for external API calls (TwelveData and OpenRouter AI).

Tracks request/response lifecycles, computes running average durations,
and outputs clean, real-time console messages to help observe latency patterns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ApiMetricsTracker:
    """Tracks latency metrics and running averages for an API service."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.total_duration_seconds: float = 0.0
        self.last_duration_seconds: float = 0.0

    def record_success(self, duration_seconds: float) -> float:
        """Record a successful response and return the updated average duration."""
        self.total_requests += 1
        self.successful_requests += 1
        self.last_duration_seconds = duration_seconds
        self.total_duration_seconds += duration_seconds
        return self.average_duration_seconds

    def record_failure(self, duration_seconds: float) -> float:
        """Record a failed response."""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_duration_seconds = duration_seconds
        return self.average_duration_seconds

    @property
    def average_duration_seconds(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_duration_seconds / self.successful_requests


# Service-level metric trackers
_biquote_tracker = ApiMetricsTracker("Biquote API")
_twelvedata_tracker = ApiMetricsTracker("TwelveData API")
_finnhub_tracker = ApiMetricsTracker("Finnhub API")
_ai_tracker = ApiMetricsTracker("OpenRouter AI")


def _get_tracker(service: str) -> ApiMetricsTracker:
    s_lower = service.lower()
    if "biquote" in s_lower:
        return _biquote_tracker
    if "twelve" in s_lower:
        return _twelvedata_tracker
    if "finnhub" in s_lower:
        return _finnhub_tracker
    return _ai_tracker


def log_api_request(service: str, target: str, details: str = "") -> None:
    """Log an outgoing request to console and logger with timestamp."""
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    detail_str = f" ({details})" if details else ""
    msg = f"[{now_str}] [{service}] -> SENDING: {target}{detail_str}"
    print(msg, flush=True)
    logger.info(msg)


def log_api_response(
    service: str,
    target: str,
    duration_seconds: float,
    status: int | str = 200,
    details: str = "",
) -> None:
    """Log an incoming API response with elapsed time and session average."""
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    tracker = _get_tracker(service)
    avg_sec = tracker.record_success(duration_seconds)
    detail_str = f" | {details}" if details else ""

    msg = (
        f"[{now_str}] [{service}] <- RECEIVED: {target} | HTTP {status} in "
        f"{duration_seconds:.2f}s ({duration_seconds * 1000:.0f}ms) | "
        f"Session Avg: {avg_sec:.2f}s (Total: {tracker.successful_requests} reqs){detail_str}"
    )
    print(msg, flush=True)
    logger.info(msg)


def log_api_error(
    service: str,
    target: str,
    duration_seconds: float,
    error_msg: str,
) -> None:
    """Log an API error or retry with elapsed time."""
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    tracker = _get_tracker(service)
    tracker.record_failure(duration_seconds)

    msg = (
        f"[{now_str}] [{service}] !! ERROR: {target} after {duration_seconds:.2f}s | {error_msg}"
    )
    print(msg, flush=True)
    logger.warning(msg)


def get_telemetry_summary() -> dict[str, dict[str, float | int]]:
    """Return summary dictionary of all recorded latency metrics."""
    return {
        "biquote": {
            "total_requests": _biquote_tracker.total_requests,
            "successful_requests": _biquote_tracker.successful_requests,
            "failed_requests": _biquote_tracker.failed_requests,
            "average_duration_seconds": round(_biquote_tracker.average_duration_seconds, 3),
            "last_duration_seconds": round(_biquote_tracker.last_duration_seconds, 3),
        },
        "twelvedata": {
            "total_requests": _twelvedata_tracker.total_requests,
            "successful_requests": _twelvedata_tracker.successful_requests,
            "failed_requests": _twelvedata_tracker.failed_requests,
            "average_duration_seconds": round(_twelvedata_tracker.average_duration_seconds, 3),
            "last_duration_seconds": round(_twelvedata_tracker.last_duration_seconds, 3),
        },
        "finnhub": {
            "total_requests": _finnhub_tracker.total_requests,
            "successful_requests": _finnhub_tracker.successful_requests,
            "failed_requests": _finnhub_tracker.failed_requests,
            "average_duration_seconds": round(_finnhub_tracker.average_duration_seconds, 3),
            "last_duration_seconds": round(_finnhub_tracker.last_duration_seconds, 3),
        },
        "openrouter_ai": {
            "total_requests": _ai_tracker.total_requests,
            "successful_requests": _ai_tracker.successful_requests,
            "failed_requests": _ai_tracker.failed_requests,
            "average_duration_seconds": round(_ai_tracker.average_duration_seconds, 3),
            "last_duration_seconds": round(_ai_tracker.last_duration_seconds, 3),
        },
    }
