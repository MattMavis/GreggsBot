# Deploying Greggs Bot

The bot is one long-running Python process. It needs Python 3.11 or newer, outbound internet, and a handful of settings. It does not need a web port or a database.

Do part 1 once, then pick one of the hosting options in part 3.

## 1. Set up the bot in Discord

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and open your application (or create one with **New Application**).
2. Open **Bot**:
   - Click **Reset Token** and copy the token. This is `DISCORD_TOKEN`. Treat it like a password.
   - Under **Privileged Gateway Intents**, switch on **Message Content Intent**. Without it the bot connects but never sees a command.
3. Open **OAuth2 > URL Generator** to invite the bot to your server:
   - Scopes: `bot`
   - Bot permissions: `View Channels`, `Send Messages`, `Embed Links`, `Read Message History`, `Mention Everyone`
   - Open the generated URL and pick your server.
4. In your server, create a role named exactly `Greggs Bot Maintainer` and give it to whoever may restart the bot with `@GreggsBot restart`.

`Mention Everyone` is only needed so raid reminders can ping roles that are not set as mentionable.

## 2. Settings

| Name | Required | What it is |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | The bot token from step 1. |
| `API` | no | Without it 8-ball, pasta and quick links are switched off. Base URL of the JSON API that serves links, pastas, 8-ball answers, reminders and mention replies. |
| `PREFIX` | no | Command prefix. Default `!`. |
| `WOWUTILS_KEY` | no | Group API key from wowutils.com (your group > Settings > API Access). Turns on `!raids` and calendar reminders. |
| `RAID_CHANNEL` | no | ID of the channel raid reminders are posted in. |
| `RAID_ROLE` | no | Name or ID of a role to ping in raid reminders. Several roles: separate with commas. |
| `RAID_REMIND` | no | When to remind: a time on the raid day (`14:00`) and/or hours before the start (`1`). Default `14:00,1`. |
| `WCL_TOKEN` | no | Warcraft Logs v1 API key, from the bottom of <https://www.warcraftlogs.com/profile>. Needed for `!wcl`. |
| `BOT_CHAN` | no | ID of a channel the bot posts its own status messages to. |
| `REMINDER_TZ` | no | Timezone for raid reminder times, e.g. `Europe/London`. |
| `GUILD_NAME`, `GUILD_REALM`, `GUILD_REGION` | no | Default guild for `!rank`, `!check` and `!wcl`. Default `Greggs`, `Draenor`, `EU`. |
| `RAID` | no | Raider.IO raid slug to pin for `!rank`. Default is the newest raid. |

Two things to know:

- **Set `REMINDER_TZ` on any hosted server.** Hosted machines usually run on UTC, so without it reminders fire an hour out during British Summer Time.
- **To get a channel ID** for `BOT_CHAN`, turn on Discord's **Settings > Advanced > Developer Mode**, then right-click the channel and choose **Copy Channel ID**.

## 3. Hosting options

### Option A: your own PC (quickest, good for testing)

In a terminal in the repo folder:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy environment.env.example environment.env
```

Fill in `environment.env`, then start the bot:

```
python -m greggsbot
```

The bot is online only while this window is open. `@GreggsBot restart` makes it exit, so to have it come back by itself, save this as `run.bat` in the repo folder and start that instead:

```
:loop
.venv\Scripts\python -m greggsbot
timeout /t 5
goto loop
```

### Option B: a Linux server or Raspberry Pi (runs 24/7)

1. Get the code and install it:

   ```
   sudo apt install -y python3 python3-venv git
   git clone https://github.com/MattMavis/GreggsBot.git
   cd GreggsBot
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp environment.env.example environment.env
   nano environment.env
   chmod 600 environment.env
   ```

2. Check it starts, then stop it with Ctrl+C:

   ```
   .venv/bin/python -m greggsbot
   ```

3. Create `/etc/systemd/system/greggsbot.service` so it starts on boot and restarts after a crash or a `restart` command. Replace `YOUR_USER` with your login name in all three places:

   ```
   [Unit]
   Description=Greggs Bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=YOUR_USER
   WorkingDirectory=/home/YOUR_USER/GreggsBot
   ExecStart=/home/YOUR_USER/GreggsBot/.venv/bin/python -m greggsbot
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

4. Turn it on:

   ```
   sudo systemctl daemon-reload
   sudo systemctl enable --now greggsbot
   ```

Useful commands afterwards:

- `sudo systemctl status greggsbot` shows whether it is running.
- `journalctl -u greggsbot -f` follows the live log.
- `sudo systemctl restart greggsbot` restarts it.

### Option C: Heroku, Railway or a similar host

The repo's `Procfile` already tells these hosts what to run (`worker: python -m greggsbot`).

1. Create an app and connect it to the GitHub repo, on the branch you want to deploy.
2. Add each setting from part 2 as a config variable in the host's dashboard. `environment.env` is not uploaded, so the file is not used here.
3. Make sure one **worker** process is running and no **web** process. On Heroku: **Resources** tab, switch `worker` on, or run `heroku ps:scale worker=1 web=0`.
4. If the host asks for a Python version, add a file named `.python-version` to the repo containing `3.13`.

These hosts restart the process when it exits, so `@GreggsBot restart` works without extra setup. Free tiers that put idle apps to sleep are not suitable, because a sleeping bot is offline.

## 4. Check it is working

1. The bot shows as online in the member list.
2. If `BOT_CHAN` is set, it posts "bot started bleep bloop" there.
3. `!ghelp` replies with the command list.
4. `!roll` and `!token` reply. These need nothing but the bot itself.
5. `!8ball will this work?` replies. This one confirms the `API` setting is right (skip it if you run without `API`).

The log line `Scheduling X of Y reminders` at startup tells you how many raid reminders were accepted. A rejected reminder gets its own line saying why.

## 5. Updating

Pull the new code and restart:

```
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart greggsbot
```

On Windows use `.venv\Scripts\pip` and restart the window or `run.bat`. On Heroku-style hosts, pushing to the deployed branch redeploys.

Raid reminders are read once at startup, so restart the bot after changing them. Links, pastas and replies refresh by themselves within five minutes.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Exits at once with `Missing required environment variable(s)` | `DISCORD_TOKEN` is empty or the settings file was not found. Run from the repo folder. |
| Exits with `PrivilegedIntentsRequired` | Message Content Intent is off (part 1, step 2). |
| Exits with `Improper token has been passed` | The token is wrong or was reset. Copy a fresh one. |
| Online but ignores every command | Wrong `PREFIX`, or the bot cannot see or post in that channel. |
| `!roll` works but `!8ball` and `!pasta` say "trouble fetching" | `API` is wrong or the JSON API is down. |
| Replies arrive without the embed box | The bot lacks the `Embed Links` permission. |
| Reminders fire at the wrong hour | Set `REMINDER_TZ`. |
| Reminders never fire | Check the startup log for the rejected reminder and its reason. |

The full log is in `log/out.log` next to the code (or in the host's log viewer for option C).
