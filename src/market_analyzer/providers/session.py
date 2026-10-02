"""Trading-session awareness.

Real-time data does not mean "recent data". Outside market hours the newest bar
on the wire is legitimately hours old, so a naive staleness check would fail a
perfectly good feed. The analyzer therefore asks the provider whether the
session is open before applying a wall-clock staleness threshold.

Holiday and half-day calendars are supplied by the caller, so adding a venue is
a config change rather than a code change.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo


class SessionState(StrEnum):
    PRE = "pre"
    OPEN = "open"
    POST = "post"
    CLOSED = "closed"
    HOLIDAY = "holiday"


class MarketCalendar:
    """Regular trading hours for one venue.

    Defaults to US equities (09:30-16:00 America/New_York).
    """

    def __init__(
        self,
        timezone_name: str = "America/New_York",
        open_time: time = time(9, 30),
        close_time: time = time(16, 0),
        holidays: frozenset[date] = frozenset(),
        half_days: frozenset[date] = frozenset(),
    ) -> None:
        self.timezone_name = timezone_name
        self.tz = ZoneInfo(timezone_name)
        self.open_time = open_time
        self.close_time = close_time
        self.holidays = holidays
        self.half_days = half_days

    def state(self, now_utc: datetime | None = None) -> SessionState:
        now_utc = now_utc or datetime.now(timezone.utc)
        local = now_utc.astimezone(self.tz)
        today = local.date()

        if today in self.holidays:
            return SessionState.HOLIDAY
        if local.weekday() >= 5:  # Saturday, Sunday
            return SessionState.CLOSED

        close = time(13, 0) if today in self.half_days else self.close_time
        if local.time() < self.open_time:
            return SessionState.PRE
        if local.time() >= close:
            return SessionState.POST
        return SessionState.OPEN

    def is_open(self, now_utc: datetime | None = None) -> bool:
        return self.state(now_utc) is SessionState.OPEN

    def session_close_utc(self, now_utc: datetime | None = None) -> datetime | None:
        """UTC timestamp of the most recent completed session close."""
        now_utc = now_utc or datetime.now(timezone.utc)
        local = now_utc.astimezone(self.tz)
        for back in range(0, 10):
            day = local.date() - timedelta(days=back)
            if day in self.holidays or day.weekday() >= 5:
                continue
            close = time(13, 0) if day in self.half_days else self.close_time
            return datetime.combine(day, close, tzinfo=self.tz).astimezone(timezone.utc)
        return None


class FxMetalsCalendar:
    """FX / precious metals: 24/5 with daily break ~22:00-22:05 UTC.
    Approximation: open Sunday 22:00 UTC, close Friday 22:00 UTC.
    """

    def __init__(
        self,
        daily_break_start: time = time(22, 0),
        daily_break_end: time = time(22, 5),
    ) -> None:
        self.daily_break_start = daily_break_start
        self.daily_break_end = daily_break_end

    def state(self, now_utc: datetime | None = None) -> SessionState:
        now_utc = now_utc or datetime.now(timezone.utc)

        # Weekend: closed Fri 22:00 -> Sun 22:00 UTC
        if now_utc.weekday() == 4 and now_utc.time() >= self.daily_break_start:
            return SessionState.CLOSED
        if now_utc.weekday() == 5:
            return SessionState.CLOSED
        if now_utc.weekday() == 6 and now_utc.time() < self.daily_break_end:
            return SessionState.CLOSED

        # Daily rollover break
        if self.daily_break_start <= now_utc.time() < self.daily_break_end:
            return SessionState.CLOSED

        return SessionState.OPEN

    def is_open(self, now_utc: datetime | None = None) -> bool:
        return self.state(now_utc) is SessionState.OPEN

    def session_close_utc(self, now_utc: datetime | None = None) -> datetime | None:
        # FX doesn't have a single daily close; use current time
        return datetime.now(timezone.utc)


class CryptoCalendar:
    """Crypto: 24/7/365. Always open."""

    def state(self, now_utc: datetime | None = None) -> SessionState:
        return SessionState.OPEN

    def is_open(self, now_utc: datetime | None = None) -> bool:
        return True

    def session_close_utc(self, now_utc: datetime | None = None) -> datetime | None:
        return datetime.now(timezone.utc)


def get_calendar(session_type: str) -> MarketCalendar | FxMetalsCalendar | CryptoCalendar:
    """Return the appropriate calendar for a session type."""
    if session_type == "fx_metals":
        return FxMetalsCalendar()
    if session_type == "crypto_24_7":
        return CryptoCalendar()
    # Default: US equity
    return MarketCalendar()
