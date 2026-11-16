import random
from datetime import datetime

from .bank import COIN, DAILY, START, Bank
from .base import NOBODY, ResponderModule, find_mentioned_user
from .deathroll import Deathroll

REELS = [COIN, "🥧", "🍩", "🍪", "☕", "💎"]


def slot_payout(reels):
    """What a spin pays back per point staked."""
    kinds = len(set(reels))
    if kinds == 1:
        return 25 if reels[0] == "💎" else 10
    return 1.5 if kinds == 2 else 0


def parse_wager(text, balance):
    """A stake between 1 and the balance ('all' for everything), or None."""
    amount = balance if str(text).lower() == "all" else int(text) if str(text).isdigit() else 0
    return amount if 1 <= amount <= balance else None


class GambleModule(ResponderModule):
    name = "Gambling"
    commands = ("points", "daily", "leaderboard", "give", "coinflip", "slots", "deathroll")

    def __init__(self, bot):
        super().__init__(bot)
        self.bank = Bank()
        self.arena = Deathroll(self)
        self.games = self.arena.games

    def game_of(self, channel, user):
        return self.arena.game_of(channel, user)

    async def take_roll(self, message):
        return await self.arena.take_roll(message)

    async def deathroll(self, message, args):
        await self.arena.challenge(message, args)

    async def help_text(self):
        p = self.config.prefix
        content = (
            f"__Description__: Gamble away your {COIN}. They're worth nothing. Everyone starts with {START}.\n"
            f"__Bank__: `{p}points [@user]`, `{p}daily` (+{DAILY}), `{p}leaderboard`, `{p}give @user 50`\n"
            f"__Games__: `{p}coinflip 50 [heads|tails]`, `{p}slots 50`, `{p}deathroll @user 100`\n"
            "Use `all` instead of a number to stake the lot."
        )
        return self.name, content

    async def respond(self, message, word, args):
        allowed = self.config.gambling_channel
        if allowed and message.channel.id != allowed:
            await message.reply(f"Not in here. Gambling lives in <#{allowed}>.")
            return
        await getattr(self, word)(message, args)

    async def wager(self, message, text, usage):
        """The stake the author asked for, or None after telling them why not."""
        balance = self.bank.balance(message.author.id)
        amount = parse_wager(text, balance)
        if amount is None and balance == 0:
            await message.reply(f"You're skint. Come back for your `{self.config.prefix}daily`.")
        elif amount is None:
            await message.reply(f"Usage: `{self.config.prefix}{usage}`. You have {balance} {COIN}.")
        return amount

    async def points(self, message, args):
        user = (find_mentioned_user(message, args[0]) if args else None) or message.author
        await message.reply(f"{user.mention} has {self.bank.balance(user.id)} {COIN}.", allowed_mentions=NOBODY)

    async def daily(self, message, args):
        today = datetime.now(self.config.tz).date().isoformat()
        if self.bank.claim_daily(message.author.id, today):
            balance = self.bank.balance(message.author.id)
            await message.reply(f"Here's your {DAILY} {COIN} dole money. You now have {balance}.")
        else:
            await message.reply("You've had today's handout already. Greedy.")

    async def leaderboard(self, message, args):
        medals = ["🥇", "🥈", "🥉"]
        lines = [
            f"{medals[i] if i < 3 else f'{i + 1}.'} <@{user_id}>: {points} {COIN}"
            for i, (user_id, points) in enumerate(self.bank.top(10))
        ]
        text = "**Richest degenerates**\n" + ("\n".join(lines) or "Nobody has played yet.")
        await message.reply(text, allowed_mentions=NOBODY)

    async def give(self, message, args):
        target = find_mentioned_user(message, args[0]) if args else None
        if target is None or target.bot or target.id == message.author.id:
            await message.reply(f"Usage: `{self.config.prefix}give @user 50`")
            return
        amount = await self.wager(message, args[1] if len(args) > 1 else "", "give @user 50")
        if amount is None:
            return
        self.bank.add(message.author.id, -amount)
        self.bank.add(target.id, amount)
        await message.reply(f"💸 {message.author.mention} gave {target.mention} {amount} {COIN}. Charity case.")

    async def coinflip(self, message, args):
        amount = await self.wager(message, args[0] if args else "", "coinflip 50 [heads|tails]")
        if amount is None:
            return
        call = args[1].lower() if len(args) > 1 and args[1].lower() in ("heads", "tails") else "heads"
        landed = random.choice(("heads", "tails"))
        won = call == landed
        self.bank.add(message.author.id, amount if won else -amount)
        outcome = f"You win {amount} {COIN}! 🎉" if won else f"You lose {amount} {COIN}. Unlucky, dickhead."
        balance = self.bank.balance(message.author.id)
        await message.reply(f"🪙 You called **{call}**, it landed **{landed}**. {outcome} Balance: {balance}.")

    async def slots(self, message, args):
        amount = await self.wager(message, args[0] if args else "", "slots 50")
        if amount is None:
            return
        reels = [random.choice(REELS) for _ in range(3)]
        payout = int(amount * slot_payout(reels))
        self.bank.add(message.author.id, payout - amount)
        if payout > amount:
            outcome = f"{'JACKPOT! ' if len(set(reels)) == 1 else ''}You win {payout - amount} {COIN}! 🎉"
        elif payout == amount:
            outcome = "You get your stake back. Thrilling."
        else:
            outcome = f"You lose {amount} {COIN}. The house thanks you."
        balance = self.bank.balance(message.author.id)
        await message.reply(f"🎰 [ {' | '.join(reels)} ] {outcome} Balance: {balance}.")
