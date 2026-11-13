import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

from ..util import truncate
from .base import ResponderModule

logger = logging.getLogger(__name__)

SEAT_ICONS = {"tank": "🛡️", "healer": "💚"}
MAX_RUNS = 8
MAX_LFG = 10


def zone(data):
    try:
        return ZoneInfo(data.get("serverTimeZone") or "UTC")
    except Exception:
        return timezone.utc


def when(date, time, tz):
    try:
        start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except (TypeError, ValueError):
        return str(date)
    return f"<t:{int(start.timestamp())}:F>"


def seat_text(slot):
    return slot.get("characterName") or slot.get("guestName") or "*open*"


def run_text(run, tz):
    dungeons = " / ".join(d.get("name", "?") for d in run.get("dungeons") or []) or "any dungeon"
    head = f"{when(run.get('date'), run.get('startTime'), tz)} - **{dungeons}**"
    if run.get("note"):
        head += f" *({run['note']})*"
    slots = run.get("slots") or []
    seats = [f"{SEAT_ICONS[s['slotId']]} {seat_text(s)}" for s in slots if s.get("slotId") in SEAT_ICONS]
    dps = [seat_text(s) for s in slots if str(s.get("slotId", "")).startswith("dps")]
    if dps:
        seats.append("⚔️ " + ", ".join(dps))
    return head + ("\n" + " · ".join(seats) if seats else "")


def lfg_text(entry, tz):
    characters = []
    for c in entry.get("characters") or []:
        spec = " ".join(part for part in (c.get("specName"), c.get("className")) if part)
        characters.append(f"**{c.get('name', '?')}**" + (f" ({spec})" if spec else ""))
    windows = entry.get("windows") or []
    if entry.get("anytime") or not windows:
        free = "anytime"
    else:
        first = windows[0]
        free = f"from {when(first.get('date'), first.get('startTime'), tz)}"
    text = f"{', '.join(characters) or '?'} - {free}"
    if entry.get("note"):
        text += f" *({entry['note']})*"
    return text


class MythicKeysModule(ResponderModule):
    name = "Mythic+ Keys"
    commands = ("keys",)

    def __init__(self, bot, wowutils):
        super().__init__(bot)
        self.wowutils = wowutils

    async def help_text(self):
        return self.name, f"__Description__: Planned key runs and who's looking for a group.\n__Usage__: `{self.config.prefix}keys`"

    async def fetch(self):
        group_id = await self.wowutils.group()
        runs, _ = await self.wowutils.request(f"/groups/{group_id}/keys/groups")
        lfg, _ = await self.wowutils.request(f"/groups/{group_id}/keys/lfg")
        return runs, lfg

    async def respond(self, message, word, args):
        fetched = await self.fetch_or_reply(message, self.fetch())
        if fetched is None:
            return
        runs, lfg = fetched
        planned = runs.get("data") or []
        looking = lfg.get("data") or []
        if not planned and not looking:
            await message.reply("No keys planned and nobody looking for a group. Depleted before it started.")
            return

        embed = discord.Embed(title="Mythic+ keys", color=0xFAA61A)
        if planned:
            lines = [run_text(run, zone(runs)) for run in planned[:MAX_RUNS]]
            if len(planned) > MAX_RUNS:
                lines.append(f"...and {len(planned) - MAX_RUNS} more")
            embed.description = truncate("\n\n".join(lines), 4096)
        else:
            embed.description = "No runs planned."
        if looking:
            lines = [lfg_text(entry, zone(lfg)) for entry in looking[:MAX_LFG]]
            if len(looking) > MAX_LFG:
                lines.append(f"...and {len(looking) - MAX_LFG} more")
            embed.add_field(name="Looking for a group", value=truncate("\n".join(lines), 1024), inline=False)
        await message.reply(embed=embed)
