from ..util import weighted_pick
from .base import ResponderModule


class EightBallModule(ResponderModule):
    name = "8Ball"
    commands = ("8ball",)

    async def help_text(self):
        content = f"__Description__: Ask the Magic 8-Ball a yes/no question\n__Usage__: `{self.config.prefix}8ball [question]`"
        return self.name, content

    async def respond(self, message, word, args):
        if not args:
            await message.reply("Ask a yes/no question and the 8-ball will reach into the future to find the answer.")
            return
        answers = await self.fetch_or_reply(message, self.bot.resources.answers())
        if answers is None:
            return
        answer = weighted_pick([a for a in answers if a.get("content")])
        if answer is None:
            await message.reply("The 8-Ball did not foresee this!")
        else:
            await message.reply(f"\n{answer['content']}")
