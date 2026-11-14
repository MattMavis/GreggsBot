import logging
import random

import discord

from ..util import truncate
from .base import BaseModule, ResponderModule

logger = logging.getLogger(__name__)

RECEIPT = "Got it. I've passed your message on to the Greggs officers."


def dm_embed(message):
    author = message.author
    embed = discord.Embed(
        title="Direct Message To The Bot", color=random.randint(0, 0xFFFFFF), timestamp=message.created_at
    )
    embed.add_field(name="Sent By", value=f"{author} ({author.mention})", inline=False)
    embed.add_field(name="Message:", value=truncate(message.content, 1024) or "*(no text)*", inline=False)
    if message.attachments:
        links = "\n".join(a.url for a in message.attachments)
        embed.add_field(name="Attachments", value=truncate(links, 1024), inline=False)
    embed.set_thumbnail(url=author.display_avatar.url)
    embed.set_footer(text="DM Bot Messages | DM Logs")
    return embed


class DmLogModule(BaseModule):
    """Copies direct messages sent to the bot into one channel, and tells the sender it did."""

    name = "DM Log"

    async def forward(self, message):
        channel = self.bot.get_channel(self.config.dm_log_channel)
        if channel is None:
            logger.error("[%s] DM_LOG_CHANNEL %s not found", self.name, self.config.dm_log_channel)
            return
        await channel.send(embed=dm_embed(message))
        await message.channel.send(RECEIPT)


class PingModule(ResponderModule):
    name = "Ping"
    commands = ("ping",)

    async def respond(self, message, word, args):
        await message.reply("Pong!")
