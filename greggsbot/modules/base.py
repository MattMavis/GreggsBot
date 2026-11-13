import logging

logger = logging.getLogger(__name__)

TROUBLE = "Sorry, I had some trouble fetching that information."
COOKIE = "\nBut here, have a cookie :cookie:."


def parse_command(content, prefix):
    if not content.startswith(prefix):
        return None
    parts = content[len(prefix):].split()
    if not parts:
        return None
    return parts[0].lower(), parts[1:]


class BaseModule:
    name = ""

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    async def start(self):
        pass

    async def handle_message(self, message):
        pass

    async def help_text(self):
        return None

    async def log(self, text, prefix=None):
        line = f"[{prefix}] - {text}" if prefix else text
        logger.info("[%s] %s", self.name, line)
        channel = self.bot.get_channel(self.config.bot_chan) if self.config.bot_chan else None
        if channel is None:
            return
        try:
            await channel.send(line)
        except Exception:
            logger.exception("Could not log to the bot channel")

    async def fetch_or_reply(self, message, coro):
        """Awaits a fetch; on failure logs it, tells the user and returns None."""
        try:
            return await coro
        except Exception:
            logger.exception("[%s] fetch failed", self.name)
            await message.reply(TROUBLE)
            return None


def is_admin(member):
    return any(r.name == "Greggs Bot Maintainer" for r in getattr(member, "roles", []))


def can_manage(member):
    permissions = getattr(member, "guild_permissions", None)
    return is_admin(member) or bool(permissions and permissions.manage_guild)


class ResponderModule(BaseModule):
    commands = ()

    async def is_command(self, word):
        return word in self.commands

    async def handle_message(self, message):
        parsed = parse_command(message.content, self.config.prefix)
        if parsed is None:
            return
        word, args = parsed
        if not await self.is_command(word):
            return
        logger.info("[%s] <- [%s]", self.name, message.content)
        await self.respond(message, word, args)

    async def respond(self, message, word, args):
        raise NotImplementedError
