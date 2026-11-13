import logging

from ..util import extra_entries, weighted_pick
from .base import BaseModule

logger = logging.getLogger(__name__)


class AiModule(BaseModule):
    name = "AI"

    async def handle_message(self, message):
        content = message.content.lower()
        if "play despacito" in content:
            await message.reply("Fuck no, my cousin, Alexa, handles those requests...")
        elif "kick" in content and len(message.mentions) == 2:
            await message.reply("Sadly, this is not within my power, learn to get along!")
        else:
            await self.lookup_response(message)

    async def lookup_response(self, message):
        replies = extra_entries("replies.txt")
        if self.bot.resources is not None:
            try:
                replies = replies + await self.bot.resources.bot_replies()
            except Exception:
                logger.exception("[%s] could not fetch replies, using the built-in ones", self.name)
        reply = weighted_pick([r for r in replies if r.get("content")])
        if reply is None:
            await message.reply("My creator forgot to give me witty responses...")
        else:
            await message.reply(str(reply["content"]))
