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

        self.wowutils_key = get("WOWUTILS_KEY")
        self.raid_roles = [name.strip() for name in get("RAID_ROLE").split(",") if name.strip()]
        self.raid_channel = None
        if get("RAID_CHANNEL"):
            try:
                self.raid_channel = int(get("RAID_CHANNEL"))
            except ValueError:
                raise ConfigError("RAID_CHANNEL must be a channel id (a number)")
        from .modules.raidcalendar import DAY_MESSAGE, HOUR_MESSAGE, parse_reminders

        try:
            self.raid_reminders = parse_reminders(get("RAID_REMIND", "14:00,1"))
        except ValueError:
            raise ConfigError("RAID_REMIND must be times (14:00) or hours before the raid (1), separated by commas")

        self.raid_day_message = get("RAID_DAY_MESSAGE", DAY_MESSAGE)
        self.raid_hour_message = get("RAID_HOUR_MESSAGE", HOUR_MESSAGE)
        self.raid_setup_id = get("RAID_SETUP_ID", "1")

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
