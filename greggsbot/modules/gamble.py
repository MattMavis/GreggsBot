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
        bank, players = self.module.bank, [self.challenger, self.opponent]
        skint = next((p for p in players if bank.balance(p.id) < self.amount), None)
        if skint is not None:
            text = f"Deathroll off: {skint.mention} no longer has {self.amount} {COIN}."
            await interaction.response.edit_message(content=text, view=None)
            return
        game = DeathrollGame(bank, players, self.amount, self.message)
        await interaction.response.edit_message(content=game.text(), view=game)

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


class DeathrollGame(discord.ui.View):
    """The Roll button. Players take turns rolling 1-(the last roll); whoever rolls 1 loses."""

    def __init__(self, bank, players, amount, message):
        super().__init__(timeout=60)
        self.bank = bank
        self.players = players
        self.amount = amount
        self.message = message
        self.top = max(100, amount * 10)
        self.turn = 0
        self.lines = []
        # stakes are held while the game runs so nobody can spend them elsewhere
        for player in players:
            bank.add(player.id, -amount)

    def text(self, footer=None):
        header = f"💀 **Deathroll** for {self.amount} {COIN}: {self.players[0].mention} vs {self.players[1].mention}"
        lines = self.lines if len(self.lines) <= 20 else self.lines[:3] + ["..."] + self.lines[-15:]
        footer = footer or f"🎲 {self.players[self.turn].mention} to roll 1-{self.top}. One minute, or you forfeit."
        return "\n".join([header, *lines, footer])

    def settle(self, loser):
        self.stop()
        winner = self.players[1 - self.players.index(loser)]
        self.bank.add(winner.id, 2 * self.amount)
        return winner

    @discord.ui.button(label="Roll", emoji="🎲", style=discord.ButtonStyle.primary)
    async def roll(self, interaction, button):
        player = self.players[self.turn]
        if interaction.user.id != player.id:
            await interaction.response.send_message("It's not your roll.", ephemeral=True)
            return
        roll = random.randint(1, self.top)
        self.lines.append(f"{player.display_name} rolls 1-{self.top}: **{roll}**{' 💀' if roll == 1 else ''}")
        self.top = roll
        if roll == 1:
            winner = self.settle(player)
            footer = f"🎉 {winner.mention} takes {self.amount} {COIN} off {player.mention}."
            await interaction.response.edit_message(content=self.text(footer), view=None)
        else:
            self.turn = 1 - self.turn
            await interaction.response.edit_message(content=self.text(), view=self)

    async def on_timeout(self):
        loser = self.players[self.turn]
        winner = self.settle(loser)
        footer = f"⏰ {loser.mention} didn't roll in time and forfeits. {winner.mention} takes {self.amount} {COIN}."
        try:
            await self.message.edit(content=self.text(footer), view=None)
        except discord.HTTPException:
            logger.exception("Could not finish a timed-out deathroll")


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
        # a slash reply only fills in the "thinking..." placeholder, which never pings, so post a fresh message
        view.message = await message.channel.send(
            f"💀 {message.author.mention} challenges {opponent.mention} to a **deathroll** for {amount} {COIN}! "
            "Take turns rolling; whoever rolls a 1 loses. One minute to answer.",
            view=view,
        )
