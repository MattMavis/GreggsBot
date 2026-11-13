import asyncio
import logging

import aiohttp
import discord

from .modules.ai import AiModule
from .modules.base import is_admin
from .modules.eightball import EightBallModule
from .modules.guides import GuidesModule
from .modules.help import HelpModule
from .modules.pasta import PastaModule
from .modules.quicklinks import QuickLinksModule
from .modules.raidcalendar import RaidCalendarModule
from .modules.raiderio import RaiderIoModule
from .modules.raidreminder import RaidReminderModule
from .modules.roll import RollModule
from .modules.warcraftlogs import WarcraftLogsModule
from .modules.wowtoken import WowTokenModule
from .resources import ResourceService

logger = logging.getLogger(__name__)


class GreggsBot(discord.Client):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        # Pasta and link content must never be able to ping @everyone or roles
        allowed = discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True)
        super().__init__(intents=intents, allowed_mentions=allowed)
        self.config = config
        self.session = None
        self.resources = None
        self.ai = None
        self.modules = []
        self.modules_started = False

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        if self.config.api:
            self.resources = ResourceService(self.config.api, self.session)

    async def close(self):
        await super().close()
        if self.session is not None:
            await self.session.close()

    async def on_ready(self):
        logger.info("Logged in as %s", self.user)
        # on_ready fires again after reconnects
        if self.modules_started:
            return
        self.modules_started = True

        self.ai = AiModule(self)
        self.modules = [RollModule(self), RaiderIoModule(self), WowTokenModule(self), WarcraftLogsModule(self)]
        if self.resources is not None:
            self.modules += [
                EightBallModule(self),
                PastaModule(self),
                QuickLinksModule(self),
                RaidReminderModule(self),
                GuidesModule(self),
            ]
        else:
            logger.warning("API is not set: 8-ball, pasta, quick links, raid reminders and guides are off")
        if self.config.wowutils_key:
            self.modules.append(RaidCalendarModule(self))
        self.modules.append(HelpModule(self))
        for module in self.modules:
            try:
                await module.start()
            except Exception:
                logger.exception("Module %s failed to start", module.name)
        await self.modules[0].log(":robot: bot started bleep bloop bleep bloop :robot:")

    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        try:
            if self.user in message.mentions:
                await self.handle_mention(message)
            elif message.content.startswith(self.config.prefix):
                await asyncio.gather(*(self.run_module(m, message) for m in self.modules))
        except Exception:
            logger.exception("Failed to handle message")

    async def run_module(self, module, message):
        try:
            await module.handle_message(message)
        except Exception:
            logger.exception("Module %s failed on [%s]", module.name, message.content)

    async def handle_mention(self, message):
        if self.ai is None:
            return
        if "restart" in message.content.lower():
            await self.restart(message)
        else:
            await self.ai.handle_message(message)

    async def restart(self, message):
        if not is_admin(message.author):
            await message.reply("No, you're not my master, shame on you for trying to restart me!")
            return
        logger.info("Restarting bot...")
        await message.reply("Very well master, restarting, brb...")
        await self.close()
