import json
import logging
import os
import random
from datetime import datetime

import discord

from .base import ResponderModule
from .roll import find_mentioned_user

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join("state", "points.json")
START = 500
DAILY = 200
COIN = "<:SausageRoll:718927129529679945>"
REELS = [COIN,"🥧", "🍩", "🍪", "☕", "💎"]
NOBODY = discord.AllowedMentions.none()


def deathroll(start, roll=random.randint):
    """Rolls 1-start, then 1-(that roll), and so on. Whoever rolls the final 1 loses."""
    rolls = []
    while start > 1:
        start = roll(1, start)
        rolls.append(start)
    return rolls


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


class Bank:
    def __init__(self, path=STATE_FILE):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.accounts = dict(json.load(f))
        except (OSError, ValueError, TypeError):
            self.accounts = {}

    def account(self, user_id):
        return self.accounts.setdefault(str(user_id), {"points": START, "daily": ""})

    def balance(self, user_id):
        return self.account(user_id)["points"]

    def add(self, user_id, amount):
        self.account(user_id)["points"] += amount
        self.save()

    def claim_daily(self, user_id, today):
        account = self.account(user_id)
        if account["daily"] == today:
            return False
        account["daily"] = today
        self.add(user_id, DAILY)
        return True

    def top(self, count):
        ranked = sorted(self.accounts.items(), key=lambda item: -item[1]["points"])
        return [(user_id, account["points"]) for user_id, account in ranked[:count]]

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.accounts, f)
        os.replace(self.path + ".tmp", self.path)


class Challenge(discord.ui.View):
    """The Accept / Decline buttons under a deathroll challenge."""

    def __init__(self, module, challenger, opponent, amount):
        super().__init__(timeout=60)
        self.module = module
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.message = None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("This one isn't for you.", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content=self.module.play_deathroll(self), view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction, button):
        if interaction.user.id not in (self.opponent.id, self.challenger.id):
            await interaction.response.send_message("This one isn't for you.", ephemeral=True)
            return
        self.stop()
        text = f"🐔 {interaction.user.mention} bottled the deathroll. No {COIN} changed hands."
        await interaction.response.edit_message(content=text, view=None)

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            text = f"⏰ {self.opponent.mention} never answered {self.challenger.mention}'s deathroll. Coward."
            await self.message.edit(content=text, view=None)
        except discord.HTTPException:
            logger.exception("Could not expire a deathroll challenge")


class GambleModule(ResponderModule):
    name = "Gambling"
    commands = ("points", "daily", "leaderboard", "give", "coinflip", "slots", "deathroll")

    def __init__(self, bot):
        super().__init__(bot)
        self.bank = Bank()

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

    async def deathroll(self, message, args):
        usage = "deathroll @user 100"
        opponent = find_mentioned_user(message, args[0]) if args else None
        if opponent is None or opponent.bot or opponent.id == message.author.id:
            await message.reply(f"Usage: `{self.config.prefix}{usage}` (a real person, and not yourself)")
            return
        amount = await self.wager(message, args[1] if len(args) > 1 else "", usage)
        if amount is None:
            return
        if self.bank.balance(opponent.id) < amount:
            await message.reply(f"{opponent.mention} can't afford that, they only have {self.bank.balance(opponent.id)} {COIN}.", allowed_mentions=NOBODY)
            return
        view = Challenge(self, message.author, opponent, amount)
        view.message = await message.reply(
            f"💀 {message.author.mention} challenges {opponent.mention} to a **deathroll** for {amount} {COIN}! "
            "Whoever rolls a 1 loses. One minute to answer.",
            view=view,
        )

    def play_deathroll(self, challenge):
        players = (challenge.challenger, challenge.opponent)
        amount = challenge.amount
        skint = next((p for p in players if self.bank.balance(p.id) < amount), None)
        if skint is not None:
            return f"Deathroll off: {skint.mention} no longer has {amount} {COIN}."

        lines = []
        top = max(100, amount * 10)
        rolls = deathroll(top)
        for i, roll in enumerate(rolls):
            lines.append(f"{players[i % 2].display_name} rolls 1-{top}: **{roll}**{' 💀' if roll == 1 else ''}")
            top = roll
        if len(lines) > 20:
            lines = lines[:3] + ["..."] + lines[-15:]
        loser = players[(len(rolls) - 1) % 2]
        winner = players[len(rolls) % 2]
        self.bank.add(loser.id, -amount)
        self.bank.add(winner.id, amount)
        header = f"💀 **Deathroll** for {amount} {COIN}: {players[0].mention} vs {players[1].mention}"
        footer = f"🎉 {winner.mention} takes {amount} {COIN} off {loser.mention}."
        return "\n".join([header, *lines, footer])
