"""Kiểm thử toàn diện cho trò chơi Bắn Súng Zombie Multiplayer (Đêm Tử Thần)."""
from __future__ import annotations

import math
import time

import bots
from zombie import (
    CLASSES,
    PERKS,
    WEAPONS,
    ZombieRoom,
)


def test_zombie_room_lifecycle_and_classes():
    room = ZombieRoom("ZMB1", "outpost")
    room.join("u1", "Alpha", "#38bdf8")
    room.join("u2", "Bravo", "#4ade80")
    room.join("u3", "Charlie", "#fbbf24")
    room.join("u4", "Delta", "#f87171")

    room.handle("u1", "class", {"cls": "assault"})
    room.handle("u2", "class", {"cls": "medic"})
    room.handle("u3", "class", {"cls": "engineer"})
    room.handle("u4", "class", {"cls": "vanguard"})
    room.handle("u1", "start", {})

    assert room.status == "playing"
    assert room.phase == "wave"
    assert room.wave == 1
    assert len(room.survivors) == 4
    assert room.survivors["1"]["cls"] == "assault"
    assert room.survivors["2"]["cls"] == "medic"
    assert room.survivors["3"]["turrets"] == 1  # Engineer bắt đầu với 1 Sentry Turret
    assert room.survivors["4"]["maxHp"] == CLASSES["vanguard"]["hp"]


def test_zombie_combat_weapons_and_special_infected():
    room = ZombieRoom("ZMB2", "lab")
    room.join("u1", "Shooter", "#38bdf8")
    room.handle("u1", "class", {"cls": "engineer"})
    room.handle("u1", "start", {})

    sv = room.survivors["1"]
    sv["money"] = 5000
    sv["x"], sv["y"] = 700.0, 450.0
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # Mua và kiểm tra tất cả các loại vũ khí (smg, shotgun, rifle, flamer, railgun)
    for wid in ("smg", "shotgun", "rifle", "flamer", "railgun"):
        room.handle("u1", "buy", {"item": wid})
        assert wid in sv["weapons"]

    # Thử bắn Railgun xuyên hàng dọc 2 zombie
    z1 = room._spawn_one_zombie("walker")
    z2 = room._spawn_one_zombie("bloater")
    z1["x"], z1["y"] = 820.0, 450.0
    z2["x"], z2["y"] = 900.0, 450.0
    z2["hp"] = 50.0
    room.handle("u1", "switch", {"weapon": "railgun"})
    room.handle("u1", "shoot", {"aim": 0.0})

    # Bloater bị tiêu diệt phải tạo ra vũng axit độc (hazard)
    assert len(room.hazards) >= 1
    assert room.total_kills >= 2

    # Thử đặt Trụ súng Sentry & bắn hạ zombie mới
    z3 = room._spawn_one_zombie("runner")
    z3["x"], z3["y"] = 790.0, 450.0
    z3["hp"] = 15.0
    room.handle("u1", "turret", {})
    assert len(room.turrets) == 1
    room.tick(dt_override=0.066)
    assert room.total_kills >= 3

    # Thử Lướt né (Dash) miễn nhiễm sát thương
    hp_before = sv["hp"]
    room.handle("u1", "dash", {})
    room._damage_survivor(sv, 50.0, time.time())
    assert sv["hp"] == hp_before

    # Thử ném Lựu đạn nổ diệt mục tiêu
    z4 = room._spawn_one_zombie("brute")
    z4["x"], z4["y"] = 860.0, 450.0
    z4["hp"] = 80.0
    room.handle("u1", "grenade", {"tx": 860.0, "ty": 450.0})
    for _ in range(12):
        room.tick(dt_override=0.06)
    assert z4["hp"] <= 0

    # Kiểm tra Đợt 5 có sinh Boss
    q5 = room._build_wave_queue(5)
    assert "boss" in q5


def test_zombie_downed_revive_and_wave_shop():
    room = ZombieRoom("ZMB3", "outpost")
    room.join("u1", "PlayerA", "#38bdf8")
    room.join("u2", "MedicB", "#4ade80")
    room.handle("u2", "class", {"cls": "medic"})
    room.handle("u1", "start", {})

    sv1 = room.survivors["1"]
    sv2 = room.survivors["2"]
    sv1["x"], sv1["y"] = 500.0, 450.0
    sv2["x"], sv2["y"] = 520.0, 450.0
    room.zombies.clear()
    # Giữ lại 1 zombie trong hàng đợi để đợt chưa kết thúc sớm
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # Gây sát thương chí mạng lên PlayerA -> chuyển sang Downed (không chết ngay vì còn MedicB)
    room._damage_survivor(sv1, 500.0, time.time())
    assert sv1["alive"] is True
    assert sv1["downed"] is True

    # MedicB đứng sát bên trong 1.5s (Medic cứu nhanh ×2.1) -> PlayerA được cứu sống!
    for _ in range(25):
        room.tick(dt_override=0.066)
    assert sv1["downed"] is False
    assert sv1["alive"] is True
    assert sv1["hp"] > 0
    assert sv2["revives"] == 1

    # Dọn sạch đợt -> chuyển sang pha Shop tiếp tế
    room.wave_remaining_to_spawn.clear()
    room.zombies.clear()
    room.tick(dt_override=0.066)
    assert room.phase == "shop"

    # Mua Perk & bấm Sẵn sàng cả 2 người -> nhảy ngay sang Đợt 2
    sv1["money"] = 600
    room.handle("u1", "buy", {"item": "damage"})
    assert sv1["perks"]["damage"] == 1
    room.handle("u1", "ready_shop", {})
    room.handle("u2", "ready_shop", {})
    room.tick(dt_override=0.066)
    assert room.phase == "wave"
    assert room.wave == 2


def test_zombie_ai_survivor_bots_and_solo_mode():
    assert bots.supports("zombie")
    assert "zombie" in bots.bot_channels()

    room = ZombieRoom("ZBOT", "endless")
    room.add_bot("hard")
    room.join("u1", "HumanHero", "#6366f1")
    room.handle("u1", "add_bot", {"mark": "3", "level": "normal"})
    assert len(room.bot_players()) == 2

    room.handle("u1", "start", {})
    sv_human = room.survivors["1"]
    sv_bot = room.survivors["2"]
    sv_human["x"], sv_human["y"] = 500.0, 450.0
    sv_bot["x"], sv_bot["y"] = 540.0, 450.0

    # Gây gục ngã cho người chơi -> Bot tự chạy lại cứu!
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0
    room._damage_survivor(sv_human, 500.0, time.time())
    assert sv_human["downed"] is True

    for _ in range(55):
        room.tick(dt_override=0.066)
    assert sv_human["downed"] is False
    assert sv_human["alive"] is True

    # Sinh 1 zombie ngay trước mặt Bot -> Bot tự ngắm và bắn hạ
    z = room._spawn_one_zombie("walker")
    z["x"], z["y"] = sv_bot["x"] + 130.0, sv_bot["y"]
    z["hp"] = 35.0
    kills_before = room.total_kills
    for _ in range(20):
        room.tick(dt_override=0.066)
    assert room.total_kills > kills_before


def test_zombie_six_players_and_rematch_monotonic_events():
    room = ZombieRoom("Z6P1", "outpost")
    room.join("u1", "Leader", "#38bdf8")
    for idx in range(2, 7):
        room.handle("u1", "add_bot", {"mark": str(idx), "level": "normal"})
    assert len(room._seated_marks()) == 6
    assert len(room.bot_players()) == 5

    room.handle("u1", "start", {})
    assert len(room.survivors) == 6
    v1 = room.match_view("u1")
    assert v1["matchId"] == 1
    assert v1["maxSeats"] == 6

    # Bắn vài phát ở ván 1 để đẩy _event_seq lên cao
    room.handle("u1", "shoot", {"aim": 0.0})
    seq_v1 = room.events[-1]["seq"]
    assert seq_v1 >= 2

    # Kết thúc ván 1 và bấm Chơi ván mới (Rematch)
    room.resign("u1")
    assert room.status == "finished"
    for p in room.bot_players():
        room.vote_rematch(p.uid)
    room.vote_rematch("u1")

    assert room.status == "playing"
    v2 = room.match_view("u1")
    assert v2["matchId"] == 2
    assert len(room.hazards) == 0
    assert len(room.telegraphs) == 0

    # Bắn ở ván 2 -> seq PHẢI lớn hơn seq_v1 để client không bao giờ lọc bỏ tia đạn!
    room.handle("u1", "shoot", {"aim": 0.0})
    shot_evs = [e for e in room.events if e["t"] == "shot"]
    assert shot_evs
    assert shot_evs[-1]["seq"] > seq_v1


def test_zombie_shop_upgrades_launcher_and_items():
    room = ZombieRoom("ZSHP", "lab")
    room.join("u1", "Gunsmith", "#38bdf8")
    room.handle("u1", "start", {})
    sv = room.survivors["1"]
    sv["money"] = 6000
    sv["x"], sv["y"] = 500.0, 450.0
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # Mua Phóng Lựu M79 & nâng cấp lên Mk.II -> Mk.III
    room.handle("u1", "buy", {"item": "launcher"})
    assert "launcher" in sv["weapons"]
    assert sv["weaponLv"]["launcher"] == 1
    room.handle("u1", "buy", {"item": "upgrade:launcher"})
    assert sv["weaponLv"]["launcher"] == 2
    room.handle("u1", "buy", {"item": "upgrade:launcher"})
    assert sv["weaponLv"]["launcher"] == 3

    # Bắn tên lửa M79 tiêu diệt mục tiêu gần đó bằng sát thương nổ lan
    z = room._spawn_one_zombie("walker")
    z["x"], z["y"] = 640.0, 450.0
    room.handle("u1", "shoot", {"aim": 0.0})
    for _ in range(10):
        room.tick(dt_override=0.06)
    assert z["hp"] <= 0

    # Mua Shield & Stim (reset Dash cooldown)
    sv["dashCd"] = time.time() + 3.0
    sv["reloadUntil"] = time.time() + 2.0
    room.handle("u1", "buy", {"item": "shield"})
    assert sv["armor"] > sv["maxArmor"]
    room.handle("u1", "buy", {"item": "stim"})
    assert sv["dashCd"] == 0.0
    assert sv["stimUntil"] > time.time()
    room.handle("u1", "buy", {"item": "ammo"})
    assert sv["reloadUntil"] == 0.0


def test_zombie_miniboss_and_titan_telegraph_skills():
    room = ZombieRoom("ZBOS", "lab")
    room.join("u1", "Hunter", "#38bdf8")
    room.handle("u1", "start", {})

    # Kiểm tra các mốc Mini-Boss (Đợt 3, 6) và Boss lớn (Đợt 5, 10)
    assert "butcher" in room._build_wave_queue(3)
    assert "boss" in room._build_wave_queue(5)
    assert "queen" in room._build_wave_queue(6)
    assert "titan" in room._build_wave_queue(10)

    # Kiểm tra chiêu Pháo Kích Nhiệt Hạch của Titan tạo vòng cảnh báo (telegraph)
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0
    sv = room.survivors["1"]
    sv["x"], sv["y"] = 500.0, 450.0

    titan = room._spawn_one_zombie("titan")
    titan["x"], titan["y"] = 760.0, 450.0
    titan["specialCd"] = 0.0
    room.tick(dt_override=0.066)

    assert len(room.telegraphs) >= 1
    view = room.match_view("u1")
    assert len(view["bosses"]) == 1
    assert view["bosses"][0]["kind"] == "titan"
    assert len(view["telegraphs"]) >= 1
