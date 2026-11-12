import logging
from datetime import datetime
from urllib.parse import quote

import discord

from ..resources import get_json
from ..util import format_date
from .base import ResponderModule

logger = logging.getLogger(__name__)

GUILD_PAGE = "https://www.warcraftlogs.com/guild/id/219370"
MAX_LOGS = 3


class WarcraftLogsModule(ResponderModule):
    name = "Warcraft Logs"
    commands = ("wcl",)

    async def help_text(self):
        return self.name, f"__Description__: Fetch latest logs.\n__Usage__: `{self.config.prefix}wcl`"

    async def respond(self, message, word, args):
        c = self.config
        if not c.wcl_token:
            await message.reply("Warcraft Logs isn't configured for this bot (no WCL_TOKEN), sorry.")
            return

        url = (
            "https://www.warcraftlogs.com/v1/reports/guild/"
            f"{quote(c.guild_name, safe='')}/{quote(c.guild_realm, safe='')}/{quote(c.guild_region, safe='')}"
        )
        try:
            reports = await get_json(self.bot.session, url, {"api_key": c.wcl_token})
            logs = [r for r in reports if isinstance(r, dict)][:MAX_LOGS]
        except Exception:
            logger.exception("[%s] fetching logs failed", self.name)
            await message.reply(f"Couldn't fetch latest logs. Try guild page at {GUILD_PAGE}")
            return

        if not logs:
            await message.reply(f"No logs found. Try guild page at {GUILD_PAGE}")
            return

        embed = discord.Embed(
            title=f"<{c.guild_name}> Warcraft Logs",
            description=f"Latest {len(logs)}",
            url=GUILD_PAGE,
            color=0xFF0000,
        )
        for log in logs:
            date = format_date(datetime.fromtimestamp(log["start"] / 1000, tz=c.tz))
            embed.add_field(name=date, value=f"https://www.warcraftlogs.com/reports/{log['id']}", inline=False)
        await message.reply(embed=embed)
