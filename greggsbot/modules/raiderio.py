import logging

import discord

from ..resources import HttpError, get_json
from ..util import ordinal
from .base import TROUBLE, ResponderModule

logger = logging.getLogger(__name__)

GUILD_URL = "https://raider.io/api/v1/guilds/profile"
CHAR_URL = "https://raider.io/api/v1/characters/profile"
REGIONS = ["EU", "US", "KR", "TW"]
ROLES = ["tank", "healer", "dps"]
DEFAULT_CHARACTER = "Nkose"


def rank_text(rank):
    return ordinal(rank) if rank else "-"


def medal(rank):
    medals = [":first_place:", ":second_place:", ":third_place:"]
    if not rank:
        return "-"
    return medals[rank - 1] if rank <= len(medals) else str(rank)


def slug_label(slug):
    return slug.replace("-", " ").title()


def pick_raid_slug(progression, pinned=""):
    if pinned:
        return pinned if pinned in progression else None
    return next(iter(progression), None)


def rank_fields(data, slug):
    """Three (name, value) pairs: mythic, heroic, normal."""
    progress = (data.get("raid_progression") or {}).get(slug) or {}
    rankings = (data.get("raid_rankings") or {}).get(slug) or {}
    total = progress.get("total_bosses", 0)
    fields = []
    for key, short in (("mythic", "M"), ("heroic", "HC"), ("normal", "N")):
        killed = progress.get(f"{key}_bosses_killed", 0)
        ranks = rankings.get(key) or {}
        name = f"{slug_label(slug)} {short} {killed}/{total}"
        value = f"S {rank_text(ranks.get('realm'))} / R {rank_text(ranks.get('region'))}"
        fields.append((name, value))
    return fields


def best_role_score(data):
    seasons = data.get("mythic_plus_scores_by_season") or []
    scores = (seasons[0].get("scores") if seasons else None) or {}
    best_role, best_score = "dps", 0
    for role in ("dps", "healer", "tank"):
        score = scores.get(role) or 0
        if score > best_score:
            best_role, best_score = role, score
    return best_role, best_score


def check_summary(data, role=""):
    """Returns (description, [(name, value), ...]) for the !check embed."""
    best_role, best_score = best_role_score(data)
    role = role or best_role
    label = "DPS" if role == "dps" else f"{role.capitalize()}s"
    ranks = data.get("mythic_plus_ranks") or {}

    def realm_rank(key):
        return (ranks.get(key) or {}).get("realm")

    fields = [
        ("All Classes & Roles", medal(realm_rank("overall"))),
        (f"All {label}", medal(realm_rank(role))),
        (f"All {data.get('class', '')} {label}", medal(realm_rank(f"class_{role}"))),
    ]
    return f"Best score: **{best_score}** [{best_role}]", fields


def split_role(args):
    for i, arg in enumerate(args):
        if arg.lower() in ROLES:
            return arg.lower(), args[:i] + args[i + 1:]
    return "", args


class RaiderIoModule(ResponderModule):
    name = "Raider IO Module"
    commands = ("rank", "check")

    async def help_text(self):
        p = self.config.prefix
        content = (
            "__Description__: Instantly query Raider IO for guild or character rankings.\n"
            f"__Usage (guild ranks)__: `{p}rank [guild] [realm] [region]`\n"
            f"__Examples__: `{p}rank`, `{p}rank Greggs`\n"
            f"__Usage (character ranks)__: `{p}check [character] [realm] [region] [role]`\n"
            f"__Examples__: `{p}check Nkose`, `{p}check Nkose tank`\n"
            "__Possible roles__: `tank`, `healer`, `dps`"
        )
        return self.name, content

    async def respond(self, message, word, args):
        if word == "rank":
            await self.rank(message, args)
        else:
            await self.check(message, args)

    async def fetch(self, message, url, params):
        try:
            return await get_json(self.bot.session, url, params)
        except HttpError as e:
            if e.status in (400, 404):
                logger.warning("[%s] Raider.IO answered %s for %s", self.name, e.status, params)
                await message.reply(f"Sorry, I couldn't find that {'guild' if url == GUILD_URL else 'character'}.")
                return None
            logger.exception("[%s] Raider.IO request failed", self.name)
        except Exception:
            logger.exception("[%s] Raider.IO request failed", self.name)
        await message.reply(TROUBLE)
        return None

    def parse_args(self, args, default_name):
        c = self.config
        name = args[0] if len(args) >= 1 else default_name
        realm = args[1] if len(args) >= 2 else c.guild_realm
        region = args[2].upper() if len(args) >= 3 else c.guild_region
        return name, realm, region

    async def rank(self, message, args):
        name, realm, region = self.parse_args(args, self.config.guild_name)

        if name.lower() == "quick":
            await message.reply("Quick? Didn't they disband? RIP.")
            return
        if name.lower() == "fresh":
            await message.reply("Fresh? Don't you mean 'STALE'?!")
            return
        if region not in REGIONS:
            await message.reply(f"Where the fuck is {region}? Try one of {', '.join(REGIONS)}.")
            return

        params = {"name": name, "realm": realm, "region": region, "fields": "raid_rankings,raid_progression"}
        data = await self.fetch(message, GUILD_URL, params)
        if data is None:
            return

        slug = pick_raid_slug(data.get("raid_progression") or {}, self.config.raid)
        if slug is None:
            await message.reply("Raider.IO has no raid progression for that guild yet.")
            return

        embed = discord.Embed(title="Raider.IO Rankings", color=0xFF0000, description=f"<{name}> {realm}-{region}")
        if data.get("profile_url"):
            embed.url = data["profile_url"]
            embed.set_footer(text=data["profile_url"])
        for field_name, value in rank_fields(data, slug):
            embed.add_field(name=field_name, value=value, inline=True)
        await message.reply(embed=embed)

    async def check(self, message, args):
        role, args = split_role(args)
        name, realm, region = self.parse_args(args, DEFAULT_CHARACTER)

        if region not in REGIONS:
            await message.reply(f"Where the fuck is {region}? Try one of {', '.join(REGIONS)}.")
            return
        if name.lower() == "lightslayers":
            await message.reply("Raider.io scores? LuL, might as well go back to gearscore, that was awful too!!")
            return

        params = {
            "name": name,
            "realm": realm,
            "region": region,
            "fields": "mythic_plus_ranks,mythic_plus_scores_by_season:current",
        }
        data = await self.fetch(message, CHAR_URL, params)
        if data is None:
            return

        description, fields = check_summary(data, role)
        embed = discord.Embed(
            title=f"M+ Rankings for {name} ({realm}-{region})", color=0xFAA61A, description=description
        )
        if data.get("profile_url"):
            embed.url = data["profile_url"]
        for field_name, value in fields:
            embed.add_field(name=field_name, value=value, inline=True)
        await message.reply(embed=embed)
