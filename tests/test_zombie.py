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

    # Chỉ cho phép mua đồ khi đang ở pha shop (giữa các đợt)
    room.phase = "shop"
    room.shop_deadline = time.time() + 16.0
    for wid in ("smg", "shotgun", "rifle", "flamer", "tesla", "railgun"):
        room.handle("u1", "buy", {"item": wid})
        assert wid in sv["weapons"]
    room.phase = "wave"

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
    from games import GameError
    room = ZombieRoom("ZSHP", "lab")
    room.join("u1", "Gunsmith", "#38bdf8")
    room.handle("u1", "start", {})
    sv = room.survivors["1"]
    sv["money"] = 6000
    sv["x"], sv["y"] = 500.0, 450.0
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # Không được phép mua đồ khi đang đánh wave!
    try:
        room.handle("u1", "buy", {"item": "launcher"})
        assert False, "Expected GameError when buying during wave"
    except GameError:
        pass

    # Chuyển sang pha chờ (shop): vừa mua đồ vừa DI CHUYỂN tự do được!
    room.phase = "shop"
    room.shop_deadline = time.time() + 16.0
    old_x = sv["x"]
    room.handle("u1", "input", {"vx": 1.0, "vy": 0.0, "aim": 0.0, "firing": False})
    room.tick(dt_override=0.066)
    assert sv["x"] > old_x, "Survivor must be able to move during shop intermission!"

    # Mua Phóng Lựu M79 & nâng cấp lên Mk.II -> Mk.III
    room.handle("u1", "buy", {"item": "launcher"})
    assert "launcher" in sv["weapons"]
    assert sv["weaponLv"]["launcher"] == 1
    room.handle("u1", "buy", {"item": "upgrade:launcher"})
    assert sv["weaponLv"]["launcher"] == 2
    room.handle("u1", "buy", {"item": "upgrade:launcher"})
    assert sv["weaponLv"]["launcher"] == 3

    # Mua Shield (chỉ hồi đầy đúng maxArmor, KHÔNG còn Over-Shield!) & Stim
    sv["armor"] = 10.0
    sv["dashCd"] = time.time() + 3.0
    sv["reloadUntil"] = time.time() + 2.0
    room.handle("u1", "buy", {"item": "shield"})
    assert sv["armor"] == sv["maxArmor"]
    room.handle("u1", "buy", {"item": "stim"})
    assert sv["dashCd"] == 0.0
    assert sv["stimUntil"] > time.time()
    room.handle("u1", "buy", {"item": "ammo"})
    assert sv["reloadUntil"] == 0.0

    # Sang lại wave để bắn tên lửa M79 tiêu diệt mục tiêu gần đó bằng sát thương nổ lan
    room.phase = "wave"
    z = room._spawn_one_zombie("walker")
    z["x"], z["y"] = sv["x"] + 130.0, sv["y"]
    room.handle("u1", "shoot", {"aim": 0.0})
    for _ in range(10):
        room.tick(dt_override=0.06)
    assert z["hp"] <= 0


def test_zombie_cc_gadgets_turret_hp_barrels_and_maps():
    # Kiểm tra cả 6 bản đồ mới đều khởi tạo sạch sẽ
    for map_id in ("outpost", "lab", "metro", "dock", "reactor", "endless"):
        r = ZombieRoom("ZMAP", map_id)
        r.join("u1", "Scout", "#38bdf8")
        r.handle("u1", "start", {})
        assert len(r._obstacles()) >= 5
        assert len(r.barrels) == 4

    room = ZombieRoom("ZCC1", "metro")
    room.join("u1", "Tactician", "#38bdf8")
    room.handle("u1", "class", {"cls": "engineer"})
    room.handle("u1", "start", {})
    sv = room.survivors["1"]
    sv["money"] = 4000
    sv["x"], sv["y"] = 500.0, 340.0
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # Mua Tesla, Cryo, EMP, Mine trong pha shop
    room.phase = "shop"
    room.shop_deadline = time.time() + 16.0
    for it in ("tesla", "cryo", "emp", "mine"):
        room.handle("u1", "buy", {"item": it})
    room.phase = "wave"

    # 1. Bắn Tesla giật chuyền qua 2 zombie và làm chậm/choáng
    z1 = room._spawn_one_zombie("brute")
    z2 = room._spawn_one_zombie("brute")
    z1["x"], z1["y"] = 640.0, 340.0
    z2["x"], z2["y"] = 720.0, 340.0
    room.handle("u1", "switch", {"weapon": "tesla"})
    room.handle("u1", "shoot", {"aim": 0.0})
    assert z1["slowTimer"] > 0 and z2["slowTimer"] > 0
    assert any(e["t"] == "chain" for e in room.events)

    # 2. Ném Lựu Đạn EMP -> làm choáng Stun 2.8s
    room.handle("u1", "emp", {"tx": 680.0, "ty": 340.0})
    for _ in range(12):
        room.tick(dt_override=0.06)
    assert z1["stunTimer"] > 1.5

    # 3. Ném Lựu Đạn Băng Cryo -> tạo vùng Cryo Hazard trên sàn
    room.handle("u1", "cryo", {"tx": 680.0, "ty": 340.0})
    for _ in range(12):
        room.tick(dt_override=0.06)
    assert any(h.get("kind") == "cryo" for h in room.hazards)

    # 4. Trụ súng Sentry có HP & bị Zombie đập mất máu
    room.handle("u1", "turret", {})
    tr = room.turrets[0]
    assert tr["hp"] > 0 and tr["hp"] == tr["maxHp"]
    z3 = room._spawn_one_zombie("walker")
    z3["x"], z3["y"] = tr["x"] + 15.0, tr["y"]
    z3["stunTimer"] = 0.0
    tr["fireCd"] = time.time() + 10.0  # để zombie kịp đánh trụ
    room.tick(dt_override=0.066)
    assert tr["hp"] < tr["maxHp"]

    # 5. Khi Zombie đánh trúng người chơi -> phát sự kiện 'hurt' để hiện vết cào & viền máu
    room._damage_survivor(sv, 20.0, time.time(), sx=520.0, sy=450.0, kind="melee")
    assert any(e["t"] == "hurt" and e["mark"] == "1" for e in room.events)

    # 6. Đặt Mìn Từ Trường & kích nổ khi Zombie bước vào
    room.handle("u1", "mine", {})
    assert len(room.mines) == 1
    z4 = room._spawn_one_zombie("walker")
    z4["x"], z4["y"] = room.mines[0]["x"] + 10.0, room.mines[0]["y"]
    room.tick(dt_override=0.066)
    assert len(room.mines) == 0
    assert z4["hp"] <= 0

    # 7. Bắn nổ Thùng Phuy Nhiên Liệu -> phải phát sự kiện 'barrel_hit', 'boom' (kind='barrel'), gây AoE và kích nổ dây chuyền!
    assert len(room.barrels) >= 2
    b1 = room.barrels[0]
    b2 = room.barrels[1]
    b1["x"], b1["y"] = sv["x"] + 120.0, sv["y"]
    b2["x"], b2["y"] = b1["x"] + 90.0, b1["y"] + 40.0
    z5 = room._spawn_one_zombie("walker")
    z5["x"], z5["y"] = b1["x"] + 50.0, b1["y"] - 30.0
    room.events.clear()
    room.handle("u1", "switch", {"weapon": "pistol"})
    sv["fireCd"] = 0.0
    room.handle("u1", "shoot", {"aim": 0.0})
    assert b1["hp"] > 0
    assert any(e["t"] == "barrel_hit" for e in room.events), "Non-lethal hit on barrel must emit barrel_hit"
    sv["fireCd"] = 0.0
    room.handle("u1", "shoot", {"aim": 0.0})
    assert b1["hp"] <= 0 and b1.get("detonated") is True
    assert b2["hp"] <= 0 and b2.get("detonated") is True, "Adjacent barrel must chain-detonate"
    barrel_booms = [e for e in room.events if e["t"] == "boom" and e.get("kind") == "barrel"]
    assert len(barrel_booms) >= 2, "Shooting barrel must emit boom(kind='barrel') for VFX!"
    assert z5["hp"] <= 0, "Barrel explosion must damage/kill nearby zombies"


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


def test_zombie_bot_proactive_movement_and_gadgets():
    room = ZombieRoom("ZAI1", "outpost")
    room.join("u1", "Leader", "#38bdf8")
    room.handle("u1", "add_bot", {"mark": "2", "level": "normal"})
    room.handle("u1", "start", {})

    sv_h = room.survivors["1"]
    sv_b = room.survivors["2"]
    sv_h["x"], sv_h["y"] = 500.0, 450.0
    sv_b["x"], sv_b["y"] = 780.0, 450.0
    room.zombies.clear()
    room.wave_remaining_to_spawn = ["walker"]
    room.spawn_timer = 99.0

    # 1. Zombie ở tầm trung (~320px): bot phải chủ động di chuyển (strafe / điều chỉnh vị trí), không đứng yên
    z1 = room._spawn_one_zombie("walker")
    z1["x"], z1["y"] = 1100.0, 450.0
    z1["hp"] = 500.0
    start_x, start_y = sv_b["x"], sv_b["y"]
    for _ in range(8):
        room.tick(dt_override=0.066)
    moved_dist = math.hypot(sv_b["x"] - start_x, sv_b["y"] - start_y)
    assert moved_dist > 25.0, f"Bot should actively reposition/strafe, moved only {moved_dist:.1f}px"

    # 2. Cụm 2 zombie trong tầm ném: bot chủ động ném lựu đạn (EMP / Cryo / Grenade)
    sv_b["x"], sv_b["y"] = 760.0, 450.0
    sv_b["_botThrowCd"] = 0.0
    sv_b["emps"] = 0
    sv_b["cryos"] = 0
    sv_b["grenades"] = 2
    room.zombies.clear()
    room.projectiles.clear()
    za = room._spawn_one_zombie("walker")
    zb = room._spawn_one_zombie("walker")
    za["x"], za["y"] = 960.0, 450.0
    zb["x"], zb["y"] = 985.0, 465.0
    za["hp"] = zb["hp"] = 400.0
    room.tick(dt_override=0.066)
    assert sv_b["grenades"] == 1
    assert any(p["kind"] == "grenade" and p["owner"] == "2" for p in room.projectiles)

    # 3. Gặp Boss + có EMP: bot chủ động ném EMP để làm choáng
    sv_b["_botThrowCd"] = 0.0
    sv_b["emps"] = 1
    room.zombies.clear()
    room.projectiles.clear()
    boss = room._spawn_one_zombie("boss")
    boss["x"], boss["y"] = 970.0, 450.0
    room.tick(dt_override=0.066)
    assert sv_b["emps"] == 0
    assert any(p["kind"] == "emp" and p["owner"] == "2" for p in room.projectiles)

    # 4. Trong pha shop: bot tự mua bổ sung lựu đạn & di chuyển đi nhặt tiền rơi
    room.phase = "shop"
    room.shop_deadline = time.time() + 16.0
    sv_b["grenades"] = 0
    sv_b["cryos"] = 0
    sv_b["emps"] = 0
    sv_b["money"] = 600
    sv_b["x"], sv_b["y"] = 700.0, 450.0
    room.pickups = [{"id": 999, "kind": "cash", "x": 810.0, "y": 450.0, "ttl": 15.0}]
    for _ in range(12):
        room.tick(dt_override=0.066)
    assert sv_b["grenades"] >= 2
    assert sv_b["x"] > 720.0


def test_zombie_enemy_scaling_by_squad_size_and_smart_ai():
    # 1. So sánh 1 chiến binh vs 6 chiến binh: số lượng, HP quái thường/Boss, sát thương & tốc độ phải scale rõ rệt
    r1 = ZombieRoom("ZSC1", "outpost")
    r1.join("u1", "Solo", "#38bdf8")
    r1.handle("u1", "start", {})

    r6 = ZombieRoom("ZSC6", "outpost")
    r6.join("u1", "Lead", "#38bdf8")
    for idx in range(2, 7):
        r6.handle("u1", "add_bot", {"mark": str(idx), "level": "normal"})
    r6.handle("u1", "start", {})

    q1_w5 = r1._build_wave_queue(5)
    q6_w5 = r6._build_wave_queue(5)
    assert len(q6_w5) >= int(len(q1_w5) * 2.2), f"6p wave should scale up strongly: {len(q1_w5)} vs {len(q6_w5)}"
    assert "boss" in q6_w5 and "butcher" in q6_w5  # Phòng 6 người ở đợt Boss có thêm Mini-Boss hộ tống

    z1_w = r1._spawn_one_zombie("walker")
    z6_w = r6._spawn_one_zombie("walker")
    assert z6_w["maxHp"] > z1_w["maxHp"] * 1.65
    assert z6_w["dmg"] > z1_w["dmg"] * 1.30
    assert z6_w["speed"] > z1_w["speed"] * 1.15

    z1_b = r1._spawn_one_zombie("boss")
    z6_b = r6._spawn_one_zombie("boss")
    assert z6_b["maxHp"] > z1_b["maxHp"] * 2.4

    # 2. AI Zombie chọn mục tiêu thông minh: ưu tiên kết liễu người thấp máu ở cùng khoảng cách
    r6.zombies.clear()
    r6.wave_remaining_to_spawn = ["walker"]
    r6.spawn_timer = 99.0
    sv_healthy = r6.survivors["1"]
    sv_low = r6.survivors["2"]
    for m, s in r6.survivors.items():
        if m not in ("1", "2"):
            s["x"], s["y"] = 1450.0, 820.0
    sv_healthy["x"], sv_healthy["y"] = 600.0, 450.0
    sv_healthy["hp"] = sv_healthy["maxHp"]
    sv_low["x"], sv_low["y"] = 800.0, 450.0
    sv_low["hp"] = sv_low["maxHp"] * 0.25
    runner = r6._spawn_one_zombie("runner")
    runner["x"], runner["y"] = 700.0, 450.0
    chosen = r6._choose_zombie_target(runner, [sv_healthy, sv_low], [])
    assert chosen["mark"] == "2"

    # 3. Spitter bắn đón đầu theo hướng di chuyển (lead shot)
    sv_low["x"], sv_low["y"] = 700.0, 450.0
    sv_low["moveVx"], sv_low["moveVy"] = 0.0, 220.0
    lx, ly = ZombieRoom._predict_target_pos(450.0, 450.0, sv_low, 325.0, lead_factor=0.7)
    assert ly > sv_low["y"] + 40.0

    # 4. Titan ở phòng 6 người tung nhiều vòng pháo kích hơn phòng 1 người (>= 5 vòng)
    r6.zombies.clear()
    r6.telegraphs.clear()
    for idx, s in enumerate(r6.survivors.values()):
        s["alive"] = True
        s["downed"] = False
        s["x"], s["y"] = 350.0 + idx * 140.0, 450.0
    titan6 = r6._spawn_one_zombie("titan")
    titan6["x"], titan6["y"] = 750.0, 220.0
    titan6["specialCd"] = 0.0
    r6.tick(dt_override=0.066)
    assert len(r6.telegraphs) >= 5


