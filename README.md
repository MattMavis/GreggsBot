# Greggs Bot

An all purpose Discord bot for the Greggs guild on Draenor-EU. Python 3.9+ and discord.py 2.x.

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

`environment.env` is loaded automatically if it exists in the working directory. See [DEPLOY.md](DEPLOY.md) for running it as a service.

### Message Content Intent

The bot reads command text, so the **Message Content Intent** must be enabled for it in the
[Discord Developer Portal](https://discord.com/developers/applications): your application > Bot >
Privileged Gateway Intents > Message Content Intent. Without it the bot connects fine but sees no
commands.

## Commands

Every command works with the prefix (`!roll`) and as a slash command (`/roll`). Slash-only names: `/duel @user` (for `!roll duel @user`), `/link name` (for quick links) and `/help` (for `!ghelp`).

| Area | Commands | Needs |
|---|---|---|
| Dice | `!roll [max]`, `!roll duel @user` | - |
| Lookups | `!rank`, `!check`, `!token`, `!wcl` | `WCL_TOKEN` for `!wcl` |
| Fun | `!8ball`, `!pasta`, quick links, replies when mentioned | `API` |
| Raids | `!raids`, `!keys` | `WOWUTILS_KEY` |
| Raid officers | `!reminders off 17/11`, `!raidtest`, `!raidtest cancel`, `!raidmessage hour <text>` | `WOWUTILS_KEY` |
| Loot council | `!lootcouncil status`; officers: `!lootcouncil [2]`, `undo`, `reset` | `WOWUTILS_KEY` |
| Gambling | `!points`, `!daily`, `!leaderboard`, `!give @user 50`, `!coinflip 50 tails`, `!slots 50`, `!deathroll @user 100` | - |
| Other | `!ping`, `!ghelp`, direct messages to the bot | `DM_LOG_CHANNEL` for DMs |

Officer commands need a role named `Officer` or `Greggs Bot Maintainer`, or the Manage Server permission.

## Settings

Only `DISCORD_TOKEN` (Developer Portal > Bot > Reset Token) is required.

General:

- `PREFIX` - command prefix, default `!`.
- `BOT_CHAN` - channel id the bot logs to. Unset = log file/console only.
- `REMINDER_TZ` - IANA timezone for the raid-day reminder time and the daily points reset, e.g. `Europe/London`. Default is the machine's local time.
- `DM_LOG_CHANNEL` - channel id that direct messages sent to the bot are copied into anonymously (text and attachments, never the sender). The sender gets a reply saying it was passed on. Empty = DMs are ignored.
- `GAMBLING_CHANNEL` - channel id the gambling commands are limited to. Empty = any channel.

Content and lookups:

- `API` - base URL of the JSON API (a Firebase Realtime Database) serving `links.json`, `answers.json`, `pastas.json` and `botreplies.json`. Without it 8-ball, pasta, quick links and the mention replies are off.
- `GUILD_NAME`, `GUILD_REALM`, `GUILD_REGION` - default guild for `!rank`, `!check` and `!wcl`. Default `Greggs`, `Draenor`, `EU`.
- `RAID` - Raider.IO raid slug to pin for `!rank` (e.g. `tier-mn-1`). Default is the newest raid.
- `WCL_TOKEN` - Warcraft Logs v1 API key (https://www.warcraftlogs.com/profile).

Raids (all need `WOWUTILS_KEY`):

- `WOWUTILS_KEY` - group API key from wowutils.com (your group > Settings > API Access). Turns on the raid calendar, reminders, `!keys` and the loot council.
- `RAID_CHANNEL` - channel id reminders are posted in. Without it only `!raids` works.
- `RAID_ROLE` - name or id of a role to ping in reminders. Several roles: separate with commas.
- `RAID_REMIND` - when to remind, default `14:00,1`: a time on the raid day (`14:00`, in `REMINDER_TZ`) and/or a number of hours before the start (`1`).
- `RAID_DAY_MESSAGE`, `RAID_HOUR_MESSAGE` - default wording of the two reminders. `{link}` becomes the raid planning hub link, built with `RAID_SETUP_ID` (default `1`). A file in `messages/` (written by `!raidmessage`, or by hand; read each time) overrides these.
- `RAID_CANCEL_NOTICES` - `on` to post in `RAID_CHANNEL` when a raid night is cancelled or put back on. Default off.
- `LOOT_COUNCIL_RANKS` - wowutils roster ranks `!lootcouncil` draws from, default `Raider`. Nobody is drawn twice until the whole list has had a turn.

## Files the bot writes

- `state/raid_reminders.json` - reminders already sent, muted nights.
- `state/loot_council.json` - who has had a loot council turn this round.
- `state/points.json` - gambling points. They are worth nothing.
- `messages/raid_day.txt`, `messages/raid_hour.txt` - reminder wording set with `!raidmessage`.
- `log/out.log` - the log (also printed to the console).

## Notes

- Extra mention replies and 8-ball answers live in `greggsbot/data/replies.txt` and `greggsbot/data/answers.txt`, one per line. They are added to the ones from `API`.
- `@bot restart` from someone with the `Greggs Bot Maintainer` role makes the bot exit, so run it under something that restarts it (systemd, or the `Procfile` on Heroku-style hosts).
- A deathroll in progress is lost if the bot restarts, along with both stakes.

## Layout

- `greggsbot/bot.py` - the client; builds the list of modules and routes messages to them.
- `greggsbot/slash.py` - slash commands; each hands over to the same module code as the prefix command.
- `greggsbot/config.py` - settings. `greggsbot/state.py` - JSON files under `state/`. `greggsbot/wowutils.py` - wowutils API client.
- `greggsbot/modules/` - one file per feature. `raidschedule.py` (reminder timing) and `bank.py` (points) have no Discord code and are what the tests mostly cover.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest -q
```
