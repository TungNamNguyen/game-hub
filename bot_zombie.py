"""AI Survivor Bot cho Đêm Tử Thần (Zombie Outbreak).

Chiến đấu theo thời gian thực ở tần số 15 Hz ngay trong bước mô phỏng của ``ZombieRoom``:
  - Chủ động di chuyển chiến thuật: tiến vào tầm bắn, vòng né vật cản khi bị khuất tầm nhìn,
    di chuyển vòng cung (strafing), giữ khoảng cách (kiting), bám đội hình & nhặt vật phẩm rơi.
  - Ưu tiên chạy tới cứu đồng đội đang Gục Ngã (Downed).
  - Ngắm bắn chuẩn theo cấp độ (Dễ / Thường / Khó), tự nạp đạn, đặt trụ Sentry & mìn,
    chủ động ném lựu đạn nổ, lựu đạn băng Cryo và EMP khi gặp cụm quái hoặc Boss.
  - Tự mua súng mạnh hơn, tiếp đạn, lựu đạn & nâng cấp Perk trong pha Cửa Hàng Tiếp Tế.
"""
from __future__ import annotations

import math

from bots import Bot
from zombie import ARENA_H, ARENA_W, PERKS, WEAPONS, _segment_hits_rect

_HEAVY_ZOMBIES = frozenset({"brute", "butcher", "queen", "boss", "titan"})


class ZombieBot(Bot):
    CHANNEL = "zombie"

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        # Hành vi chiến đấu thời gian thực của Bot chạy trực tiếp qua step_bot_survivor() ở 15 Hz.
        return []


def _obstacle_avoidance(x: float, y: float, obs: list[dict], margin: float = 38.0) -> tuple[float, float]:
    """Tạo lực đẩy mượt khỏi tường/vật cản gần để bot không bị kẹt góc."""
    ax, ay = 0.0, 0.0
    for ob in obs:
        cx = max(ob["x"], min(x, ob["x"] + ob["w"]))
        cy = max(ob["y"], min(y, ob["y"] + ob["h"]))
        dx = x - cx
        dy = y - cy
        d = math.hypot(dx, dy)
        if 1e-4 < d < margin:
            w = (margin - d) / margin
            ax += (dx / d) * w * 1.85
            ay += (dy / d) * w * 1.85
    # Đẩy nhẹ khỏi biên sân
    edge = 65.0
    if x < edge:
        ax += (edge - x) / edge * 1.4
    elif x > ARENA_W - edge:
        ax -= (x - (ARENA_W - edge)) / edge * 1.4
    if y < edge:
        ay += (edge - y) / edge * 1.4
    elif y > ARENA_H - edge:
        ay -= (y - (ARENA_H - edge)) / edge * 1.4
    return ax, ay


def _pick_best_pickup(room, sv: dict, max_dist: float = 380.0) -> dict | None:
    """Chọn vật phẩm rơi trên sàn đáng nhặt nhất trong tầm."""
    if not room.pickups:
        return None
    wid = sv["weapon"]
    low_ammo = WEAPONS[wid]["reserve"] != -1 and sv["reserve"].get(wid, 0) < WEAPONS[wid]["mag"] * 3
    low_hp = sv["hp"] < sv["maxHp"] * 0.82
    best = None
    best_score = 1e9
    for pk in room.pickups:
        kind = pk.get("kind", "")
        if kind == "med" and not low_hp:
            continue
        if kind == "ammo" and not low_ammo:
            continue
        if kind == "nuke" and len(room.zombies) < 2 and room.phase == "wave":
            continue
        d = math.hypot(pk["x"] - sv["x"], pk["y"] - sv["y"])
        if d > max_dist:
            continue
        prio = {
            "nuke": 0.40,
            "double_dmg": 0.50,
            "inf_ammo": 0.55,
            "med": 0.60 if sv["hp"] < sv["maxHp"] * 0.55 else 0.80,
            "ammo": 0.72,
            "cash": 0.90,
        }.get(kind, 1.0)
        sc = d * prio
        if sc < best_score:
            best_score = sc
            best = pk
    return best


def _nearest_human_mate(room, sv: dict) -> dict | None:
    """Tìm đồng đội người chơi thật còn sống gần nhất để bám đội hình co-op."""
    best = None
    best_d = 1e9
    for om, o in room.survivors.items():
        if om == sv["mark"] or not o["alive"] or o["downed"]:
            continue
        seat_p = room.seat(om)
        if seat_p is None or seat_p.bot:
            continue
        d = math.hypot(o["x"] - sv["x"], o["y"] - sv["y"])
        if d < best_d:
            best_d = d
            best = o
    return best


def step_bot_survivor(room, player, sv: dict, dt: float, now: float) -> None:
    """Cập nhật AI chiến đấu cho một Bot đồng đội ở tần số 15 Hz."""
    if not sv["alive"] or sv["downed"]:
        sv["vx"] = sv["vy"] = 0.0
        sv["firing"] = False
        return

    level = player.level if player.level in ("easy", "normal", "hard") else "normal"
    obs = room._obstacles()
    try:
        slot_seed = int(sv["mark"])
    except (TypeError, ValueError):
        slot_seed = 1

    # 1. Pha tiếp tế: tự mua vũ khí / nâng cấp Mk.II-III / đạn / lựu đạn / máu / perk & di chuyển nhặt đồ
    if room.phase == "shop":
        sv["firing"] = False
        if sv["hp"] < sv["maxHp"] * 0.72 and sv["money"] >= 120:
            try:
                room._buy_item(sv, "medkit")
            except Exception:
                pass
        if sv["armor"] < sv["maxArmor"] * 0.45 and sv["money"] >= 140 and level != "easy":
            try:
                room._buy_item(sv, "shield")
            except Exception:
                pass
        buy_order = (
            ("rifle", "tesla", "launcher", "railgun", "flamer", "shotgun", "smg")
            if level == "hard"
            else ("rifle", "tesla", "shotgun", "launcher", "smg")
        )
        for wid in buy_order:
            if wid not in sv["weapons"] and sv["money"] >= WEAPONS[wid]["cost"]:
                try:
                    room._buy_item(sv, wid)
                    break
                except Exception:
                    pass
        # Tiếp đạn nếu vũ khí chính sắp hết đạn dự trữ
        cur_w = sv["weapon"]
        if WEAPONS[cur_w]["reserve"] != -1 and sv["reserve"].get(cur_w, 0) < WEAPONS[cur_w]["mag"] * 2 and sv["money"] >= 100:
            try:
                room._buy_item(sv, "ammo")
            except Exception:
                pass
        # Mua thêm lựu đạn nổ, băng & EMP để dùng chủ động trong đợt kế tiếp
        if sv["grenades"] < 2 and sv["money"] >= (260 if level == "easy" else 140):
            try:
                room._buy_item(sv, "grenade")
            except Exception:
                pass
        if sv.get("cryos", 0) == 0 and sv["money"] >= 150 and level != "easy":
            try:
                room._buy_item(sv, "cryo")
            except Exception:
                pass
        if sv.get("emps", 0) == 0 and sv["money"] >= 160 and level != "easy":
            try:
                room._buy_item(sv, "emp")
            except Exception:
                pass
        if sv.get("mines", 0) == 0 and sv["money"] >= 170 and level == "hard":
            try:
                room._buy_item(sv, "mine")
            except Exception:
                pass
        if sv.get("mines", 0) > 0:
            try:
                room._deploy_mine(sv)
            except Exception:
                pass
        # Nâng cấp vũ khí chính lên Mk.II / Mk.III nếu đủ tiền
        if level != "easy":
            cur_w = sv["weapon"]
            cur_lv = room._weapon_lv(sv, cur_w)
            if cur_w != "pistol" and cur_lv < 3 and sv["money"] >= room._weapon_upgrade_cost(cur_w, cur_lv):
                try:
                    room._buy_item(sv, f"upgrade:{cur_w}")
                except Exception:
                    pass
        for perk in ("damage", "armor", "reload", "vamp"):
            cur = sv["perks"].get(perk, 0)
            cost = PERKS[perk]["cost"] + cur * 110
            if cur < PERKS[perk]["max"] and sv["money"] >= cost:
                try:
                    room._buy_item(sv, perk)
                    break
                except Exception:
                    pass
        if sv["turrets"] == 0 and sv["money"] >= 280 and level != "easy":
            try:
                room._buy_item(sv, "turret")
            except Exception:
                pass

        # Trong pha chờ, chủ động chạy đi nhặt đồ rơi trên sàn hoặc tập hợp đội hình quanh đồng đội
        sx, sy = 0.0, 0.0
        pk = _pick_best_pickup(room, sv, max_dist=650.0)
        if pk is not None:
            dx, dy = pk["x"] - sv["x"], pk["y"] - sv["y"]
            d = math.hypot(dx, dy) or 1.0
            sx, sy = dx / d, dy / d
        else:
            anchor = _nearest_human_mate(room, sv)
            if anchor is not None:
                ang = (slot_seed * 1.4) + 0.6
                tx = anchor["x"] + math.cos(ang) * 120.0
                ty = anchor["y"] + math.sin(ang) * 120.0
                dx, dy = tx - sv["x"], ty - sv["y"]
                d = math.hypot(dx, dy)
                if d > 55.0:
                    sx, sy = (dx / d) * 0.75, (dy / d) * 0.75
        if sx != 0.0 or sy != 0.0:
            ox, oy = _obstacle_avoidance(sv["x"], sv["y"], obs, margin=34.0)
            sx += ox * 0.6
            sy += oy * 0.6
            sm = math.hypot(sx, sy)
            if sm > 0.12:
                sv["vx"], sv["vy"] = sx / sm, sy / sm
                sv["aim"] = math.atan2(sv["vy"], sv["vx"])
            else:
                sv["vx"] = sv["vy"] = 0.0
        else:
            sv["vx"] = sv["vy"] = 0.0
        return

    # 2. Đặt trụ súng Sentry nếu đang mang theo và có zombie
    if sv["turrets"] > 0 and room.zombies:
        try:
            room._deploy_turret(sv)
        except Exception:
            pass

    # 3. Tự chọn vũ khí tốt nhất còn đạn
    best_w = sv["weapon"]
    cur_empty = (
        sv["mag"].get(best_w, 0) <= 0
        and WEAPONS[best_w]["reserve"] != -1
        and sv["reserve"].get(best_w, 0) <= 0
    )
    if cur_empty or (best_w == "pistol" and len(sv["weapons"]) > 1):
        for wid in reversed(sv["weapons"]):
            if WEAPONS[wid]["reserve"] == -1 or sv["reserve"].get(wid, 0) > 0 or sv["mag"].get(wid, 0) > 0:
                best_w = wid
                sv["weapon"] = wid
                break
    w_range = WEAPONS[best_w]["range"]

    # 4. Chọn mục tiêu chiến đấu trước để hỗ trợ di chuyển tìm góc bắn & strafe
    def _has_los(z: dict) -> bool:
        return not any(_segment_hits_rect(sv["x"], sv["y"], z["x"], z["y"], ob) is not None for ob in obs)

    def threat_score(z: dict) -> float:
        d = math.hypot(z["x"] - sv["x"], z["y"] - sv["y"])
        prio = 0.70 if z["kind"] in ("runner", "spitter", "butcher", "queen", "boss", "titan") else 1.0
        return d * prio

    target = None
    target_visible = False
    td = 1e9
    if room.zombies:
        visible = [z for z in room.zombies if _has_los(z)]
        target = min(visible or room.zombies, key=threat_score)
        target_visible = bool(visible)
        td = math.hypot(target["x"] - sv["x"], target["y"] - sv["y"])

    # 5. Tính toán di chuyển: cứu đồng đội, né nguy hiểm, vòng tường, strafe & nhặt đồ
    downed_mates = [
        o for om, o in room.survivors.items()
        if om != sv["mark"] and o["alive"] and o["downed"]
    ]
    move_x, move_y = 0.0, 0.0

    if downed_mates:
        mate = min(downed_mates, key=lambda o: math.hypot(o["x"] - sv["x"], o["y"] - sv["y"]))
        dx = mate["x"] - sv["x"]
        dy = mate["y"] - sv["y"]
        d = math.hypot(dx, dy)
        if d > 36.0:
            ox, oy = _obstacle_avoidance(sv["x"], sv["y"], obs, margin=32.0)
            mx, my = (dx / d) + ox * 0.45, (dy / d) + oy * 0.45
            mm = math.hypot(mx, my) or 1.0
            move_x, move_y = mx / mm, my / mm
    else:
        steer_x, steer_y = 0.0, 0.0
        nearest_z_dist = 1e9
        safe_r = {"easy": 165.0, "normal": 195.0, "hard": 235.0}[level]
        for z in room.zombies:
            dx = sv["x"] - z["x"]
            dy = sv["y"] - z["y"]
            d = math.hypot(dx, dy) or 1.0
            if d < nearest_z_dist:
                nearest_z_dist = d
            if d < safe_r:
                weight = (safe_r - d) / safe_r
                steer_x += (dx / d) * weight * 1.9
                steer_y += (dy / d) * weight * 1.9

        for hz in room.hazards:
            if hz.get("kind", "acid") != "acid":
                continue
            dx = sv["x"] - hz["x"]
            dy = sv["y"] - hz["y"]
            d = math.hypot(dx, dy) or 1.0
            if d < hz["radius"] + 58.0:
                steer_x += (dx / d) * 2.6
                steer_y += (dy / d) * 2.6

        # Ưu tiên né khẩn cấp vòng cảnh báo chiêu của Boss / Mini-Boss (Telegraphs)
        in_telegraph = False
        for tg in getattr(room, "telegraphs", ()):
            dx = sv["x"] - tg["x"]
            dy = sv["y"] - tg["y"]
            d = math.hypot(dx, dy) or 1.0
            if d < tg["radius"] + 42.0:
                in_telegraph = True
                steer_x += (dx / d) * 4.4
                steer_y += (dy / d) * 4.4

        # Di chuyển chiến thuật theo mục tiêu: tìm góc bắn nếu bị tường che, tiến vào tầm bắn, hoặc vòng strafe
        strafe_sign = 1.0 if ((int(now * 0.42) + slot_seed) % 2 == 0) else -1.0
        if target is not None and not in_telegraph:
            tx_dx = target["x"] - sv["x"]
            tx_dy = target["y"] - sv["y"]
            t_len = math.hypot(tx_dx, tx_dy) or 1.0
            ux, uy = tx_dx / t_len, tx_dy / t_len
            px, py = -uy * strafe_sign, ux * strafe_sign  # vector vuông góc để strafe / vòng tường

            if not target_visible:
                # Bị vật cản chắn tầm nhìn -> chủ động tiến vòng sang ngang để tìm góc bắn
                steer_x += ux * 0.85 + px * 0.95
                steer_y += uy * 0.85 + py * 0.95
            else:
                engage_r = min(w_range * 0.82, 430.0)
                if td > engage_r:
                    # Tiến lại gần để lọt vào tầm bắn hiệu quả
                    steer_x += ux * 1.05 + px * 0.30
                    steer_y += uy * 1.05 + py * 0.30
                elif nearest_z_dist > safe_r * 0.72:
                    # Giữ nhịp di chuyển vòng cung (strafing) để tránh đứng trơ một chỗ
                    strafe_w = {"easy": 0.45, "normal": 0.72, "hard": 0.85}[level]
                    steer_x += px * strafe_w
                    steer_y += py * strafe_w

        # Chủ động nhặt vật phẩm rơi (máu, đạn, tiền, Power-Up) nếu không bị áp sát quá nguy hiểm
        if nearest_z_dist > 85.0 and not in_telegraph:
            pk = _pick_best_pickup(room, sv, max_dist=380.0)
            if pk is not None:
                pdx, pdy = pk["x"] - sv["x"], pk["y"] - sv["y"]
                pd = math.hypot(pdx, pdy) or 1.0
                steer_x += (pdx / pd) * 1.35
                steer_y += (pdy / pd) * 1.35

        # Bám nhẹ đội hình người chơi thật nếu bị tách quá xa (> 430px)
        anchor = _nearest_human_mate(room, sv)
        if anchor is not None and nearest_z_dist > 110.0 and not in_telegraph:
            adx, ady = anchor["x"] - sv["x"], anchor["y"] - sv["y"]
            ad = math.hypot(adx, ady) or 1.0
            if ad > 430.0:
                steer_x += (adx / ad) * 0.85
                steer_y += (ady / ad) * 0.85

        # Tách nhẹ khỏi đồng đội đứng quá sát để không chồng lên nhau
        for om, o in room.survivors.items():
            if om == sv["mark"] or not o["alive"] or o["downed"]:
                continue
            sdx, sdy = sv["x"] - o["x"], sv["y"] - o["y"]
            sd = math.hypot(sdx, sdy)
            if 1e-4 < sd < 64.0:
                w = (64.0 - sd) / 64.0
                steer_x += (sdx / sd) * w * 0.9
                steer_y += (sdy / sd) * w * 0.9

        # Kéo nhẹ về giữa bản đồ để tránh bị ép vào góc chết
        cx_dx = ARENA_W * 0.5 - sv["x"]
        cy_dy = ARENA_H * 0.5 - sv["y"]
        cd = math.hypot(cx_dx, cy_dy) or 1.0
        if cd > 460.0:
            steer_x += (cx_dx / cd) * 0.60
            steer_y += (cy_dy / cd) * 0.60

        # Né vật cản & biên bản đồ mượt mà
        ox, oy = _obstacle_avoidance(sv["x"], sv["y"], obs, margin=38.0)
        steer_x += ox
        steer_y += oy

        rm = math.hypot(steer_x, steer_y)
        if rm > 0.14:
            move_x, move_y = steer_x / rm, steer_y / rm
            if in_telegraph and sv["dashCd"] <= now and level != "easy":
                sv["vx"], sv["vy"] = move_x, move_y
                room._do_dash(sv, now)

    sv["vx"] = move_x
    sv["vy"] = move_y

    # 6. Ngắm bắn, ném lựu đạn (Nổ / Băng / EMP), đặt mìn & khai hỏa
    if target is None:
        sv["firing"] = False
        if move_x != 0.0 or move_y != 0.0:
            sv["aim"] = math.atan2(move_y, move_x)
        return

    aim_err = {"easy": 0.16, "normal": 0.08, "hard": 0.025}[level]
    sv["aim"] = math.atan2(target["y"] - sv["y"], target["x"] - sv["x"]) + room.rng.uniform(-aim_err, aim_err)

    # Nếu zombie quá sát và sẵn sàng Dash -> lướt né
    if td < 72.0 and sv["dashCd"] <= now and level != "easy":
        room._do_dash(sv, now)

    # Đặt mìn trên đường rút lui nếu mang theo và zombie áp sát
    if sv.get("mines", 0) > 0 and td < 240.0:
        try:
            room._deploy_mine(sv)
        except Exception:
            pass

    # Chủ động ném bom (EMP / Cryo / Lựu đạn nổ) có giãn cách để tránh ném chồng cùng lúc
    if now >= sv.get("_botThrowCd", 0.0) and 95.0 < td < 370.0:
        cluster = sum(
            1 for z in room.zombies
            if math.hypot(z["x"] - target["x"], z["y"] - target["y"]) <= 125.0
        )
        is_heavy = target["kind"] in _HEAVY_ZOMBIES
        threw = False

        # Ưu tiên EMP khi gặp Boss/Mini-Boss hoặc cụm đông đang áp sát
        if (
            not threw
            and sv.get("emps", 0) > 0
            and level != "easy"
            and ((is_heavy and target.get("stunTimer", 0.0) <= 0.15) or cluster >= 3)
        ):
            room._throw_grenade(sv, target["x"], target["y"], kind="emp")
            sv["_botThrowCd"] = now + 2.8
            threw = True

        # Ném Lựu Đạn Băng (Cryo) làm chậm cụm quái nhanh hoặc Boss/Brute
        if (
            not threw
            and sv.get("cryos", 0) > 0
            and level != "easy"
            and target.get("slowTimer", 0.0) <= 0.5
            and (cluster >= 2 or is_heavy or target["kind"] == "runner")
        ):
            room._throw_grenade(sv, target["x"], target["y"], kind="cryo")
            sv["_botThrowCd"] = now + 2.6
            threw = True

        # Ném Lựu Đạn Nổ khi có cụm zombie (>= 2 với Normal/Hard, >= 3 với Easy) hoặc mục tiêu lớn
        min_cluster = 3 if level == "easy" else 2
        if (
            not threw
            and sv["grenades"] > 0
            and (cluster >= min_cluster or (is_heavy and level != "easy"))
        ):
            room._throw_grenade(sv, target["x"], target["y"], kind="grenade")
            sv["_botThrowCd"] = now + (3.8 if level == "easy" else 2.5)

    fire_chance = {"easy": 0.55, "normal": 0.82, "hard": 1.0}[level]
    # Z12: Chỉ khai hỏa khi có tầm nhìn trực tiếp (hoặc dùng súng phóng lựu nổ lan) để tránh bắn phí đạn vào tường
    can_shoot_target = target_visible or WEAPONS[best_w].get("splash", 0.0) > 0
    sv["firing"] = can_shoot_target and td <= w_range * 1.05 and room.rng.random() <= fire_chance
