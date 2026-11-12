import discord

from ..resources import to_list
from ..util import has_tag, tags_of, truncate
from .base import COOKIE, ResponderModule

COLOR = 0xFAA61A


def find_raid(raids, name):
    return next((r for r in raids if has_tag(r, name)), None)


def find_boss(raid, name):
    return next((b for b in to_list(raid.get("bosses")) if has_tag(b, name)), None)


def lookup_boss(raids, boss_name, raid_name=""):
    """Returns (boss, raid) or None."""
    if raid_name:
        raid = find_raid(raids, raid_name)
        boss = find_boss(raid, boss_name) if raid else None
        return (boss, raid) if boss else None
    for raid in raids:
        boss = find_boss(raid, boss_name)
        if boss:
            return boss, raid
    return None


def add_field(embed, name, value, inline=False):
    if value:
        embed.add_field(name=truncate(name or "Extra", 256), value=truncate(value, 1024), inline=inline)


class GuidesModule(ResponderModule):
    name = "Raid Guides"
    commands = ("guide",)

    async def help_text(self):
        return self.name, f"__Description__: Fetch boss guides like a BOSS.\n__Usage__: `{self.config.prefix}guide <raid> <boss>`"

    async def respond(self, message, word, args):
        prefix = self.config.prefix
        if not 1 <= len(args) <= 2:
            await message.reply(
                f"Please add a raid or boss parameter to your command! (e.g. `{prefix}guide uldir taloc` or `{prefix}guide taloc`)"
            )
            return
        raid_name, boss_name = (args[0], args[1]) if len(args) == 2 else ("", args[0])

        raids = await self.fetch_or_reply(message, self.bot.resources.raids())
        if raids is None:
            return

        found = lookup_boss(raids, boss_name, raid_name)
        if found:
            await message.reply(embed=self.boss_embed(*found))
            return
        # the "boss" argument might be a raid, so list that raid's guides instead
        raid = find_raid(raids, boss_name)
        if raid:
            await message.reply(embed=self.raid_embed(raid))
            return
        text = f'No guide was found for a boss named "{boss_name}"'
        text += f' in a raid named "{raid_name}".' if raid_name else "."
        await message.reply(text + COOKIE)

    def boss_embed(self, boss, raid):
        embed = discord.Embed(title=truncate(f"__{boss.get('name', '?')} Mythic - {raid.get('name', '?')}__", 256), color=COLOR)
        if boss.get("thumbnail"):
            embed.set_thumbnail(url=boss["thumbnail"])
        if boss.get("description"):
            embed.description = truncate(boss["description"], 4096)
        add_field(embed, "Wowhead", boss.get("wowhead"), True)
        add_field(embed, "Youtube", boss.get("youtube"))
        for extra in to_list(boss.get("extra"))[:20]:
            add_field(embed, extra.get("name"), extra.get("content"))
        return embed

    def raid_embed(self, raid):
        embed = discord.Embed(title=truncate(f"__{raid.get('name', '?')}__", 256), color=COLOR)
        if raid.get("description"):
            embed.description = truncate(raid["description"], 4096)
        guides = ""
        for boss in to_list(raid.get("bosses")):
            tags = tags_of(boss)
            if tags:
                guides += f"**{boss.get('name', '?')}:** `{self.config.prefix}guide {tags[0]}`\n"
        add_field(embed, "__Available guide commands__", guides)
        extras = "".join(f"**{e.get('name', '?')}:** {e.get('content', '')}\n" for e in to_list(raid.get("extra")))
        add_field(embed, "__Extras__", extras)
        return embed
