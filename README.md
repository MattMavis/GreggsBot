# Greggs Bot

An all purpose Discord bot for the Greggs guild on Draenor-EU. Python 3.11+ and discord.py 2.x.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy environment.env.example environment.env     # Linux/macOS: cp
```

Fill in `environment.env`, then run:

```
python -m greggsbot
```

### Message Content Intent

The bot reads command text, so the **Message Content Intent** must be enabled for it in the
[Discord Developer Portal](https://discord.com/developers/applications): your application > Bot >
Privileged Gateway Intents > Message Content Intent. Without it the bot connects fine but sees no
commands.

### Environment variables

Required:

- `DISCORD_TOKEN` - bot token (Developer Portal > Bot > Reset Token).

Optional:

- `API` - base URL of the JSON API (a Firebase Realtime Database) serving `raids.json`, `links.json`, `answers.json`, `pastas.json`, `reminders.json` and `botreplies.json`. Without it 8-ball, pasta, quick links, raid reminders and guides are switched off.
- `WOWUTILS_KEY` - group API key from wowutils.com (your group > Settings > API Access). Turns on `!raids` and raid reminders read from the group's calendar.
- `RAID_CHANNEL` - channel id reminders are posted in. Without it only `!raids` works.
- `RAID_ROLE` - name of a role to ping in reminders.
- `RAID_REMIND_HOURS` - hours before each raid to remind, default `24,1`. Reminders 12 hours or more ahead also name who hasn't answered the signup.
- `WCL_TOKEN` - Warcraft Logs v1 API key (https://www.warcraftlogs.com/profile). Without it `!wcl` says logs aren't configured.
- `PREFIX` - command prefix, default `!`.
- `BOT_CHAN` - channel id the bot logs to. Unset = log file/console only.
- `GUILD_NAME`, `GUILD_REALM`, `GUILD_REGION` - default guild for `!rank`, `!check` and `!wcl`. Default `Greggs`, `Draenor`, `EU`.
- `REMINDER_TZ` - IANA timezone for raid reminder cron times, e.g. `Europe/London`. Default is the machine's local time.
- `RAID` - Raider.IO raid slug to pin for `!rank` (e.g. `tier-mn-1`). Default is the newest raid.

`environment.env` is loaded automatically if it exists in the working directory.

## Notes

- Logs go to the console and `log/out.log`.
- `@bot restart` from someone with the `Greggs Bot Maintainer` role makes the bot exit, so run it under something that restarts it (the `Procfile` does this on Heroku-style hosts).
- Reminder cron expressions can have 5 fields, or 6 with seconds first (like node-cron).

## Tests

```
pip install -r requirements-dev.txt
python -m pytest -q
```
