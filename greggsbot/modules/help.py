from .base import ResponderModule

LIMIT = 2000


def split_messages(header, sections, limit=LIMIT):
    """Packs help sections into messages under the limit, splitting only between sections."""
    chunks = []
    current = header
    for section in sections:
        while len(section) > limit:
            # a single module that is too long on its own has to be cut
            cut = section.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(section[:cut])
            section = section[cut:].lstrip("\n")
        gap = "\n" if current == header else "\n\n"
        if current and len(current) + len(gap) + len(section) > limit:
            chunks.append(current)
            current = ""
        current = f"{current}{gap}{section}" if current else section
    if current:
        chunks.append(current)
    return chunks


class HelpModule(ResponderModule):
    name = "Helper"
    commands = ("ghelp",)

    async def respond(self, message, word, args):
        sections = []
        for module in self.bot.modules:
            help_ = await module.help_text()
            if help_ is not None:
                name, content = help_
                sections.append(f"__**{name}**__\n{content}")

        header = "Alright love, I'm Greggs Bot and here's what I can do:"
        chunks = split_messages(header, sections)
        await message.reply(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)
