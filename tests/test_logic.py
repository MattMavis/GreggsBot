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
