import logging

from ..util import has_tag, tags_of
from .base import COOKIE, ResponderModule

logger = logging.getLogger(__name__)


class QuickLinksModule(ResponderModule):
    name = "Quick Links"

    async def is_command(self, word):
        try:
            links = await self.bot.resources.links()
        except Exception:
            logger.exception("Could not fetch quick links")
            return False
        return any(has_tag(link, word) for link in links)

    async def help_text(self):
        try:
            links = await self.bot.resources.links()
        except Exception:
            logger.exception("Could not fetch quick links for help")
            commands = "(unavailable right now)"
        else:
            commands = ", ".join(f"`{self.config.prefix}{t}`" for link in links for t in tags_of(link))
        return self.name, f"__Description__: Get links fucking quick\n__Usage__: {commands}"

    async def respond(self, message, word, args):
        links = await self.fetch_or_reply(message, self.bot.resources.links())
        if links is None:
            return
        link = next((l for l in links if has_tag(l, word) and l.get("content")), None)
        if link is None:
            await message.reply(f'No link was found for the command "{word}"' + COOKIE)
        else:
            await message.reply(f"\n<{link['content']}>")
