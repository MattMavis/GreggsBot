import logging
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, env=None):
        env = os.environ if env is None else env

        def get(name, default=""):
            return (env.get(name) or "").strip() or default

        if not get("DISCORD_TOKEN"):
            raise ConfigError("Missing required environment variable: DISCORD_TOKEN")

        self.token = get("DISCORD_TOKEN")
        self.api = get("API").rstrip("/") + "/" if get("API") else ""
        self.wcl_token = get("WCL_TOKEN")
        self.prefix = get("PREFIX", "!")
        self.guild_name = get("GUILD_NAME", "Greggs")
        self.guild_realm = get("GUILD_REALM", "Draenor")
        self.guild_region = get("GUILD_REGION", "EU").upper()
        self.raid = get("RAID")

        self.bot_chan = None
        if get("BOT_CHAN"):
            try:
                self.bot_chan = int(get("BOT_CHAN"))
            except ValueError:
                logger.warning("BOT_CHAN is not a number, channel logging is disabled")

        self.tz = None
        if get("REMINDER_TZ"):
            try:
                self.tz = ZoneInfo(get("REMINDER_TZ"))
            except Exception:
                raise ConfigError(f"REMINDER_TZ {get('REMINDER_TZ')!r} is not a known timezone")
