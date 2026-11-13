"""Slash-command versions of the prefix commands. Each one hands over to the same module code."""

import logging
from typing import Literal, Optional

import discord
from discord import app_commands

from .modules.eightball import EightBallModule
from .modules.guides import GuidesModule
from .modules.help import HelpModule
from .modules.pasta import PastaModule
from .modules.quicklinks import QuickLinksModule
from .modules.raidcalendar import RaidCalendarModule
from .modules.raiderio import DEFAULT_CHARACTER, RaiderIoModule
from .modules.roll import RollModule
from .modules.warcraftlogs import WarcraftLogsModule
from .modules.wowtoken import WowTokenModule

logger = logging.getLogger(__name__)


class SlashMessage:
    """Looks enough like a discord.Message for the modules to answer a slash command."""

    def __init__(self, interaction, content, mentions=()):
        self.interaction = interaction
        self.content = content
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.mentions = list(mentions)
        self.replied = False

    async def reply(self, content=None, **kwargs):
        self.replied = True
        if content is not None:
            content = content.lstrip("\n")
        await self.interaction.followup.send(content, **kwargs)


async def run(interaction, module, word, args=(), mentions=()):
    args = [str(a) for a in args]
    await interaction.response.defer()
    message = SlashMessage(interaction, " ".join([f"/{word}", *args]), mentions)
    logger.info("[%s] <- [%s]", module.name, message.content)
    try:
        await module.respond(message, word, args)
    except Exception:
        logger.exception("[%s] slash command failed", module.name)
        if not message.replied:
            await message.reply("Something went wrong, sorry.")
    if not message.replied:
        # the module answered in the channel instead (duels), so drop the "thinking..." placeholder
        await interaction.delete_original_response()


def register(bot):
    tree = bot.tree
    config = bot.config
    found = {type(m): m for m in bot.modules}

    def command(module_class, name, description):
        """Registers the decorated function only when its module is loaded."""
        module = found.get(module_class)

        def decorator(func):
            if module is not None:
                tree.command(name=name, description=description)(app_commands.guild_only()(func))
            return func

        decorator.module = module
        return decorator

    roll_cmd = command(RollModule, "roll", "Roll the die! 1-100, or up to a max of your choosing")

    @roll_cmd
    @app_commands.describe(max="Highest number you can roll (default 100)")
    async def roll(interaction: discord.Interaction, max: Optional[int] = None):
        await run(interaction, roll_cmd.module, "roll", [max] if max is not None else [])

    duel_cmd = command(RollModule, "duel", "Challenge someone to a roll duel")

    @duel_cmd
    @app_commands.describe(opponent="Who you are challenging")
    async def duel(interaction: discord.Interaction, opponent: discord.Member):
        await run(interaction, duel_cmd.module, "roll", ["duel", opponent.mention], [opponent])

    token_cmd = command(WowTokenModule, "token", "Find out how shite value WoW Tokens are")

    @token_cmd
    async def token(interaction: discord.Interaction):
        await run(interaction, token_cmd.module, "token")

    rank_cmd = command(RaiderIoModule, "rank", "Raider.IO raid rankings for a guild")

    @rank_cmd
    @app_commands.describe(guild="Guild name", realm="Realm, e.g. tarren-mill", region="EU, US, KR or TW")
    async def rank(
        interaction: discord.Interaction,
        guild: Optional[str] = None,
        realm: Optional[str] = None,
        region: Optional[str] = None,
    ):
        args = [guild or config.guild_name, realm or config.guild_realm, region or config.guild_region]
        await run(interaction, rank_cmd.module, "rank", args)

    check_cmd = command(RaiderIoModule, "check", "Raider.IO Mythic+ rankings for a character")

    @check_cmd
    @app_commands.describe(
        character="Character name", realm="Realm, e.g. tarren-mill", region="EU, US, KR or TW", role="Role to rank"
    )
    async def check(
        interaction: discord.Interaction,
        character: Optional[str] = None,
        realm: Optional[str] = None,
        region: Optional[str] = None,
        role: Optional[Literal["tank", "healer", "dps"]] = None,
    ):
        args = [character or DEFAULT_CHARACTER, realm or config.guild_realm, region or config.guild_region]
        await run(interaction, check_cmd.module, "check", args + ([role] if role else []))

    wcl_cmd = command(WarcraftLogsModule, "wcl", "Latest Warcraft Logs reports")

    @wcl_cmd
    async def wcl(interaction: discord.Interaction):
        await run(interaction, wcl_cmd.module, "wcl")

    raids_cmd = command(RaidCalendarModule, "raids", "Upcoming raid nights and who's signed up")

    @raids_cmd
    async def raids(interaction: discord.Interaction):
        await run(interaction, raids_cmd.module, "raids")

    eightball_cmd = command(EightBallModule, "8ball", "Ask the Magic 8-Ball a yes/no question")

    @eightball_cmd
    @app_commands.describe(question="Your yes/no question")
    async def eightball(interaction: discord.Interaction, question: str):
        await run(interaction, eightball_cmd.module, "8ball", question.split())

    pasta_cmd = command(PastaModule, "pasta", "Emoji pasta straight from the meme factory")

    @pasta_cmd
    @app_commands.describe(key="A specific pasta (leave empty for a random one)")
    async def pasta(interaction: discord.Interaction, key: Optional[str] = None):
        await run(interaction, pasta_cmd.module, "pasta", key.split()[:1] if key else [])

    guide_cmd = command(GuidesModule, "guide", "Fetch boss guides like a BOSS")

    @guide_cmd
    @app_commands.describe(boss="Boss (or raid) name", raid="Raid name, if the boss name is ambiguous")
    async def guide(interaction: discord.Interaction, boss: str, raid: Optional[str] = None):
        args = [raid.split()[0], boss.split()[0]] if raid else boss.split()[:1]
        await run(interaction, guide_cmd.module, "guide", args)

    link_cmd = command(QuickLinksModule, "link", "Get links fucking quick")

    @link_cmd
    @app_commands.describe(name="Which link")
    async def link(interaction: discord.Interaction, name: str):
        await run(interaction, link_cmd.module, name.split()[0].lower() if name.split() else "")

    help_cmd = command(HelpModule, "help", "What Greggs Bot can do")

    @help_cmd
    async def help_(interaction: discord.Interaction):
        await run(interaction, help_cmd.module, "ghelp")
