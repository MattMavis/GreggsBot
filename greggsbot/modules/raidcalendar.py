import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord

from ..resources import HttpError
from .base import TROUBLE, ResponderModule

logger = logging.getLogger(__name__)

API = "https://api.wowutils.com/v1"
POLL_SECONDS = 300
GRACE = timedelta(minutes=30)
STATE_FILE = os.path.join("state", "raid_reminders.json")
COMING = ("present", "late")


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


def due_reminders(events, tz, now, reminders, sent, local_tz=None):
    """(event, start, key) for each reminder whose moment has arrived and has not been sent."""
    due = []
    for start, event in upcoming(events, tz, now):
        for reminder in reminders:
            fire_at = fire_time(start, reminder, local_tz)
            key = f"{event.get('eventId')}|{reminder[0]}{reminder[1]}"
            if fire_at <= now < min(start, fire_at + GRACE) and key not in sent:
                due.append((event, start, key))
    return due


def stamp(start, style):
    return f"<t:{int(start.timestamp())}:{style}>"


def title(event):
    name = event.get("name") or "Raid"
    return f"**{name}** ({event['difficulty']})" if event.get("difficulty") else f"**{name}**"


class RaidCalendarModule(ResponderModule):
    name = "Raid Calendar"
    commands = ("raids",)

    def __init__(self, bot):
        super().__init__(bot)
        self.group_id = None
        self.etag = None
        self.cached = ([], timezone.utc)
        self.sent = self.load_sent()
        self.task = None

    async def help_text(self):
        return self.name, f"__Description__: Upcoming raid nights and who's signed up.\n__Usage__: `{self.config.prefix}raids`"

    async def start(self):
        if self.config.raid_channel:
            self.task = asyncio.create_task(self.poll())
        else:
            logger.warning("RAID_CHANNEL is not set: raid reminders are off, %sraids still works", self.config.prefix)

    async def request(self, path, etag=None):
        headers = {"Authorization": f"Bearer {self.config.wowutils_key}"}
        if etag:
            headers["If-None-Match"] = etag
        async with self.bot.session.get(API + path, headers=headers) as resp:
            if resp.status == 304:
                return None, etag
            if resp.status != 200:
                raise HttpError(resp.status)
            return await resp.json(content_type=None), resp.headers.get("ETag")

    async def fetch_events(self):
        if self.group_id is None:
            root, _ = await self.request("")
            self.group_id = root["group"]["groupId"]
        data, self.etag = await self.request(
            f"/groups/{self.group_id}/calendar-events?upcoming=true&limit=30", self.etag
        )
        if data is not None:
            try:
                tz = ZoneInfo(data.get("serverTimeZone") or "UTC")
            except Exception:
                tz = timezone.utc
            self.cached = (data.get("data") or [], tz)
        return self.cached

    async def respond(self, message, word, args):
        fetched = await self.fetch_or_reply(message, self.fetch_events())
        if fetched is None:
            return
        events, tz = fetched
        nights = upcoming(events, tz, datetime.now(timezone.utc))[:5]
        if not nights:
            await message.reply("No raid nights on the calendar. Go outside.")
            return
        lines = [f"{stamp(start, 'F')} ({stamp(start, 'R')}) - {title(e)}\n{signup_line(e)}" for start, e in nights]
        embed = discord.Embed(title="Upcoming raid nights", description="\n\n".join(lines), color=0xFAA61A)
        await message.reply(embed=embed)

    async def poll(self):
        while True:
            try:
                await self.send_due()
            except HttpError as e:
                hint = " (check WOWUTILS_KEY and that API sharing is on)" if e.status in (401, 403) else ""
                logger.error("[%s] wowutils answered %s%s", self.name, e.status, hint)
            except Exception:
                logger.exception("[%s] reminder check failed", self.name)
            await asyncio.sleep(POLL_SECONDS)

    async def send_due(self):
        events, tz = await self.fetch_events()
        now = datetime.now(timezone.utc)
        for event, start, key in due_reminders(
            events, tz, now, self.config.raid_reminders, self.sent, self.config.tz
        ):
            await self.send_reminder(event, start)
            self.sent.add(key)
        live = {str(e.get("eventId")) for _, e in upcoming(events, tz, now)}
        self.sent = {key for key in self.sent if key.split("|")[0] in live}
        self.save_sent()

    async def send_reminder(self, event, start):
        channel = self.bot.get_channel(self.config.raid_channel)
        if channel is None:
            logger.error("[%s] RAID_CHANNEL %s not found", self.name, self.config.raid_channel)
            return

        lines = []
        role = discord.utils.get(channel.guild.roles, name=self.config.raid_role) if self.config.raid_role else None
        if role is not None:
            lines.append(role.mention)
        elif self.config.raid_role:
            logger.error("[%s] role %r not found", self.name, self.config.raid_role)
        lines.append(f"⏰ {title(event)} starts {stamp(start, 'R')} - {stamp(start, 't')}")
        lines.append(signup_line(event))
        await channel.send(
            "\n".join(lines)[:2000], allowed_mentions=discord.AllowedMentions(roles=True)
        )

    def load_sent(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, ValueError):
            return set()

    def save_sent(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self.sent), f)
