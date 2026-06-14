"""
East African Time (EAT) helpers.

EAT is UTC+3 with no daylight saving — Africa/Nairobi covers Kenya,
Uganda, Tanzania, Ethiopia, etc. and is a fixed +3 offset year-round.

Convention used across this project:
- All timestamps are still STORED in the database as naive UTC
  (via now_utc()), so existing columns/comparisons keep working.
- Anything that represents "what date/time is it right now for the
  user" (e.g. the date a journal entry belongs to, "today" cutoffs,
  export timestamps shown to users) should use today_eat() / now_eat().
- Templates can convert any stored UTC datetime to EAT for display
  using the `eat` Jinja filter registered in app.py.
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

EAT = ZoneInfo("Africa/Nairobi")


def now_utc():
    """Naive UTC datetime — use this for DB timestamp columns (replaces datetime.utcnow())."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_eat():
    """Current timezone-aware datetime in East African Time."""
    return datetime.now(EAT)


def today_eat():
    """Current date (no time component) in East African Time.

    Use this anywhere `date.today()` was being used to mean
    'today, for the user' — e.g. journal entry dates, daily
    rollovers, default date-range bounds.
    """
    return now_eat().date()


def to_eat(dt):
    """Convert a stored (naive UTC) datetime to an aware EAT datetime, for display.

    Returns None if dt is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EAT)


def format_eat(dt, fmt='%Y-%m-%d %H:%M EAT'):
    """Convenience formatter: stored UTC datetime -> EAT string."""
    converted = to_eat(dt)
    if converted is None:
        return ''
    return converted.strftime(fmt)