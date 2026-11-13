import logging
import time

logger = logging.getLogger(__name__)


class HttpError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


async def get_json(session, url, params=None):
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            raise HttpError(resp.status)
        return await resp.json(content_type=None)


def to_list(data):
    """Firebase sends lists as dicts keyed by id, as lists with nulls, or as null."""
    if isinstance(data, dict):
        data = data.values()
    elif not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


class ResourceService:
    def __init__(self, base_url, session, ttl=300, clock=time.monotonic):
        self.base_url = base_url
        self.session = session
        self.ttl = ttl
        self.clock = clock
        self.cache = {}

    async def get(self, name):
        now = self.clock()
        cached = self.cache.get(name)
        if cached and now - cached[0] < self.ttl:
            return cached[1]
        try:
            data = to_list(await get_json(self.session, f"{self.base_url}{name}.json"))
        except Exception:
            if cached is None:
                raise
            logger.warning("Refreshing %s failed, serving stale data", name, exc_info=True)
            data = cached[1]
        self.cache[name] = (now, data)
        return data

    async def links(self):
        return await self.get("links")

    async def answers(self):
        return await self.get("answers")

    async def pastas(self):
        return await self.get("pastas")

    async def reminders(self):
        return await self.get("reminders")

    async def bot_replies(self):
        return await self.get("botreplies")
