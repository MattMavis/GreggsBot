from .resources import HttpError

API = "https://api.wowutils.com/v1"


class WowUtils:
    def __init__(self, bot):
        self.bot = bot
        self.group_id = None

    async def request(self, path, etag=None):
        headers = {"Authorization": f"Bearer {self.bot.config.wowutils_key}"}
        if etag:
            headers["If-None-Match"] = etag
        async with self.bot.session.get(API + path, headers=headers) as resp:
            if resp.status == 304:
                return None, etag
            if resp.status != 200:
                raise HttpError(resp.status)
            return await resp.json(content_type=None), resp.headers.get("ETag")

    async def group(self):
        if self.group_id is None:
            root, _ = await self.request("")
            self.group_id = root["group"]["groupId"]
        return self.group_id
