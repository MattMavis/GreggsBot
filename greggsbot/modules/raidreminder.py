import asyncio
import logging
import time
from datetime import datetime

import discord
from croniter import croniter

from .base import BaseModule

logger = logging.getLogger(__name__)


def to_croniter_expr(expr):
    """node-cron takes an optional leading seconds field, croniter wants seconds last."""
    fields = str(expr).split()
    if len(fields) == 6:
        fields = fields[1:] + fields[:1]
    cron = " ".join(fields)
    return cron if len(fields) in (5, 6) and croniter.is_valid(cron) else None


def mention_names(entry):
    names = entry.get("mentions")
    return [str(n) for n in names if n] if isinstance(names, list) else []


class RaidReminderModule(BaseModule):
    name = "RaidReminder"

    def __init__(self, bot):
        super().__init__(bot)
        self.tasks = []

    async def start(self):
        try:
            reminders = await self.bot.resources.reminders()
        except Exception:
            logger.exception("Could not fetch reminders")
            return
        valid = [r for r in (self.validate(entry) for entry in reminders) if r]
        logger.info("Scheduling %d of %d reminders", len(valid), len(reminders))
        for reminder in valid:
            self.tasks.append(asyncio.create_task(self.run_reminder(reminder)))

    def validate(self, entry):
        if not entry.get("enabled"):
            return None
        title = entry.get("title")
        cron = to_croniter_expr(entry.get("cron", ""))
        if cron is None:
            logger.error('Invalid cron in reminder "%s" [%s]', title, entry.get("cron"))
            return None
        try:
            guild_id = int(entry.get("guild"))
            channel_id = int(entry.get("channel"))
        except (TypeError, ValueError):
            logger.error('Reminder "%s" has a bad guild or channel id', title)
            return None
        if self.bot.get_guild(guild_id) is None:
            logger.error('Reminder "%s": I am not in guild %s', title, guild_id)
            return None
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.error('Reminder "%s": channel %s not found or not a text channel', title, channel_id)
            return None
        return {"entry": entry, "cron": cron, "guild": guild_id, "channel": channel_id}

    async def run_reminder(self, reminder):
        tz = self.config.tz
        fires = croniter(reminder["cron"], datetime.now(tz))
        while True:
            delay = fires.get_next(datetime).timestamp() - time.time()
            await asyncio.sleep(max(delay, 0))
            try:
                await self.send_reminder(reminder)
            except Exception:
                logger.exception('Sending reminder "%s" failed', reminder["entry"].get("title"))

    async def send_reminder(self, reminder):
        entry = reminder["entry"]
        guild = self.bot.get_guild(reminder["guild"])
        channel = self.bot.get_channel(reminder["channel"])
        if guild is None or channel is None:
            logger.error('Reminder "%s": guild or channel is gone', entry.get("title"))
            return

        pings = []
        for role_name in mention_names(entry):
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                logger.error("Could not find the role %r for a mention", role_name)
            else:
                pings.append(role.mention)

        text = str(entry.get("message", ""))
        if pings:
            text = " ".join(pings) + "\n" + text
        # reminders are written by admins, so they may ping roles and @here/@everyone
        await channel.send(text, allowed_mentions=discord.AllowedMentions(roles=True, everyone=True))
