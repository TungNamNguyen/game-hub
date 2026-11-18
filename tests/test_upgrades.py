"""Kiểm thử tổng hợp các nâng cấp mới: Token Auth, Clock & Undo, Geo Streak/Compass/Dynamic, Bluff Reveal/Taunt, Poker AI Bot."""
from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import bots
from bluff import BluffRoom, TAUNTS
from bot_poker import PokerBot, postflop_strength, preflop_strength
from chessgame import ChessRoom
from games import GameError
from geoguessr import (
    GeoRoom,
    compass_direction,
    extract_region,
    infer_region_from_coords,
)
from hub import ProfileStore
from poker import Card, CHIP_START, PokerRoom
from xiangqi import XiangqiRoom


def test_profile_token_bind_and_anti_spoof():
    with TemporaryDirectory() as tmp:
        store = ProfileStore(Path(tmp))
        assert store.verify_or_bind_token("u_alice", "secret_abc") is True
        assert store.verify_or_bind_token("u_alice", "secret_abc") is True
        assert store.verify_or_bind_token("u_alice", "wrong_token") is False
        assert store.verify_or_bind_token("u_alice", "") is False


def test_chess_clock_increment_timeout_and_undo():
    room = ChessRoom("CH01", "standard")
    room.apply_initial_config({"clock": "180+2"})
    assert room.HAS_CLOCK is True
    assert room.clock_initial == 180.0
    assert room.clock_increment == 2.0

    room.join("u1", "Trang", "#fff")
    room.join("u2", "Den", "#000")
    assert room.status == "playing"
    assert room.turn == "X"

    # Simulate 3 seconds spent on first move
    room.turn_started_at = time.time() - 3.0
    room.handle("u1", "move", {"from": 52, "to": 36})  # e2 -> e4
    assert room.turn == "O"
    assert 178.0 <= room.clock_remain["X"] <= 179.5  # 180 - 3 + 2

    # Test human-to-human undo request / decline / accept
    room.handle("u1", "undo", {})
    assert room.undo_offer == "X"
    room.handle("u2", "undo-decline", {})
    assert room.undo_offer == ""
    assert len(room.moves) == 1

    room.handle("u1", "undo", {})
    room.handle("u2", "undo-accept", {})
    assert room.undo_offer == ""
    assert len(room.moves) == 0
    assert room.turn == "X"

    # Simulate timeout on turn O
    room.handle("u1", "move", {"from": 52, "to": 36})
    room.clock_remain["O"] = 0.05
    room.turn_started_at = time.time() - 1.0
    assert room.tick() is True
    assert room.status == "finished"
    assert room.winner == "X"


def test_chess_and_xiangqi_undo_vs_bot():
    # Chess vs Bot: 2-ply immediate rollback
    croom = ChessRoom("CHBT", "standard")
    croom.join("u1", "Human", "#111")
    croom.add_bot("easy")
    croom.handle("u1", "move", {"from": 52, "to": 36})
    assert len(croom.moves) == 1
    bot_player = croom.bot_player()
    assert bot_player is not None
    croom.handle(bot_player.uid, "move", {"from": 12, "to": 28})
    assert len(croom.moves) == 2 and croom.turn == "X"

    croom.handle("u1", "undo", {})
    assert len(croom.moves) == 0
    assert croom.turn == "X"

    # Xiangqi clock & undo vs Bot
    xroom = XiangqiRoom("XQBT", "standard")
    xroom.apply_initial_config({"clock": "600+0"})
    xroom.join("u1", "Human", "#111")
    xroom.add_bot("easy")
    assert xroom.clock_initial == 600.0
    # Red pawn 6*9+0 = 54 forward to 45
    xroom.handle("u1", "move", {"from": 54, "to": 45})
    xbot = xroom.bot_player()
    assert xbot is not None
    # Black pawn 3*9+0 = 27 forward to 36
    xroom.handle(xbot.uid, "move", {"from": 27, "to": 36})
    assert len(xroom.moves) == 2

    xroom.handle("u1", "undo", {})
    assert len(xroom.moves) == 0
    assert xroom.turn == "X"


def test_geo_compass_streak_and_dynamic_config():
    deg, d_vi = compass_direction(21.0285, 105.8542, 10.7769, 106.7009)
    assert 160.0 <= deg <= 190.0
    assert d_vi == "Nam"

    deg2, d_vi2 = compass_direction(10.0, 100.0, 20.0, 110.0)
    assert d_vi2 == "Đông Bắc"

    room = GeoRoom("STRK", "world")
    room.join("u1", "Explorer", "#0ea5e9")
    room.handle("u1", "config", {"format": "streak", "dynamicSv": False})
    assert room.config["format"] == "streak"
    assert room.config["dynamic_sv"] is False

    room.handle("u1", "start", {})
    assert room.phase == "guessing"
    target = room._current_target()
    assert target is not None
    # Guess exactly on target -> guaranteed regionMatch True -> streak = 1
    room.handle("u1", "guess", {"lat": target["lat"], "lng": target["lng"]})
    assert room.phase == "round_result"
    res0 = room.round_results[0]
    assert res0["regionMatch"] is True
    assert res0["streak"] == 1
    assert "dirVi" in res0

    # Advance to round 2 and miss on opposite side of globe
    room.handle("u1", "next", {"round": 1})
    assert room.phase == "guessing"
    target2 = room._current_target()
    assert target2 is not None
    miss_lat = -target2["lat"] if abs(target2["lat"]) > 15 else 64.0
    miss_lng = ((target2["lng"] + 180 + 180) % 360) - 180
    target2_region = extract_region(target2, "world")
    if infer_region_from_coords(miss_lat, miss_lng, "world").lower() == target2_region.lower():
        miss_lat, miss_lng = -50.0, -70.0
    room.handle("u1", "guess", {"lat": miss_lat, "lng": miss_lng})
    assert room.round_results[0]["regionMatch"] is False
    assert "1" in room.eliminated

    # Next advances to finished because solo player missed
    room.handle("u1", "next", {"round": 2})
    assert room.phase == "finished"
    assert room.best_streaks["u1" if False else "1"] == 1


def test_bluff_taunt_and_sequential_reveal_duration():
    room = BluffRoom("BLF1", "p2")
    room.join("u1", "A", "#111")
    room.join("u2", "B", "#222")
    assert room.status == "playing"

    room.handle("u2", "taunt", {"text": TAUNTS[0]})
    view = room.match_view("u1")
    assert "P2" in view["taunts"]
    assert view["taunts"]["P2"]["text"] == TAUNTS[0]

    with pytest.raises(GameError):
        room.handle("u1", "taunt", {"text": "hack"})

    # Play 3 cards then call liar -> reveal duration should exceed 3 cards * 0.6s
    turn_uid = room.seat(room.turn).uid
    other_uid = "u2" if turn_uid == "u1" else "u1"
    hand_ids = [c.id for c in room.state[room.turn].hand[:3]]
    room.handle(turn_uid, "play", {"cards": hand_ids})
    before_t = time.time()
    room.handle(other_uid, "liar", {})
    assert room.phase == "reveal"
    assert room.deadline - before_t >= 3.4


def test_poker_bot_registered_cash_and_tourney():
    assert bots.supports("poker")
    engine = bots.make_bot("poker", "hard")
    assert isinstance(engine, PokerBot)

    # Preflop and postflop evaluators sanity
    assert preflop_strength([Card(14, "S"), Card(14, "H")]) > 0.90
    assert preflop_strength([Card(7, "S"), Card(2, "D")]) < 0.35
    board = [Card(14, "S"), Card(13, "S"), Card(2, "C"), Card(9, "D"), Card(4, "H")]
    assert postflop_strength([Card(14, "H"), Card(14, "D")], board, "river") > 0.75

    # Solo cash table with bots
    room = PokerRoom("PKBT", "p4")
    room.add_bot("normal")
    assert len(room.bot_players()) == 3
    room.join("u1", "Hero", "#3b82f6")
    assert room.players["u1"].mark == "S1"
    assert room.phase == "starting"

    # Trigger deal immediately
    room.start_at = time.time() - 1.0
    assert room.tick() is True
    assert room.status == "playing"
    assert room.phase == "betting"

    # Let bots play until human turn or hand finishes
    steps = 0
    while room.phase == "betting" and steps < 25:
        b = room.bot_to_act()
        if b is None:
            if room.actor == "S1":
                opts = room._action_options("S1")
                room.handle("u1", "check" if opts["canCheck"] else "call", {})
            else:
                break
        else:
            acts = engine.actions(room, b.mark)
            assert acts
            for act, payload in acts:
                room.handle(b.uid, act, payload)
        steps += 1
        if room.phase == "ritvote":
            b_rit = room.bot_to_act()
            if b_rit:
                for act, payload in engine.actions(room, b_rit.mark):
                    room.handle(b_rit.uid, act, payload)

    # Check auto-rebuy of busted bot during _cleanup_seats in cash table
    bot_s2 = room.seat("S2")
    assert bot_s2 is not None and bot_s2.bot
    room.state["S2"].chips = 0
    room._cleanup_seats()
    assert room.state["S2"].chips == CHIP_START

    # Solo tournament with bots
    troom = PokerRoom("PKTR", "t4")
    troom.add_bot("hard")
    troom.join("u1", "Champ", "#ec4899")
    assert troom.tournament is True
    assert troom.tstage == "running"
    assert troom.host_uid == "u1"
