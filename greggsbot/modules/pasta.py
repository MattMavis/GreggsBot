import logging
import random
from datetime import datetime

from ..util import has_tag, tags_of, truncate
from .base import COOKIE, ResponderModule

logger = logging.getLogger(__name__)


def pick_pasta(pastas, key=None, today=None):
    pastas = [p for p in pastas if p.get("content")]
    if key:
        return next((p for p in pastas if has_tag(p, key)), None)

    today = today or datetime.now()
    if today.month == 9 and today.day == 11:
        return next((p for p in pastas if has_tag(p, "911")), None)

    seasonal = [p for p in pastas if p.get("month") and str(p["month"]) == str(today.month)]
    regular = [p for p in pastas if not p.get("month")]
    pool = seasonal or regular
    return random.choice(pool) if pool else None


class PastaModule(ResponderModule):
    name = "Emoji Pasta"
    commands = ("pasta",)

    async def help_text(self):
        prefix = self.config.prefix
        try:
            pastas = await self.bot.resources.pastas()
        except Exception:
            logger.exception("Could not fetch pastas for help")
            keys = "(unavailable right now)"
        else:
            tags = [t for p in pastas if not p.get("month") for t in tags_of(p)]
            keys = ", ".join(f"`{t}`" for t in tags)
        content = (
            "__Description__: Get emoji pasta straight from the meme factory\n"
            f"__Usage__: `{prefix}pasta` for (seasonal) random or `{prefix}pasta [pasta key]`\n"
            f"__Pasta keys__: {keys}"
        )
        return self.name, content

    async def respond(self, message, word, args):
        pastas = await self.fetch_or_reply(message, self.bot.resources.pastas())
        if pastas is None:
            return
        pasta = pick_pasta(pastas, args[0] if args else None)
        if pasta is None:
            await message.reply("We ran out of pasta!!" + COOKIE)
        else:
            await message.reply(truncate(f"\n{pasta['content']}", 2000))
