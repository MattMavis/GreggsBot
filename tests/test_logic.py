import asyncio
import random
from types import SimpleNamespace

from greggsbot.config import Config
from greggsbot.modules.base import ResponderModule, parse_command
from greggsbot.modules.raiderio import check_summary, medal, pick_raid_slug, rank_fields
from greggsbot.modules.raidreminder import to_croniter_expr
from greggsbot.modules.roll import RollDuelManager, get_roll_value
from greggsbot.resources import to_list
from greggsbot.util import fmt_number, ordinal, weighted_pick


def test_weighted_pick_respects_weights():
    entries = [{"id": "a", "weight": 1}, {"id": "b", "weight": "99"}]
    picks = [weighted_pick(entries)["id"] for _ in range(500)]
    assert picks.count("b") > 400


def test_weighted_pick_skips_zero_and_missing_weights():
    entries = [{"id": "zero", "weight": 0}, {"id": "none"}, {"id": "bad", "weight": "x"}, {"id": "ok", "weight": 1}]
    assert {weighted_pick(entries)["id"] for _ in range(50)} == {"ok"}
    assert weighted_pick(entries[:3]) is None


def test_roll_can_reach_max_and_falls_back_for_bad_max():
    random.seed(1)
    assert 6 in {get_roll_value(6) for _ in range(200)}
    assert max(get_roll_value(0) for _ in range(500)) > 90


def test_command_word_must_match_exactly():
    assert parse_command("!Roll  50", "!") == ("roll", ["50"])
    assert parse_command("?roll", "!") is None

    class Roll(ResponderModule):
        commands = ("roll",)

    module = Roll(SimpleNamespace(config=Config({"DISCORD_TOKEN": "x", "API": "http://a"})))
    assert asyncio.run(module.is_command("roll"))
    assert not asyncio.run(module.is_command("rollercoaster"))


def test_ordinal_and_medal():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 112)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "112th"]
    assert medal(3) == ":third_place:"
    assert medal(4) == "4"
    assert medal(0) == "-"
    assert medal(None) == "-"


def test_fmt_number():
    assert fmt_number(457695) == "457,695"
    assert fmt_number(22884.75) == "22,884.75"
    assert fmt_number(1.5) == "1.5"


def test_firebase_normalisation():
    assert to_list({"-a": {"x": 1}, "-b": None, "-c": {"x": 2}}) == [{"x": 1}, {"x": 2}]
    assert to_list([None, {"x": 1}, None]) == [{"x": 1}]
    assert to_list(None) == []


def test_six_field_cron_moves_seconds_last():
    assert to_croniter_expr("0 30 19 * * 1") == "30 19 * * 1 0"
    assert to_croniter_expr("30 19 * * 1") == "30 19 * * 1"
    assert to_croniter_expr("nonsense") is None


def test_raid_slug_selection():
    progression = {"tier-mn-1": {}, "sporefall": {}}
    assert pick_raid_slug(progression) == "tier-mn-1"
    assert pick_raid_slug(progression, "sporefall") == "sporefall"
    assert pick_raid_slug(progression, "gone") is None
    assert pick_raid_slug({}) is None


def test_rank_fields_show_dash_for_unranked():
    data = {
        "raid_progression": {"tier-mn-1": {"total_bosses": 9, "mythic_bosses_killed": 2, "heroic_bosses_killed": 9}},
        "raid_rankings": {"tier-mn-1": {"mythic": {"realm": 0, "region": 12}, "heroic": {"realm": 1, "region": 3}}},
    }
    assert rank_fields(data, "tier-mn-1") == [
        ("Tier Mn 1 M 2/9", "S - / R 12th"),
        ("Tier Mn 1 HC 9/9", "S 1st / R 3rd"),
        ("Tier Mn 1 N 0/9", "S - / R -"),
    ]


def test_check_summary_handles_class_without_healer():
    data = {
        "class": "Warrior",
        "mythic_plus_scores_by_season": [{"scores": {"all": 3000, "dps": 3000, "healer": 0, "tank": 2500.5}}],
        "mythic_plus_ranks": {"overall": {"realm": 2}, "dps": {"realm": 40}, "class_dps": {"realm": 7}},
    }
    description, fields = check_summary(data)
    assert description == "Best score: **3000** [dps]"
    assert fields == [("All Classes & Roles", ":second_place:"), ("All DPS", "40"), ("All Warrior DPS", "7")]
    assert check_summary(data, "healer")[1][1:] == [("All Healers", "-"), ("All Warrior Healers", "-")]


class FakeUser:
    bot = False

    def __init__(self, id):
        self.id = id
        self.mention = f"<@{id}>"


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def test_self_duel_resolves_after_two_rolls_and_cleans_up():
    async def run():
        channel, me = FakeChannel(), FakeUser(1)
        manager = RollDuelManager(timeout=5)
        await manager.create_duel(channel, me, me)
        assert await manager.add_player_roll_if_needed(me, 5)
        assert await manager.add_player_roll_if_needed(me, 5)
        assert not await manager.add_player_roll_if_needed(me, 9)
        assert manager.duels == {}
        return channel.sent

    sent = asyncio.run(run())
    assert "5 vs 5" in sent[-1] and "draw" in sent[-1]


def test_duel_winner_is_higher_roll():
    async def run():
        channel, a, b = FakeChannel(), FakeUser(1), FakeUser(2)
        manager = RollDuelManager(timeout=5)
        await manager.create_duel(channel, a, b)
        await manager.add_player_roll_if_needed(b, 80)
        await manager.add_player_roll_if_needed(a, 20)
        return channel.sent[-1]

    assert "<@2> wins" in asyncio.run(run())


def test_duel_timeout_removes_duel_from_both_players():
    async def run():
        channel, a, b = FakeChannel(), FakeUser(1), FakeUser(2)
        manager = RollDuelManager(timeout=0.01)
        await manager.create_duel(channel, a, b)
        await manager.add_player_roll_if_needed(a, 10)
        await asyncio.sleep(0.1)
        return manager.duels, channel.sent

    duels, sent = asyncio.run(run())
    assert duels == {}
    assert "<@2> didn't roll in time" in sent[-1]


def test_raid_calendar_reminders():
    from datetime import datetime, timedelta, timezone

    from greggsbot.modules.raidcalendar import due_reminders, parse_reminders, signup_line

    tz = timezone.utc
    night = {
        "eventId": "e1", "date": "2026-11-18", "startTime": "20:00", "status": "planned", "rosterSize": 3,
        "signups": [
            {"status": "present", "responded": True},
            {"status": "late", "responded": True},
            {"status": "pending", "responded": False},
        ],
    }
    cancelled = dict(night, eventId="e2", status="cancelled")
    start = datetime(2026, 11, 18, 20, 0, tzinfo=tz)

    reminders = parse_reminders("14:00, 1")

    def due(now, sent=()):
        return [key for _, _, key in due_reminders([night, cancelled], tz, now, reminders, set(sent), tz)]

    assert due(start - timedelta(hours=1)) == ["e1|before1.0"]
    assert due(start.replace(hour=14, minute=10)) == ["e1|at(14, 0)"]
    assert due(start - timedelta(hours=1), sent=["e1|before1.0"]) == []
    assert due(start - timedelta(hours=3)) == []
    assert signup_line(night) == "2/3 coming · 1 not answered"

    from greggsbot.modules.raidcalendar import find_night, upcoming

    nights = upcoming([night], tz, start - timedelta(days=2))
    assert find_night(nights, "18/11", tz)[1] is night
    assert find_night(nights, "19/11", tz) is None


def test_raid_reminder_clock_time_is_local_not_group_zone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from greggsbot.modules.raidcalendar import fire_time

    start = datetime(2026, 11, 15, 21, 0, tzinfo=ZoneInfo("Europe/Paris"))
    fire = fire_time(start, ("at", (14, 0)), ZoneInfo("Europe/London"))
    assert fire == datetime(2026, 11, 15, 14, 0, tzinfo=ZoneInfo("Europe/London"))


def test_slash_commands_follow_loaded_modules():
    from greggsbot.bot import GreggsBot
    from greggsbot.modules.help import HelpModule
    from greggsbot.modules.roll import RollModule
    from greggsbot.slash import register

    bot = GreggsBot(Config({"DISCORD_TOKEN": "x"}))
    bot.modules = [RollModule(bot), HelpModule(bot)]
    register(bot)
    assert sorted(c.name for c in bot.tree.get_commands()) == ["duel", "help", "roll"]


def test_officer_role_can_manage_reminders():
    from greggsbot.modules.base import can_manage

    member = lambda *names: SimpleNamespace(roles=[SimpleNamespace(name=n) for n in names], guild_permissions=None)
    assert can_manage(member("Officer"))
    assert not can_manage(member("Raider"))


def test_loot_council_never_repeats_within_a_round():
    from greggsbot.modules.lootcouncil import draw

    roster = ["a", "b", "c"]
    picked, seen = [], []
    for _ in range(3):
        chosen, picked, restarted = draw(roster, picked, 1)
        seen += chosen
        assert not restarted
    assert sorted(seen) == roster

    chosen, picked, restarted = draw(roster, picked, 1)
    assert restarted and picked == chosen

    # two left in the hat, three wanted: the round restarts mid-draw without repeating anyone in this draw
    chosen, picked, restarted = draw(roster, ["a"], 3)
    assert sorted(chosen) == roster and restarted

    # someone who left the roster is forgotten
    assert draw(["a", "b"], ["a", "gone"], 1)[0] == ["b"]


def test_raid_cancellation_is_announced_once():
    from greggsbot.modules.raidcalendar import status_changes

    night = {"eventId": "e1", "status": "planned"}
    changed, known = status_changes([night], {})
    assert changed == [] and known == {"e1": "planned"}

    cancelled = dict(night, status="cancelled")
    changed, known = status_changes([cancelled], known)
    assert changed == [cancelled]
    assert status_changes([cancelled], known)[0] == []


def test_key_run_text_shows_open_seats():
    from datetime import timezone

    from greggsbot.modules.mythickeys import run_text

    run = {
        "date": "2026-11-20", "startTime": "20:30", "dungeons": [{"name": "Ara-Kara"}], "note": "push week",
        "slots": [
            {"slotId": "tank", "characterName": "Thrall"},
            {"slotId": "healer", "characterName": None, "guestName": None},
            {"slotId": "dps-1", "characterName": None, "guestName": "Jaina"},
        ],
    }
    text = run_text(run, timezone.utc)
    assert "**Ara-Kara** *(push week)*" in text
    assert text.endswith("🛡️ Thrall · 💚 *open* · ⚔️ Jaina")


def test_raid_message_file_overrides_setting(tmp_path, monkeypatch):
    from greggsbot.modules.raidcalendar import MESSAGE_FILES, RaidCalendarModule

    monkeypatch.chdir(tmp_path)
    config = Config({"DISCORD_TOKEN": "x", "RAID_HOUR_MESSAGE": "from settings"})
    module = RaidCalendarModule(SimpleNamespace(config=config))
    assert module.message_text("before") == "from settings"

    (tmp_path / "messages").mkdir()
    (tmp_path / MESSAGE_FILES["before"]).write_text("from file\n", encoding="utf-8")
    assert module.message_text("before") == "from file"


def test_extra_replies_and_answers_load():
    from greggsbot.util import extra_entries

    replies = extra_entries("replies.txt")
    assert len(replies) > 20 and all(r["content"] and not r["content"].startswith("#") for r in replies)
    assert len(extra_entries("answers.txt")) >= 20
    assert extra_entries("missing.txt") == []


def test_dm_embed_carries_sender_and_text():
    from datetime import datetime, timezone

    from greggsbot.modules.dmlog import dm_embed

    class Author:
        mention = "<@1>"
        display_avatar = SimpleNamespace(url="https://example.invalid/a.png")

        def __str__(self):
            return "thrall"

    message = SimpleNamespace(
        author=Author(), content="hello officers", attachments=[], created_at=datetime(2026, 11, 14, tzinfo=timezone.utc)
    )
    fields = {f.name: f.value for f in dm_embed(message).fields}
    assert fields == {"Sent By": "thrall (<@1>)", "Message:": "hello officers"}
