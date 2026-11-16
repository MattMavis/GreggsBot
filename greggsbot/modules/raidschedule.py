from datetime import datetime, timedelta

GRACE = timedelta(minutes=30)
COMING = ("present", "late")
# {link} becomes the raid planning hub link
DAY_MESSAGE = (
    "🗓️ Any absences for tonight's raid after this point will be classed as a late absence (LA). "
    "Absence without informing an officer before the raid will count as an unauthorised absence (UA). {link}"
)
HOUR_MESSAGE = "📣 Raid starts in an hour, please check the calendar and be ready 15 minutes in advance!"


def event_start(event, tz):
    try:
        naive = datetime.strptime(f"{event['date']} {event['startTime']}", "%Y-%m-%d %H:%M")
    except (KeyError, TypeError, ValueError):
        return None
    return naive.replace(tzinfo=tz)


def upcoming(events, tz, now):
    """Planned events that have not started yet, soonest first, as (start, event)."""
    found = []
    for event in events:
        start = event_start(event, tz)
        if start and start > now and event.get("status") != "cancelled":
            found.append((start, event))
    return sorted(found, key=lambda pair: pair[0])


def signup_line(event):
    people = (event.get("signups") or []) + (event.get("guests") or [])
    count = lambda *statuses: sum(1 for p in people if p.get("status") in statuses)
    parts = [f"{count(*COMING)}/{event.get('rosterSize', len(people))} coming"]
    for status in ("tentative", "standby", "absent"):
        if count(status):
            parts.append(f"{count(status)} {status}")
    if not event.get("autoConfirmed"):
        waiting = sum(1 for s in event.get("signups") or [] if not s.get("responded"))
        if waiting:
            parts.append(f"{waiting} not answered")
    return " · ".join(parts)


def parse_reminders(text):
    """'14:00,1' -> [("at", (14, 0)), ("before", 1.0)]: a time on the raid day, or hours before the start."""
    reminders = []
    for part in text.split(","):
        part = part.strip()
        if ":" in part:
            moment = datetime.strptime(part, "%H:%M")
            reminders.append(("at", (moment.hour, moment.minute)))
        elif part:
            reminders.append(("before", float(part)))
    return reminders


def fire_time(start, reminder, local_tz=None):
    kind, value = reminder
    if kind == "at":
        # clock times are the bot's own time (REMINDER_TZ or the machine's), not the group's server zone
        return start.astimezone(local_tz).replace(hour=value[0], minute=value[1])
    return start - timedelta(hours=value)


def unsent(events, tz, now, reminders, sent, local_tz=None):
    """(start, fire_at, event, reminder, key) for each reminder not yet sent, key being what gets saved."""
    for start, event in upcoming(events, tz, now):
        for reminder in reminders:
            key = f"{event.get('eventId')}|{reminder[0]}{reminder[1]}"
            if key not in sent:
                yield start, fire_time(start, reminder, local_tz), event, reminder, key


def due_reminders(events, tz, now, reminders, sent, local_tz=None):
    """(event, reminder, key) for each reminder whose moment has arrived and has not been sent."""
    return [
        (event, reminder, key)
        for start, fire_at, event, reminder, key in unsent(events, tz, now, reminders, sent, local_tz)
        if fire_at <= now < min(start, fire_at + GRACE)
    ]


def next_fire_time(events, tz, now, reminders, sent, local_tz=None):
    """When the next unsent reminder is due, or None."""
    times = [
        fire_at
        for start, fire_at, _, _, _ in unsent(events, tz, now, reminders, sent, local_tz)
        if now < fire_at < start
    ]
    return min(times) if times else None


def status_changes(events, known):
    """Events whose status flipped since last time, plus the statuses to remember.

    An event seen for the first time is only remembered, never announced.
    """
    changed = []
    seen = {}
    for event in events:
        event_id, status = str(event.get("eventId")), event.get("status")
        seen[event_id] = status
        if known.get(event_id) not in (None, status) and status in ("planned", "cancelled"):
            changed.append(event)
    return changed, seen


def stamp(start, style):
    return f"<t:{int(start.timestamp())}:{style}>"


def title(event):
    name = event.get("name") or "Raid"
    return f"**{name}** ({event['difficulty']})" if event.get("difficulty") else f"**{name}**"


def night_date(start, local_tz=None):
    return start.astimezone(local_tz).strftime("%Y-%m-%d")


def find_night(nights, text, local_tz=None):
    """Matches '2026-11-17', '17/11' or '17/11/2026' against the upcoming nights."""
    for start, event in nights:
        local = start.astimezone(local_tz)
        if text in (f"{local:%Y-%m-%d}", f"{local.day}/{local.month}", f"{local:%d/%m}", f"{local:%d/%m/%Y}"):
            return start, event
    return None
