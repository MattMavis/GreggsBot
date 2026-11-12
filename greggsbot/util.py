import math
import random


def ordinal(n):
    n = int(n)
    if n % 100 in (11, 12, 13):
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def weighted_pick(entries):
    usable = []
    weights = []
    for entry in entries:
        try:
            weight = float(entry.get("weight"))
        except (TypeError, ValueError):
            continue
        if weight > 0 and math.isfinite(weight):
            usable.append(entry)
            weights.append(weight)
    if not usable:
        return None
    return random.choices(usable, weights=weights)[0]


def truncate(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def tags_of(entry):
    tags = entry.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    elif isinstance(tags, dict):
        tags = tags.values()
    elif not isinstance(tags, list):
        return []
    return [str(t) for t in tags if t is not None]


def has_tag(entry, word):
    return word.lower() in [t.lower() for t in tags_of(entry)]


def fmt_number(n):
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def format_date(dt):
    return f"{ordinal(dt.day)} {dt:%b %Y %H:%M:%S}"
