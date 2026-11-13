import json
import logging
import os
import random

from .base import ResponderModule, can_manage

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join("state", "loot_council.json")


def draw(eligible, picked, count):
    """Picks `count` ids nobody has had this round. Returns (chosen, picked, restarted).

    When the round runs out the list starts over, so nobody is picked twice
    before everyone has been picked once.
    """
    picked = [p for p in picked if p in eligible]
    chosen = []
    restarted = False
    while len(chosen) < min(count, len(eligible)):
        pool = [m for m in eligible if m not in picked and m not in chosen]
        if not pool:
            picked = []
            restarted = True
            continue
        pick = random.choice(pool)
        chosen.append(pick)
        picked.append(pick)
    return chosen, picked, restarted


class LootCouncilModule(ResponderModule):
    name = "Loot Council"
    commands = ("lootcouncil",)

    def __init__(self, bot, wowutils):
        super().__init__(bot)
        self.wowutils = wowutils
        self.picked, self.last = self.load_state()

    async def help_text(self):
        p = self.config.prefix
        content = (
            "__Description__: Draws this week's loot council from the roster. Nobody is drawn twice until everyone has had a turn.\n"
            f"__Usage__: `{p}lootcouncil status`\n"
            f"__Officers__: `{p}lootcouncil` or `{p}lootcouncil 2` to draw, `{p}lootcouncil undo`, `{p}lootcouncil reset`"
        )
        return self.name, content

    async def roster(self):
        """Eligible members as {memberId: display name}."""
        group_id = await self.wowutils.group()
        data, _ = await self.wowutils.request(f"/groups/{group_id}/roster")
        ranks = [r.lower() for r in self.config.loot_council_ranks]
        members = {}
        for member in data.get("members") or []:
            if ranks and str(member.get("rank", "")).lower() not in ranks:
                continue
            members[str(member.get("memberId"))] = str(member.get("displayName") or "?")
        return members

    async def respond(self, message, word, args):
        action = args[0].lower() if args else "draw"
        if action != "status" and not can_manage(message.author):
            await message.reply("Nice try. Only officers get to shake the hat.")
            return

        if action == "reset":
            self.picked, self.last = [], []
            self.save_state()
            await message.reply("Loot council list wiped. Everyone is back in the hat.")
            return

        members = await self.fetch_or_reply(message, self.roster())
        if members is None:
            return
        if not members:
            await message.reply("There's nobody on the roster to pick from.")
            return

        if action == "status":
            await message.reply(self.status_text(members))
        elif action == "undo":
            await self.undo(message, members)
        elif action == "draw" or action.isdigit():
            await self.draw(message, members, int(action) if action.isdigit() else 1)
        else:
            p = self.config.prefix
            await message.reply(f"Usage: `{p}lootcouncil`, `{p}lootcouncil 2`, `{p}lootcouncil status|undo|reset`")

    async def draw(self, message, members, count):
        count = max(1, min(count, len(members)))
        chosen, self.picked, restarted = draw(list(members), self.picked, count)
        self.last = chosen
        self.save_state()

        names = ", ".join(f"**{members[m]}**" for m in chosen)
        lines = [f"🎲 This week's loot council: {names}"]
        if restarted:
            lines.append("Everyone had a turn, so the list started over.")
        left = len(members) - len(self.picked)
        lines.append(f"{left} of {len(members)} still to have a turn." if left else "That's the whole roster done. The list starts over next time.")
        await message.reply("\n".join(lines))

    async def undo(self, message, members):
        if not self.last:
            await message.reply("There's no draw to undo.")
            return
        names = ", ".join(f"**{members.get(m, '?')}**" for m in self.last)
        self.picked = [p for p in self.picked if p not in self.last]
        self.last = []
        self.save_state()
        await message.reply(f"Put {names} back in the hat.")

    def status_text(self, members):
        had = sorted(members[m] for m in self.picked if m in members)
        left = sorted(name for m, name in members.items() if m not in self.picked)
        lines = [f"**Loot council round**: {len(had)} of {len(members)} have had a turn."]
        if self.last:
            lines.append("Last draw: " + ", ".join(members.get(m, "?") for m in self.last))
        lines.append("Had a turn: " + (", ".join(had) or "nobody yet"))
        lines.append("Still to go: " + (", ".join(left) or "nobody, the list starts over next draw"))
        return "\n".join(lines)[:2000]

    def load_state(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
            return list(state["picked"]), list(state["last"])
        except (OSError, ValueError, KeyError, TypeError):
            return [], []

    def save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"picked": self.picked, "last": self.last}, f)
