"""AI Survivor Bot cho Đêm Tử Thần (Zombie Outbreak).

Chiến đấu theo thời gian thực ở tần số 15 Hz ngay trong bước mô phỏng của ``ZombieRoom``:
  - Tự di chuyển giữ khoảng cách (kiting), tránh vũng axit và vật cản.
  - Ưu tiên chạy tới cứu đồng đội đang Gục Ngã (Downed).
  - Ngắm bắn chuẩn theo cấp độ (Dễ / Thường / Khó), tự nạp đạn, đặt trụ Sentry, ném lựu đạn khi bị vây.
  - Tự mua súng mạnh hơn & nâng cấp Perk trong pha Cửa Hàng Tiếp Tế.
"""
from __future__ import annotations

import math

from bots import Bot
from zombie import ARENA_H, ARENA_W, PERKS, WEAPONS, _segment_hits_rect


class ZombieBot(Bot):
    CHANNEL = "zombie"

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        # Hành vi chiến đấu thời gian thực của Bot chạy trực tiếp qua step_bot_survivor() ở 15 Hz.
        return []


def step_bot_survivor(room, player, sv: dict, dt: float, now: float) -> None:
    """Cập nhật AI chiến đấu cho một Bot đồng đội ở tần số 15 Hz."""
    if not sv["alive"] or sv["downed"]:
        sv["vx"] = sv["vy"] = 0.0
        sv["firing"] = False
        return

    level = player.level if player.level in ("easy", "normal", "hard") else "normal"

    # 1. Pha tiếp tế: tự mua vũ khí / nâng cấp Mk.II-III / máu / perk theo cấp độ
    if room.phase == "shop":
        sv["vx"] = sv["vy"] = 0.0
        sv["firing"] = False
        if sv["hp"] < sv["maxHp"] * 0.7 and sv["money"] >= 120:
            try:
                room._buy_item(sv, "medkit")
            except Exception:
                pass
        if sv["armor"] < sv["maxArmor"] * 0.45 and sv["money"] >= 140 and level != "easy":
            try:
                room._buy_item(sv, "shield")
            except Exception:
                pass
        buy_order = ("rifle", "tesla", "launcher", "railgun", "flamer", "shotgun", "smg") if level == "hard" else ("rifle", "tesla", "shotgun", "launcher", "smg")
        for wid in buy_order:
            if wid not in sv["weapons"] and sv["money"] >= WEAPONS[wid]["cost"]:
                try:
                    room._buy_item(sv, wid)
                    break
                except Exception:
                    pass
        if sv.get("emps", 0) == 0 and sv["money"] >= 160 and level != "easy":
            try:
                room._buy_item(sv, "emp")
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
        return

    # 2. Đặt trụ súng Sentry nếu đang mang theo và có zombie
    if sv["turrets"] > 0 and room.zombies:
        try:
            room._deploy_turret(sv)
        except Exception:
            pass

    # 3. Ưu tiên cứu đồng đội đang gục ngã!
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
            move_x, move_y = dx / d, dy / d
    else:
        # Di chuyển giữ khoảng cách (kiting) khỏi zombie gần nhất & né vũng axit
        repel_x, repel_y = 0.0, 0.0
        for z in room.zombies:
            dx = sv["x"] - z["x"]
            dy = sv["y"] - z["y"]
            d = math.hypot(dx, dy) or 1.0
            safe_r = 210.0 if level == "hard" else 160.0
            if d < safe_r:
                weight = (safe_r - d) / safe_r
                repel_x += (dx / d) * weight * 1.6
                repel_y += (dy / d) * weight * 1.6

        for hz in room.hazards:
            if hz.get("kind", "acid") != "acid":
                continue
            dx = sv["x"] - hz["x"]
            dy = sv["y"] - hz["y"]
            d = math.hypot(dx, dy) or 1.0
            if d < hz["radius"] + 55.0:
                repel_x += (dx / d) * 2.5
                repel_y += (dy / d) * 2.5

        # Ưu tiên né khẩn cấp vòng cảnh báo chiêu của Boss / Mini-Boss (Telegraphs)
        in_telegraph = False
        for tg in getattr(room, "telegraphs", ()):
            dx = sv["x"] - tg["x"]
            dy = sv["y"] - tg["y"]
            d = math.hypot(dx, dy) or 1.0
            if d < tg["radius"] + 38.0:
                in_telegraph = True
                repel_x += (dx / d) * 4.2
                repel_y += (dy / d) * 4.2

        # Kéo nhẹ về giữa bản đồ để không bị dồn vào góc chết
        cx_dx = ARENA_W * 0.5 - sv["x"]
        cy_dy = ARENA_H * 0.5 - sv["y"]
        cd = math.hypot(cx_dx, cy_dy) or 1.0
        if cd > 260.0:
            repel_x += (cx_dx / cd) * 0.65
            repel_y += (cy_dy / cd) * 0.65

        # Nhặt túi máu nếu đang thấp máu
        if sv["hp"] < sv["maxHp"] * 0.72 and room.pickups:
            meds = [pk for pk in room.pickups if pk["kind"] == "med"]
            if meds:
                pk = min(meds, key=lambda p: math.hypot(p["x"] - sv["x"], p["y"] - sv["y"]))
                pdx, pdy = pk["x"] - sv["x"], pk["y"] - sv["y"]
                pd = math.hypot(pdx, pdy) or 1.0
                if pd < 320.0:
                    repel_x += (pdx / pd) * 1.2
                    repel_y += (pdy / pd) * 1.2

        rm = math.hypot(repel_x, repel_y)
        if rm > 0.15:
            move_x, move_y = repel_x / rm, repel_y / rm
            if in_telegraph and sv["dashCd"] <= now and level != "easy":
                sv["vx"], sv["vy"] = move_x, move_y
                room._do_dash(sv, now)

    sv["vx"] = move_x
    sv["vy"] = move_y

    # 4. Chọn mục tiêu & khai hỏa
    if not room.zombies:
        sv["firing"] = False
        return

    obs = room._obstacles()

    def _has_los(z: dict) -> bool:
        return not any(_segment_hits_rect(sv["x"], sv["y"], z["x"], z["y"], ob) is not None for ob in obs)

    # Ưu tiên zombie nhìn thấy trực tiếp (không bị tường chắn) + Special Infected / Mini-Boss / Boss
    def threat_score(z: dict) -> float:
        d = math.hypot(z["x"] - sv["x"], z["y"] - sv["y"])
        prio = 0.70 if z["kind"] in ("runner", "spitter", "butcher", "queen", "boss", "titan") else 1.0
        return d * prio

    visible = [z for z in room.zombies if _has_los(z)]
    target = min(visible or room.zombies, key=threat_score)
    target_visible = bool(visible)
    td = math.hypot(target["x"] - sv["x"], target["y"] - sv["y"])
    aim_err = {"easy": 0.16, "normal": 0.08, "hard": 0.025}[level]
    sv["aim"] = math.atan2(target["y"] - sv["y"], target["x"] - sv["x"]) + room.rng.uniform(-aim_err, aim_err)

    # Nếu zombie quá sát và sẵn sàng Dash -> lướt né
    if td < 68.0 and sv["dashCd"] <= now and level != "easy":
        room._do_dash(sv, now)

    # Ném lựu đạn nếu có cụm >= 3 zombie gần nhau
    if sv["grenades"] > 0 and 110.0 < td < 330.0 and level != "easy":
        cluster = sum(1 for z in room.zombies if math.hypot(z["x"] - target["x"], z["y"] - target["y"]) <= 110.0)
        if cluster >= 3:
            room._throw_grenade(sv, target["x"], target["y"])

    # Tự chọn súng tốt nhất còn đạn
    best_w = sv["weapon"]
    if sv["mag"].get(best_w, 0) <= 0 and WEAPONS[best_w]["reserve"] != -1 and sv["reserve"].get(best_w, 0) <= 0:
        for wid in reversed(sv["weapons"]):
            if WEAPONS[wid]["reserve"] == -1 or sv["reserve"].get(wid, 0) > 0 or sv["mag"].get(wid, 0) > 0:
                best_w = wid
                sv["weapon"] = wid
                break

    w_range = WEAPONS[best_w]["range"]
    fire_chance = {"easy": 0.55, "normal": 0.82, "hard": 1.0}[level]
    # Z12: Chỉ khai hỏa khi có tầm nhìn trực tiếp (hoặc dùng súng phóng lựu nổ lan) để tránh bắn phí đạn vào tường
    can_shoot_target = target_visible or WEAPONS[best_w].get("splash", 0.0) > 0
    sv["firing"] = can_shoot_target and td <= w_range * 1.05 and room.rng.random() <= fire_chance
