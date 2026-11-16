import asyncio
import logging
import random

import discord

from .bank import COIN
from .base import NOBODY, find_mentioned_user

logger = logging.getLogger(__name__)

TURN_SECONDS = 60
TIDY_SECONDS = 300


class Challenge(discord.ui.View):
    """The Accept / Decline buttons under a deathroll challenge."""

    def __init__(self, arena, challenger, opponent, amount):
        super().__init__(timeout=60)
        self.arena = arena
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
        arena, players = self.arena, [self.challenger, self.opponent]
        skint = arena.skint(players, self.amount)
        busy = arena.busy(interaction.channel, players)
        if skint or busy:
            if skint:
                why = f"{skint.mention} no longer has {self.amount} {COIN}"
            else:
                why = f"{busy.mention} is already in one here"
            await interaction.response.edit_message(content=f"Deathroll off: {why}.", view=None)
            return
        game = DeathrollGame(arena, interaction.channel, players, self.amount)
        header = f"💀 **Deathroll** for {self.amount} {COIN}: {players[0].mention} vs {players[1].mention}. It's on."
        await interaction.response.edit_message(content=header, view=None)
        game.messages.append(self.message)
        await game.send_turn()

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


class RollButton(discord.ui.View):
    """A Roll button under one turn's prompt. Does the same as the roll command."""

    def __init__(self, game):
        super().__init__(timeout=TURN_SECONDS)
        self.game = game
        self.rolls = game.rolls

    @discord.ui.button(label="Roll", emoji="🎲", style=discord.ButtonStyle.primary)
    async def roll(self, interaction, button):
        game = self.game
        if game.over or game.rolls != self.rolls:
            await interaction.response.edit_message(view=None)
        elif interaction.user.id != game.players[game.turn].id:
            await interaction.response.send_message("It's not your roll.", ephemeral=True)
        else:
            await interaction.response.defer()
            await game.roll(interaction.user)


class DeathrollGame:
    """Players take turns using the roll command, rolling 1-(the last roll). Whoever rolls 1 loses."""

    def __init__(self, arena, channel, players, amount):
        self.arena = arena
        self.channel = channel
        self.players = players
        self.amount = amount
        self.top = max(100, amount * 10)
        self.turn = 0
        self.rolls = 0
        self.over = False
        self.prompt_message = None
        self.messages = []
        self.timer = None
        # stakes are held while the game runs so nobody can spend them elsewhere
        for player in players:
            arena.bank.add(player.id, -amount)
        arena.games.append(self)
        self.wait()

    def prompt(self):
        player = self.players[self.turn]
        prefix = self.arena.config.prefix
        return (
            f"🎲 {player.mention}, hit Roll or `/roll` (or `{prefix}roll`) for 1-{self.top}. "
            "One minute, or you forfeit."
        )

    async def send_turn(self, text=""):
        self.prompt_message = await self.channel.send(f"{text}\n{self.prompt()}".strip(), view=RollButton(self))
        self.messages.append(self.prompt_message)

    async def tidy(self):
        """Once it's over, removes the roll-by-roll messages after a while. The result message stays."""
        await self.clear_button()
        for message in self.messages:
            await message.delete(delay=TIDY_SECONDS)

    async def clear_button(self):
        message, self.prompt_message = self.prompt_message, None
        if message is not None:
            try:
                await message.edit(view=None)
            except discord.HTTPException:
                pass

    def wait(self):
        if self.timer is not None:
            self.timer.cancel()
        self.timer = asyncio.create_task(self.forfeit())

    def settle(self, loser):
        if self.timer is not None:
            self.timer.cancel()
        self.over = True
        self.arena.games.remove(self)
        winner = self.players[1 - self.players.index(loser)]
        self.arena.bank.add(winner.id, 2 * self.amount)
        return winner

    async def roll(self, player):
        # a forfeit can land while a button click is being acknowledged
        if self.over:
            return
        roll = random.randint(1, self.top)
        text = f"🎲 {player.display_name} rolls 1-{self.top}: **{roll}**"
        self.top = roll
        self.rolls += 1
        if roll == 1:
            winner = self.settle(player)
            await self.tidy()
            await self.channel.send(f"{text} 💀\n🎉 {winner.mention} takes {self.amount} {COIN} off {player.mention}.")
        else:
            self.turn = 1 - self.turn
            self.wait()
            await self.clear_button()
            await self.send_turn(text)

    async def forfeit(self):
        try:
            await asyncio.sleep(TURN_SECONDS)
            self.timer = None
            loser = self.players[self.turn]
            winner = self.settle(loser)
            await self.tidy()
            await self.channel.send(
                f"⏰ {loser.mention} didn't roll in time and forfeits. {winner.mention} takes {self.amount} {COIN}."
            )
        except Exception:
            logger.exception("Deathroll forfeit failed")


class Deathroll:
    """The live games in a GambleModule and the rules for starting and joining them."""

    def __init__(self, module):
        self.bank = module.bank
        self.config = module.config
        self.wager = module.wager
        self.games = []

    def game_of(self, channel, user):
        return next(
            (g for g in self.games if g.channel.id == channel.id and any(p.id == user.id for p in g.players)), None
        )

    def busy(self, channel, players):
        return next((p for p in players if self.game_of(channel, p)), None)

    def skint(self, players, amount):
        return next((p for p in players if self.bank.balance(p.id) < amount), None)

    async def take_roll(self, message):
        """Uses the author's roll command for their deathroll in this channel. False if they aren't in one."""
        game = self.game_of(message.channel, message.author)
        if game is None:
            return False
        if game.players[game.turn].id != message.author.id:
            await message.reply("It's not your roll.")
        else:
            await game.roll(message.author)
        return True

    async def challenge(self, message, args):
        usage = "deathroll @user 100"
        opponent = find_mentioned_user(message, args[0]) if args else None
        if opponent is None or opponent.bot or opponent.id == message.author.id:
            await message.reply(f"Usage: `{self.config.prefix}{usage}` (a real person, and not yourself)")
            return
        amount = await self.wager(message, args[1] if len(args) > 1 else "", usage)
        if amount is None:
            return
        busy = self.busy(message.channel, (message.author, opponent))
        if busy is not None:
            text = f"{busy.mention} is already in a deathroll here. One at a time."
            await message.reply(text, allowed_mentions=NOBODY)
            return
        if self.skint([opponent], amount):
            balance = self.bank.balance(opponent.id)
            text = f"{opponent.mention} can't afford that, they only have {balance} {COIN}."
            await message.reply(text, allowed_mentions=NOBODY)
            return
        view = Challenge(self, message.author, opponent, amount)
        # a slash reply only fills in the "thinking..." placeholder, which never pings, so post a fresh message
        view.message = await message.channel.send(
            f"💀 {message.author.mention} challenges {opponent.mention} to a **deathroll** for {amount} {COIN}! "
            "Take turns rolling; whoever rolls a 1 loses. One minute to answer.",
            view=view,
        )
