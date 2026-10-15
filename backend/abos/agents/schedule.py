"""Schedule calculations in the company's time zone (SPEC step 5 operating modes). Pure functions, no DB.

- Weekly tasks run at their local time on the listed days. In a `business_hours` execution window an occurrence on a
  closed day or a holiday is skipped (the next week's run covers it).
- Monthly tasks that fall on a closed day or holiday are deferred to the next opening — month-end work must not
  silently disappear because the 1st is a public holiday.
- Event-driven routine work noticed after hours waits for the next opening (`defer_to_business_hours`); critical
  alerts are not deferred (handled by the caller per `Operating.critical_alerts`).
All returned datetimes are timezone-aware UTC.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SEARCH_DAYS = 400


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def hours_for(day: date, operating_schedule: dict[str, Any] | None, holidays: set[date]) -> tuple[time, time] | None:
    """Opening hours on a local date, or None when closed (no hours set for that weekday, or a holiday)."""
    if day in holidays or not operating_schedule:
        return None
    h = operating_schedule.get(DAYS[day.weekday()])
    if not h:
        return None
    return _t(h["open"]), _t(h["close"])


def holiday_dates(holidays: list[dict[str, Any]] | None) -> set[date]:
    out = set()
    for h in holidays or []:
        d = h.get("date")
        out.add(d if isinstance(d, date) else date.fromisoformat(str(d)))
    return out


def within_hours(local_time: time, hours: tuple[time, time] | None) -> bool:
    return hours is not None and hours[0] <= local_time < hours[1]


def defer_to_business_hours(at: datetime, tz: str, operating_schedule: dict[str, Any] | None,
                            holidays: set[date]) -> datetime | None:
    """`at` if it falls inside opening hours, otherwise the next opening. None if the company never opens."""
    zone = ZoneInfo(tz)
    local = at.astimezone(zone)
    for offset in range(SEARCH_DAYS):
        day = local.date() + timedelta(days=offset)
        hours = hours_for(day, operating_schedule, holidays)
        if hours is None:
            continue
        if offset == 0:
            if within_hours(local.time(), hours):
                return at.astimezone(UTC)
            if local.time() >= hours[1]:
                continue
        return datetime.combine(day, hours[0], zone).astimezone(UTC)
    return None


def next_runs(schedule: dict[str, Any], *, tz: str, after: datetime, n: int = 5, window: str = "business_hours",
              operating_schedule: dict[str, Any] | None = None, holidays: set[date] | None = None) -> list[datetime]:
    zone = ZoneInfo(tz)
    holidays = holidays or set()
    start = after.astimezone(zone).date()
    at = _t(schedule["time"])
    out: list[datetime] = []
    for offset in range(SEARCH_DAYS):
        if len(out) >= n:
            break
        day = start + timedelta(days=offset)
        if schedule["kind"] == "weekly":
            if DAYS[day.weekday()] not in schedule["days"]:
                continue
            candidate = datetime.combine(day, at, zone)
            if candidate <= after:
                continue
            if window == "business_hours" and not within_hours(at, hours_for(day, operating_schedule, holidays)):
                continue  # closed day / holiday / outside hours: skipped
            out.append(candidate.astimezone(UTC))
        else:  # monthly
            if day.day != schedule["day"]:
                continue
            candidate = datetime.combine(day, at, zone)
            if candidate <= after:
                continue
            if window == "business_hours" and not within_hours(at, hours_for(day, operating_schedule, holidays)):
                deferred = defer_to_business_hours(candidate, tz, operating_schedule, holidays)
                if deferred is None:
                    continue
                candidate = deferred
            out.append(candidate.astimezone(UTC))
    return out


def outside_hours(schedule: dict[str, Any], operating_schedule: dict[str, Any] | None) -> list[str]:
    """Weekly days on which the scheduled time is outside opening hours (closed day or before/after hours)."""
    if schedule["kind"] != "weekly":
        return []
    at = _t(schedule["time"])
    bad = []
    for d in schedule["days"]:
        h = (operating_schedule or {}).get(d)
        if not h or not (_t(h["open"]) <= at < _t(h["close"])):
            bad.append(d)
    return bad
