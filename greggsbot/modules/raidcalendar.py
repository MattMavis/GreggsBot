import asyncio
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

from ..resources import HttpError
from ..state import load_json, save_json
from .base import ResponderModule, can_manage
from .raidschedule import (
    due_reminders,
    event_start,
    find_night,
    next_fire_time,
    signup_line,
    stamp,
    status_changes,
    title,
    upcoming,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 300
STATE_FILE = os.path.join("state", "raid_reminders.json")
# plain text files, edited by hand or with the raidmessage command; read every time a reminder is sent
MESSAGE_FILES = {"at": os.path.join("messages", "raid_day.txt"), "before": os.path.join("messages", "raid_hour.txt")}
HUB = "https://wowutils.com/viserio-cooldowns/raid"


def find_role(guild, name):
    return guild.get_role(int(name)) if name.isdigit() else discord.utils.get(guild.roles, name=name)


class RaidCalendarModule(ResponderModule):
    name = "Raid Calendar"
    commands = ("raids", "raidtest", "reminders", "raidmessage")

    def __init__(self, bot, wowutils):
        super().__init__(bot)
        self.wowutils = wowutils
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
            f"`{p}raidtest` to post test reminders, `{p}raidtest cancel` to post test cancellation notices, "
            f"`{p}raidmessage hour <new text>` or `{p}raidmessage day <new text>` to change a reminder's wording"
        )
        return self.name, content

    async def start(self):
        if self.config.raid_channel:
            self.task = asyncio.create_task(self.poll())
        else:
            logger.warning("RAID_CHANNEL is not set: raid reminders are off, %sraids still works", self.config.prefix)

    async def fetch_events(self):
        data, self.etag = await self.wowutils.request(
            f"/groups/{await self.wowutils.group()}/calendar-events?upcoming=true&limit=30", self.etag
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
        if word == "raidmessage":
            await self.edit_message(message)
            return
        fetched = await self.fetch_or_reply(message, self.fetch_events())
        if fetched is None:
            return
        events, tz = fetched
        nights = upcoming(events, tz, datetime.now(timezone.utc))
        if not nights:
            await message.reply("No raid nights on the calendar. Go outside.")
        elif word == "raidtest":
            await self.test_reminder(message, nights, cancel=bool(args) and args[0].lower().startswith("cancel"))
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

    def unmuted(self, events):
        return [e for e in events if str(e.get("eventId")) not in self.muted]

    async def test_reminder(self, message, nights, cancel=False):
        if not self.config.raid_channel:
            await message.reply("RAID_CHANNEL isn't set, so I have nowhere to post reminders.")
            return
        if cancel:
            start, event = nights[0]
            posted = [
                await self.announce_status(dict(event, status=status), start, test=True)
                for status in ("cancelled", "planned")
            ]
            what = "cancelled and back-on notices"
        else:
            posted = [await self.send_reminder(kind, test=True) for kind in ("at", "before")]
            what = "reminders"
        if all(posted):
            await message.reply(f"Both test {what} posted in <#{self.config.raid_channel}>.")
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
            await asyncio.sleep(self.seconds_until_next_check())

    def seconds_until_next_check(self):
        """The regular poll interval, cut short so the bot wakes exactly when the next reminder is due."""
        events, tz = self.cached
        now = datetime.now(timezone.utc)
        fire_at = next_fire_time(self.unmuted(events), tz, now, self.config.raid_reminders, self.sent, self.config.tz)
        if fire_at is None:
            return POLL_SECONDS
        return max(1, min(POLL_SECONDS, (fire_at - now).total_seconds() + 0.5))

    async def send_due(self):
        try:
            events, tz = await self.fetch_events()
        except Exception:
            # a reminder should still go out on time if wowutils is briefly down
            events, tz = self.cached
            if not events:
                raise
            logger.warning("[%s] wowutils fetch failed, using the calendar from the last good check", self.name)
        now = datetime.now(timezone.utc)
        changed, self.statuses = status_changes(events, self.statuses)
        for event in changed:
            start = event_start(event, tz)
            if start and start > now and self.config.raid_cancel_notices:
                await self.announce_status(event, start)
        for event, reminder, key in due_reminders(
            self.unmuted(events), tz, now, self.config.raid_reminders, self.sent, self.config.tz
        ):
            await self.send_reminder(reminder[0])
            self.sent.add(key)
        live = {str(e.get("eventId")) for _, e in upcoming(events, tz, now)}
        self.sent = {key for key in self.sent if key.split("|")[0] in live}
        self.muted &= live
        self.save_state()

    async def hub_link(self):
        group_id = self.wowutils.group_id
        link = f"{HUB}?groupId={group_id}"
        try:
            reset, _ = await self.wowutils.request(f"/groups/{group_id}/latest-reset")
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
            role = find_role(channel.guild, name)
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
        text = self.message_text(kind)
        if "{link}" in text:
            text = text.replace("{link}", await self.hub_link())
        return await self.post(text, test)

    def message_text(self, kind):
        try:
            with open(MESSAGE_FILES[kind], encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            text = ""
        return text or (self.config.raid_day_message if kind == "at" else self.config.raid_hour_message)

    async def edit_message(self, message):
        p = self.config.prefix
        parts = message.content.split(None, 2)
        if len(parts) < 2 or parts[1].lower() not in ("day", "hour"):
            await message.reply(
                f"Usage: `{p}raidmessage hour <new text>` or `{p}raidmessage day <new text>`. "
                "Leave the text off to see the current one, or use `reset` to go back to the default. "
                "`{link}` becomes the raid planning link."
            )
            return
        which = parts[1].lower()
        kind = "at" if which == "day" else "before"
        path = MESSAGE_FILES[kind]
        if len(parts) == 2:
            await message.reply(f"The {which} reminder currently says:\n{self.message_text(kind)}")
        elif parts[2].strip().lower() == "reset":
            if os.path.exists(path):
                os.remove(path)
            await message.reply(f"The {which} reminder is back to the default:\n{self.message_text(kind)}")
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(parts[2].strip() + "\n")
            await message.reply(f"Saved. The {which} reminder now says:\n{parts[2].strip()}\nUse `{p}raidtest` to see it posted.")

    async def announce_status(self, event, start, test=False):
        if event.get("status") == "cancelled":
            return await self.post(f"❌ {title(event)} on {stamp(start, 'F')} has been **cancelled**.", test)
        return await self.post(f"✅ {title(event)} on {stamp(start, 'F')} is back on.", test)

    def load_state(self):
        state = load_json(STATE_FILE, None)
        try:
            return set(state["sent"]), set(state["muted"]), dict(state.get("statuses") or {})
        except (KeyError, TypeError, ValueError, AttributeError):
            return set(), set(), {}

    def save_state(self):
        save_json(STATE_FILE, {"sent": sorted(self.sent), "muted": sorted(self.muted), "statuses": self.statuses})
