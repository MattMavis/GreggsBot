import logging
import os
from zoneinfo import ZoneInfo

from .modules.raidschedule import DAY_MESSAGE, HOUR_MESSAGE, parse_reminders

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, env=None):
        env = os.environ if env is None else env

        def get(name, default=""):
            return (env.get(name) or "").strip() or default

        def names(name, default=""):
            return [part.strip() for part in get(name, default).split(",") if part.strip()]

        def channel_id(name, strict=True):
            if not get(name):
                return None
            try:
                return int(get(name))
            except ValueError:
                if strict:
                    raise ConfigError(f"{name} must be a channel id (a number)")
                logger.warning("%s is not a number, channel logging is disabled", name)

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
        self.raid_roles = names("RAID_ROLE")
        self.raid_channel = channel_id("RAID_CHANNEL")
        try:
            self.raid_reminders = parse_reminders(get("RAID_REMIND", "14:00,1"))
        except ValueError:
            raise ConfigError("RAID_REMIND must be times (14:00) or hours before the raid (1), separated by commas")

        self.raid_day_message = get("RAID_DAY_MESSAGE", DAY_MESSAGE)
        self.raid_hour_message = get("RAID_HOUR_MESSAGE", HOUR_MESSAGE)
        self.raid_setup_id = get("RAID_SETUP_ID", "1")

        self.loot_council_ranks = names("LOOT_COUNCIL_RANKS", "Raider")

        self.dm_log_channel = channel_id("DM_LOG_CHANNEL")
        self.raid_cancel_notices = get("RAID_CANCEL_NOTICES").lower() in ("1", "on", "yes", "true")
        self.gambling_channel = channel_id("GAMBLING_CHANNEL")
        self.bot_chan = channel_id("BOT_CHAN", strict=False)

        self.tz = None
        if get("REMINDER_TZ"):
            try:
                self.tz = ZoneInfo(get("REMINDER_TZ"))
            except Exception:
                raise ConfigError(f"REMINDER_TZ {get('REMINDER_TZ')!r} is not a known timezone")
