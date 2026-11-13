import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord

from ..resources import HttpError
from .base import ResponderModule, can_manage

logger = logging.getLogger(__name__)

API = "https://api.wowutils.com/v1"
POLL_SECONDS = 300
GRACE = timedelta(minutes=30)
STATE_FILE = os.path.join("state", "raid_reminders.json")
COMING = ("present", "late")
HUB = "https://wowutils.com/viserio-cooldowns/raid"
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


def due_reminders(events, tz, now, reminders, sent, local_tz=None):
    """(event, reminder, key) for each reminder whose moment has arrived and has not been sent."""
    due = []
    for start, event in upcoming(events, tz, now):
        for reminder in reminders:
            fire_at = fire_time(start, reminder, local_tz)
            key = f"{event.get('eventId')}|{reminder[0]}{reminder[1]}"
            if fire_at <= now < min(start, fire_at + GRACE) and key not in sent:
                due.append((event, reminder, key))
    return due


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


class RaidCalendarModule(ResponderModule):
    name = "Raid Calendar"
    commands = ("raids", "raidtest", "reminders")

    def __init__(self, bot):
        super().__init__(bot)
        self.group_id = None
        self.etag = None
        self.cached = ([], timezone.utc)
        self.sent, self.muted, self.statuses = self.load_state()
        self.task = None

    async def help_text(self):
        p = self.config.prefix
        content = (
            "__Description__: Upcoming raid nights and who's signed up.\n"
            f"__Usage__: `{p}raids`\n"
            f"__Officers__: `{p}reminders off 17/11` or `{p}reminders on 17/11` to mute one night's reminders, "
            f"`{p}raidtest` to post a test reminder"
        )
        return self.name, content

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

    async def group(self):
        if self.group_id is None:
            root, _ = await self.request("")
            self.group_id = root["group"]["groupId"]
        return self.group_id

    async def fetch_events(self):
        data, self.etag = await self.request(
            f"/groups/{await self.group()}/calendar-events?upcoming=true&limit=30", self.etag
        )
        if data is not None:
            try:
                tz = ZoneInfo(data.get("serverTimeZone") or "UTC")
            except Exception:
                tz = timezone.utc
            self.cached = (data.get("data") or [], tz)
        return self.cached

    async def respond(self, message, word, args):
        if word != "raids" and not can_manage(message.author):
            await message.reply("Nice try. That one is for officers.")
            return
        fetched = await self.fetch_or_reply(message, self.fetch_events())
        if fetched is None:
            return
        events, tz = fetched
        nights = upcoming(events, tz, datetime.now(timezone.utc))
        if not nights:
            await message.reply("No raid nights on the calendar. Go outside.")
        elif word == "raidtest":
            await self.test_reminder(message, nights)
        elif word == "reminders":
            await self.toggle_reminders(message, nights, args)
        else:
            lines = [
                f"{stamp(start, 'F')} ({stamp(start, 'R')}) - {title(e)}{self.muted_mark(e)}\n{signup_line(e)}"
                for start, e in nights[:5]
            ]
            embed = discord.Embed(title="Upcoming raid nights", description="\n\n".join(lines), color=0xFAA61A)
            await message.reply(embed=embed)

    def muted_mark(self, event):
        return " 🔕" if str(event.get("eventId")) in self.muted else ""

    async def test_reminder(self, message, nights):
        if not self.config.raid_channel:
            await message.reply("RAID_CHANNEL isn't set, so I have nowhere to post reminders.")
            return
        posted = [await self.send_reminder(kind, test=True) for kind in ("at", "before")]
        if all(posted):
            await message.reply(f"Both test reminders posted in <#{self.config.raid_channel}>.")
        else:
            await message.reply("I couldn't post in the reminder channel. Check RAID_CHANNEL and my permissions there.")

    async def toggle_reminders(self, message, nights, args):
        usage = f"Usage: `{self.config.prefix}reminders off 17/11` or `{self.config.prefix}reminders on 17/11`"
        if len(args) != 2 or args[0].lower() not in ("on", "off"):
            await message.reply(usage)
            return
        night = find_night(nights, args[1], self.config.tz)
        if night is None:
            await message.reply(f"There's no raid night on {args[1]}. {usage}")
            return
        start, event = night
        if args[0].lower() == "off":
            self.muted.add(str(event.get("eventId")))
        else:
            self.muted.discard(str(event.get("eventId")))
        self.save_state()
        state = "off 🔕" if args[0].lower() == "off" else "back on 🔔"
        await message.reply(f"Reminders for {title(event)} on {stamp(start, 'F')} are {state}.")

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
        changed, self.statuses = status_changes(events, self.statuses)
        for event in changed:
            start = event_start(event, tz)
            if start and start > now:
                await self.announce_status(event, start)
        wanted = [e for e in events if str(e.get("eventId")) not in self.muted]
        for event, reminder, key in due_reminders(
            wanted, tz, now, self.config.raid_reminders, self.sent, self.config.tz
        ):
            await self.send_reminder(reminder[0])
            self.sent.add(key)
        live = {str(e.get("eventId")) for _, e in upcoming(events, tz, now)}
        self.sent = {key for key in self.sent if key.split("|")[0] in live}
        self.muted &= live
        self.save_state()

    async def hub_link(self):
        link = f"{HUB}?groupId={self.group_id}"
        try:
            reset, _ = await self.request(f"/groups/{self.group_id}/latest-reset")
            link += f"&resetId={reset['resetId']}&setupId={self.config.raid_setup_id}"
        except Exception:
            logger.exception("[%s] could not look up the current reset for the link", self.name)
        return link

    async def post(self, text, test=False):
        """Posts in the reminder channel with the raid roles pinged. Returns whether it worked."""
        channel = self.bot.get_channel(self.config.raid_channel)
        if channel is None:
            logger.error("[%s] RAID_CHANNEL %s not found", self.name, self.config.raid_channel)
            return False

        pings = []
        for name in self.config.raid_roles:
            if name.isdigit():
                role = channel.guild.get_role(int(name))
            else:
                role = discord.utils.get(channel.guild.roles, name=name)
            if role is None:
                logger.error("[%s] role %r not found", self.name, name)
            else:
                pings.append(role.mention)
        lines = [" ".join(pings)] if pings else []
        if test:
            lines.append("*(this is a test)*")
        lines.append(text)
        try:
            await channel.send("\n".join(lines)[:2000], allowed_mentions=discord.AllowedMentions(roles=True))
        except discord.HTTPException:
            logger.exception("[%s] could not post in the reminder channel", self.name)
            return False
        return True

    async def send_reminder(self, kind, test=False):
        """kind is "at" (the raid-day message) or "before" (the hour-before message)."""
        text = self.config.raid_day_message if kind == "at" else self.config.raid_hour_message
        if "{link}" in text:
            text = text.replace("{link}", await self.hub_link())
        return await self.post(text, test)

    async def announce_status(self, event, start):
        if event.get("status") == "cancelled":
            await self.post(f"❌ {title(event)} on {stamp(start, 'F')} has been **cancelled**.")
        else:
            await self.post(f"✅ {title(event)} on {stamp(start, 'F')} is back on.")

    def load_state(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
            return set(state["sent"]), set(state["muted"]), dict(state.get("statuses") or {})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return set(), set(), {}

    def save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"sent": sorted(self.sent), "muted": sorted(self.muted), "statuses": self.statuses}, f)
