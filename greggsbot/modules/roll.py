import asyncio
import logging
import random
import re

from .base import ResponderModule

logger = logging.getLogger(__name__)

DEFAULT_MAX = 100


def get_roll_value(max_value=DEFAULT_MAX):
    if max_value < 1:
        max_value = DEFAULT_MAX
    return random.randint(1, max_value)


def roll_text(roll, max_value):
    text = "🎲 rolls... "
    if roll == 100:
        return text + "💯💯💯💯"
    if roll == max_value:
        return text + f"{max_value} FUUUUUUUUUUUCK"
    special = {
        1: "1... no surprises there 💩",
        69: "69! That's the sex number 🍆💦",
        22: "two little ducks, 22 🦆🦆",
        88: "two fat ladies, 88 🍩",
    }
    return text + special.get(roll, str(roll))


class RollDuel:
    def __init__(self, channel, challenger, opponent, on_finish, timeout=60):
        self.channel = channel
        self.challenger = challenger
        self.opponent = opponent
        self.on_finish = on_finish
        self.timeout = timeout
        self.challenger_roll = None
        self.opponent_roll = None
        self.finished = False
        self.timer = None

    async def start(self, prefix):
        await self.channel.send(
            f"{self.challenger.mention} has challenged {self.opponent.mention} to a roll duel! "
            f"You both have one minute to `{prefix}roll`."
        )
        self.timer = asyncio.create_task(self.wait_for_timeout())

    def wants_roll(self, user):
        return (user.id == self.challenger.id and self.challenger_roll is None) or (
            user.id == self.opponent.id and self.opponent_roll is None
        )

    async def add_roll(self, user, roll):
        # in a self-duel the same person fills the challenger slot first, then the opponent slot
        if user.id == self.challenger.id and self.challenger_roll is None:
            self.challenger_roll = roll
        elif user.id == self.opponent.id and self.opponent_roll is None:
            self.opponent_roll = roll
        else:
            return
        if self.challenger_roll is not None and self.opponent_roll is not None:
            await self.resolve()

    async def resolve(self):
        self.finish()
        c, o = self.challenger_roll, self.opponent_roll
        header = f"🔫 Bang! {self.challenger.mention} {c} vs {o} {self.opponent.mention}\n"
        if c == o:
            await self.channel.send(header + "Oh shit, it's a draw... Everyone wins?")
        else:
            winner = self.challenger if c > o else self.opponent
            await self.channel.send(header + f"🎉 {winner.mention} wins!")

    async def wait_for_timeout(self):
        try:
            await asyncio.sleep(self.timeout)
            self.timer = None
            self.finish()
            await self.channel.send("⏰ Times up!")
            if self.challenger_roll is None and self.opponent_roll is None:
                await self.channel.send("Nobody rolled, what a fucking let down.")
            else:
                missing = self.opponent if self.opponent_roll is None else self.challenger
                present = self.challenger if missing is self.opponent else self.opponent
                await self.channel.send(
                    f"{missing.mention} didn't roll in time. What a wet towel. "
                    f"I guess {present.mention} wins! 🎉 Weey!"
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Roll duel timeout failed")

    def finish(self):
        if self.finished:
            return
        self.finished = True
        if self.timer is not None:
            self.timer.cancel()
        self.on_finish(self)


class RollDuelManager:
    def __init__(self, prefix="!", timeout=60):
        self.prefix = prefix
        self.timeout = timeout
        self.duels = {}

    async def create_duel(self, channel, challenger, opponent):
        duel = RollDuel(channel, challenger, opponent, self.remove, self.timeout)
        for user in (challenger, opponent):
            pending = self.duels.setdefault(user.id, [])
            if duel not in pending:
                pending.append(duel)
        await duel.start(self.prefix)
        return duel

    async def add_player_roll_if_needed(self, user, roll):
        for duel in reversed(self.duels.get(user.id, [])):
            if duel.wants_roll(user):
                await duel.add_roll(user, roll)
                return True
        return False

    def remove(self, duel):
        for user_id in (duel.challenger.id, duel.opponent.id):
            pending = [d for d in self.duels.get(user_id, []) if d is not duel]
            if pending:
                self.duels[user_id] = pending
            else:
                self.duels.pop(user_id, None)


def find_mentioned_user(message, text):
    match = re.fullmatch(r"<@!?(\d+)>", text)
    if not match:
        return None
    return next((u for u in message.mentions if u.id == int(match.group(1))), None)


class RollModule(ResponderModule):
    name = "Roll"
    commands = ("roll",)

    def __init__(self, bot):
        super().__init__(bot)
        self.duels = RollDuelManager(self.config.prefix)

    async def help_text(self):
        prefix = self.config.prefix
        content = f"__Description__: Roll the die! 1-100\n__Usage__: `{prefix}roll [max]`\n__Examples__: `{prefix}roll`, `{prefix}roll 200`"
        return self.name, content

    async def respond(self, message, word, args):
        if args and args[0].lower() == "duel":
            await self.start_duel(message, args[1:])
            return

        max_value = DEFAULT_MAX
        if args:
            try:
                max_value = int(args[0])
            except ValueError:
                pass
        if max_value < 1:
            max_value = DEFAULT_MAX

        roll = get_roll_value(max_value)
        if not args and await self.duels.add_player_roll_if_needed(message.author, roll):
            return
        await message.reply(roll_text(roll, max_value))

    async def start_duel(self, message, args):
        opponent = find_mentioned_user(message, args[0]) if args else None
        if opponent is None:
            await message.reply(f"Usage: `{self.config.prefix}roll duel @user`")
        elif opponent.bot:
            await message.reply("Bots can't roll, they have no fingers. Pick a real opponent.")
        else:
            await self.duels.create_duel(message.channel, message.author, opponent)
