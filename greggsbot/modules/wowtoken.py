import logging
from datetime import datetime

import discord

from ..resources import get_json
from ..util import fmt_number, format_date
from .base import ResponderModule

logger = logging.getLogger(__name__)

URL = "https://data.wowtoken.app/v2/current/retail.json"
GBP_COST = 15.0
EUR_COST = 20.0


class WowTokenModule(ResponderModule):
    name = "Wow Token Price"
    commands = ("token",)

    async def help_text(self):
        return self.name, f"__Description__: Find out how shite value WoW Tokens are.\n__Usage__: `{self.config.prefix}token`"

    async def respond(self, message, word, args):
        try:
            data = await get_json(self.bot.session, URL)
            timestamp, price = data["eu"]
            when = datetime.fromisoformat(timestamp).astimezone(self.config.tz)
            price = float(price)
        except Exception:
            logger.exception("[%s] fetching token price failed", self.name)
            await message.reply("Something went wrong, sorry. Fuck you.")
            return

        embed = discord.Embed(
            title="WoW Token Price", url="https://wowtoken.app/", description="EU token price", color=0x00558F
        )
        embed.add_field(name="Sell (g)", value=f"{fmt_number(price)}G", inline=False)
        embed.add_field(name="g per £", value=f"{fmt_number(price / GBP_COST)}G", inline=False)
        embed.add_field(name="g per €", value=f"{fmt_number(price / EUR_COST)}G", inline=False)
        embed.set_footer(text=format_date(when))
        await message.reply(embed=embed)
