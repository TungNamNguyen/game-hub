"""Đêm Tử Thần (Zombie Outbreak) — Game bắn súng sinh tồn Zombie Multiplayer (1–6 người Co-op & AI Bots).

Lấy cảm hứng từ các cơ chế xuất sắc nhất của Left 4 Dead 2, Killing Floor 2, CoD Zombies & Alien Swarm:
  - 9 chủng Zombie, Mini-Boss & Boss Đột Biến (Walker, Runner, Bloater, Spitter, Brute, Đao Đồ Tể, Mẫu Hậu Độc Dược, Chúa Tể & Bạo Chúa Hủy Diệt)
  - 4 lớp Chiến Binh (Assault, Medic, Engineer, Vanguard), 8 vũ khí có thể nâng cấp Mk.I–Mk.III & 5 Perk
  - Cơ chế Gục Ngã (Downed 15s) & Đồng đội cứu thương (Revive 2.5s), Lướt né (Dash), Lựu đạn, Trụ súng Sentry & Huyết thanh
  - Pha Tiếp Tế giữa các đợt (Armory Shop 16s) để mua súng, nâng cấp Mk.II/III, giáp, trụ súng và kỹ năng
  - Chạy mô phỏng authoritative ở 15 Hz phía server và nội suy Dead-Reckoning 60 FPS mượt mà ở client Canvas 2.5D
"""
from __future__ import annotations

import math
import random
import time

from games import GameError, Player, SeatedRoom, bot_uid

ARENA_W = 1400.0
ARENA_H = 900.0
PLAYER_RADIUS = 17.0
SHOP_SECONDS = 16.0
BLEEDOUT_SECONDS = 15.0
REVIVE_SECONDS = 2.5
REVIVE_RADIUS = 72.0
MAX_WEAPON_LV = 3

ZOMBIE_BOT_NAMES = ("Biệt Kích", "Sói Đêm", "Quân Y 09", "Thiết Giáp", "Xạ Thủ 07", "Bóng Ma")

CLASSES: dict[str, dict] = {
    "assault": {
        "label": "Đặc Nhiệm",
        "hp": 110.0,
        "armor": 20.0,
        "speed": 240.0,
        "dmgMult": 1.2,
        "reloadMult": 0.72,
        "reviveSpeed": 1.0,
        "healAura": 0.0,
        "turretMult": 1.0,
        "dashCd": 3.4,
        "startWeapons": ["pistol", "smg"],
        "startTurrets": 0,
        "startGrenades": 2,
    },
    "medic": {
        "label": "Quân Y",
        "hp": 105.0,
        "armor": 15.0,
        "speed": 248.0,
        "dmgMult": 1.0,
        "reloadMult": 0.92,
        "reviveSpeed": 2.1,
        "healAura": 2.5,
        "turretMult": 1.0,
        "dashCd": 3.2,
        "startWeapons": ["pistol", "smg"],
        "startTurrets": 0,
        "startGrenades": 2,
    },
    "engineer": {
        "label": "Công Binh",
        "hp": 105.0,
        "armor": 25.0,
        "speed": 228.0,
        "dmgMult": 1.0,
        "reloadMult": 0.88,
        "reviveSpeed": 1.15,
        "healAura": 0.0,
        "turretMult": 1.35,
        "dashCd": 3.5,
        "startWeapons": ["pistol", "shotgun"],
        "startTurrets": 1,
        "startGrenades": 1,
    },
    "vanguard": {
        "label": "Thiết Giáp",
        "hp": 150.0,
        "armor": 55.0,
        "speed": 222.0,
        "dmgMult": 1.05,
        "reloadMult": 1.0,
        "reviveSpeed": 1.0,
        "healAura": 0.0,
        "turretMult": 1.0,
        "dashCd": 2.4,
        "startWeapons": ["pistol", "shotgun"],
        "startTurrets": 0,
        "startGrenades": 2,
    },
}

WEAPONS: dict[str, dict] = {
    "pistol": {
        "name": "Súng Lục M1911",
        "cost": 0,
        "dmg": 26.0,
        "rate": 0.25,
        "mag": 15,
        "reserve": -1,
        "reload": 1.05,
        "pellets": 1,
        "spread": 0.04,
        "range": 600.0,
        "pierce": 1,
        "knockback": 32.0,
        "burn": 0.0,
        "splash": 0.0,
        "color": "#fde047",
    },
    "smg": {
        "name": "Tiểu Liên Vector",
        "cost": 220,
        "dmg": 18.0,
        "rate": 0.095,
        "mag": 36,
        "reserve": 240,
        "reload": 1.4,
        "pellets": 1,
        "spread": 0.09,
        "range": 520.0,
        "pierce": 1,
        "knockback": 18.0,
        "burn": 0.0,
        "splash": 0.0,
        "color": "#38bdf8",
    },
    "shotgun": {
        "name": "Shotgun M870",
        "cost": 320,
        "dmg": 21.0,
        "rate": 0.72,
        "mag": 8,
        "reserve": 72,
        "reload": 1.7,
        "pellets": 7,
        "spread": 0.30,
        "range": 350.0,
        "pierce": 1,
        "knockback": 95.0,
        "burn": 0.0,
        "splash": 0.0,
        "color": "#fb923c",
    },
    "rifle": {
        "name": "Súng Trường AK-47",
        "cost": 480,
        "dmg": 42.0,
        "rate": 0.15,
        "mag": 30,
        "reserve": 210,
        "reload": 1.6,
        "pellets": 1,
        "spread": 0.035,
        "range": 780.0,
        "pierce": 2,
        "knockback": 48.0,
        "burn": 0.0,
        "splash": 0.0,
        "color": "#facc15",
    },
    "launcher": {
        "name": "Phóng Lựu M79",
        "cost": 600,
        "dmg": 145.0,
        "rate": 0.92,
        "mag": 4,
        "reserve": 28,
        "reload": 2.0,
        "pellets": 1,
        "spread": 0.02,
        "range": 620.0,
        "pierce": 1,
        "knockback": 120.0,
        "burn": 0.0,
        "splash": 110.0,
        "color": "#f43f5e",
    },
    "flamer": {
        "name": "Súng Phun Lửa",
        "cost": 640,
        "dmg": 18.0,
        "rate": 0.09,
        "mag": 75,
        "reserve": 300,
        "reload": 1.9,
        "pellets": 2,
        "spread": 0.24,
        "range": 270.0,
        "pierce": 3,
        "knockback": 12.0,
        "burn": 12.0,
        "splash": 0.0,
        "chain": 0,
        "color": "#f97316",
    },
    "tesla": {
        "name": "Hồ Quang Tesla",
        "cost": 760,
        "dmg": 54.0,
        "rate": 0.36,
        "mag": 16,
        "reserve": 96,
        "reload": 1.75,
        "pellets": 1,
        "spread": 0.02,
        "range": 460.0,
        "pierce": 1,
        "knockback": 22.0,
        "burn": 0.0,
        "splash": 0.0,
        "chain": 4,
        "color": "#60a5fa",
    },
    "railgun": {
        "name": "Súng Điện Từ Railgun",
        "cost": 900,
        "dmg": 155.0,
        "rate": 0.85,
        "mag": 6,
        "reserve": 42,
        "reload": 1.95,
        "pellets": 1,
        "spread": 0.005,
        "range": 1000.0,
        "pierce": 8,
        "knockback": 115.0,
        "burn": 0.0,
        "splash": 0.0,
        "chain": 0,
        "color": "#22d3ee",
    },
}

WEAPON_ORDER = ("pistol", "smg", "shotgun", "rifle", "launcher", "flamer", "tesla", "railgun")

PERKS: dict[str, dict] = {
    "damage": {"name": "Đạn Xuyên Phá", "cost": 200, "max": 3},
    "reload": {"name": "Băng Đạn Lớn", "cost": 180, "max": 3},
    "speed": {"name": "Giày Chiến Thuật", "cost": 170, "max": 3},
    "armor": {"name": "Giáp Nano", "cost": 190, "max": 3},
    "vamp": {"name": "Đạn Hút Máu", "cost": 240, "max": 3},
}

SHOP_ITEMS: dict[str, dict] = {
    "medkit": {"name": "Túi Máu & Giáp", "cost": 120, "desc": "+65 HP · +30 Giáp", "cat": "supply"},
    "shield": {"name": "Nạp Đầy Giáp", "cost": 140, "desc": "Hồi đầy 100% thanh Giáp (Shield)", "cat": "supply"},
    "ammo": {"name": "Tiếp Đạn Toàn Bộ", "cost": 100, "desc": "Nạp đầy đạn mọi súng", "cat": "supply"},
    "stim": {"name": "Huyết Thanh Cuồng Phong", "cost": 160, "desc": "+40 HP · Reset Dash · +25% Tốc độ 20s", "cat": "supply"},
    "grenade": {"name": "Lựu Đạn Nổ (+2)", "cost": 140, "desc": "Phím [G] · Nổ diện rộng (tối đa 5)", "cat": "gadget"},
    "cryo": {"name": "Lựu Đạn Băng (+2)", "cost": 150, "desc": "Phím [F] · Đóng băng chậm 65% trong 5.5s", "cat": "gadget"},
    "emp": {"name": "Lựu Đạn EMP (+2)", "cost": 160, "desc": "Phím [Q] · Làm choáng Stun 2.8s ngắt chiêu", "cat": "gadget"},
    "mine": {"name": "Mìn Từ Trường (+2)", "cost": 170, "desc": "Phím [C] · Đặt mìn nổ 220 DMG + Choáng 1.5s", "cat": "gadget"},
    "turret": {"name": "Trụ Súng Sentry (+1)", "cost": 280, "desc": "Phím [E] · Có thanh HP & đạn (tối đa 3)", "cat": "gadget"},
    "repair": {"name": "Sửa & Nạp Trụ Súng", "cost": 150, "desc": "Hồi 100% HP & đạn cho toàn bộ Trụ của bạn", "cat": "gadget"},
}

ZOMBIE_SPECS: dict[str, dict] = {
    "walker": {"hp": 58.0, "speed": 84.0, "radius": 16.0, "dmg": 14.0, "reward": 26, "score": 100},
    "runner": {"hp": 38.0, "speed": 166.0, "radius": 13.0, "dmg": 12.0, "reward": 34, "score": 140},
    "bloater": {"hp": 115.0, "speed": 68.0, "radius": 22.0, "dmg": 18.0, "reward": 52, "score": 220},
    "spitter": {"hp": 72.0, "speed": 80.0, "radius": 15.0, "dmg": 12.0, "reward": 50, "score": 210},
    "brute": {"hp": 290.0, "speed": 74.0, "radius": 26.0, "dmg": 28.0, "reward": 98, "score": 420},
    "butcher": {
        "hp": 620.0, "speed": 106.0, "radius": 29.0, "dmg": 30.0, "reward": 230, "score": 820,
        "miniBoss": True, "title": "Đao Đồ Tể",
    },
    "queen": {
        "hp": 560.0, "speed": 86.0, "radius": 28.0, "dmg": 22.0, "reward": 240, "score": 860,
        "miniBoss": True, "title": "Mẫu Hậu Độc Dược",
    },
    "boss": {
        "hp": 1250.0, "speed": 80.0, "radius": 38.0, "dmg": 36.0, "reward": 440, "score": 1550,
        "boss": True, "title": "Chúa Tể Đột Biến",
    },
    "titan": {
        "hp": 1850.0, "speed": 76.0, "radius": 44.0, "dmg": 44.0, "reward": 680, "score": 2400,
        "boss": True, "title": "Bạo Chúa Hủy Diệt",
    },
}

BOSS_KINDS = ("butcher", "queen", "boss", "titan")

# Các chướng ngại vật hình chữ nhật (x, y, w, h, kind) tạo chiến thuật vòng vây cho 6 bản đồ
MAP_OBSTACLES: dict[str, list[dict]] = {
    "outpost": [
        {"x": 260, "y": 210, "w": 150, "h": 54, "kind": "barricade"},
        {"x": 990, "y": 210, "w": 150, "h": 54, "kind": "barricade"},
        {"x": 260, "y": 636, "w": 150, "h": 54, "kind": "barricade"},
        {"x": 990, "y": 636, "w": 150, "h": 54, "kind": "barricade"},
        {"x": 625, "y": 385, "w": 150, "h": 130, "kind": "bunker"},
        {"x": 160, "y": 410, "w": 56, "h": 80, "kind": "crate"},
        {"x": 1184, "y": 410, "w": 56, "h": 80, "kind": "crate"},
    ],
    "lab": [
        {"x": 340, "y": 170, "w": 72, "h": 180, "kind": "biotank"},
        {"x": 988, "y": 170, "w": 72, "h": 180, "kind": "biotank"},
        {"x": 340, "y": 550, "w": 72, "h": 180, "kind": "biotank"},
        {"x": 988, "y": 550, "w": 72, "h": 180, "kind": "biotank"},
        {"x": 610, "y": 240, "w": 180, "h": 46, "kind": "console"},
        {"x": 610, "y": 614, "w": 180, "h": 46, "kind": "console"},
    ],
    "metro": [
        {"x": 200, "y": 175, "w": 260, "h": 76, "kind": "train_car"},
        {"x": 940, "y": 175, "w": 260, "h": 76, "kind": "train_car"},
        {"x": 200, "y": 649, "w": 260, "h": 76, "kind": "train_car"},
        {"x": 940, "y": 649, "w": 260, "h": 76, "kind": "train_car"},
        {"x": 540, "y": 415, "w": 66, "h": 70, "kind": "pillar"},
        {"x": 794, "y": 415, "w": 66, "h": 70, "kind": "pillar"},
    ],
    "dock": [
        {"x": 230, "y": 200, "w": 210, "h": 68, "kind": "container"},
        {"x": 960, "y": 200, "w": 210, "h": 68, "kind": "container"},
        {"x": 230, "y": 632, "w": 210, "h": 68, "kind": "container"},
        {"x": 960, "y": 632, "w": 210, "h": 68, "kind": "container"},
        {"x": 615, "y": 210, "w": 170, "h": 54, "kind": "crate"},
        {"x": 615, "y": 636, "w": 170, "h": 54, "kind": "crate"},
        {"x": 195, "y": 405, "w": 70, "h": 90, "kind": "container"},
        {"x": 1135, "y": 405, "w": 70, "h": 90, "kind": "container"},
    ],
    "reactor": [
        {"x": 635, "y": 385, "w": 130, "h": 130, "kind": "reactor"},
        {"x": 270, "y": 205, "w": 96, "h": 96, "kind": "cooling_tower"},
        {"x": 1034, "y": 205, "w": 96, "h": 96, "kind": "cooling_tower"},
        {"x": 270, "y": 599, "w": 96, "h": 96, "kind": "cooling_tower"},
        {"x": 1034, "y": 599, "w": 96, "h": 96, "kind": "cooling_tower"},
        {"x": 450, "y": 424, "w": 64, "h": 52, "kind": "console"},
        {"x": 886, "y": 424, "w": 64, "h": 52, "kind": "console"},
    ],
    "endless": [
        {"x": 300, "y": 260, "w": 90, "h": 90, "kind": "pillar"},
        {"x": 1010, "y": 260, "w": 90, "h": 90, "kind": "pillar"},
        {"x": 300, "y": 550, "w": 90, "h": 90, "kind": "pillar"},
        {"x": 1010, "y": 550, "w": 90, "h": 90, "kind": "pillar"},
        {"x": 655, "y": 405, "w": 90, "h": 90, "kind": "reactor"},
    ],
}


def _clamp(val: float, lo: float, hi: float) -> float:
    return lo if val < lo else (hi if val > hi else val)


def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _resolve_circle_obstacles(x: float, y: float, r: float, obstacles: list[dict]) -> tuple[float, float]:
    """Đẩy hình tròn (x, y, r) ra ngoài các vật cản chữ nhật & biên bản đồ."""
    x = _clamp(x, r + 10.0, ARENA_W - r - 10.0)
    y = _clamp(y, r + 10.0, ARENA_H - r - 10.0)
    for ob in obstacles:
        ox, oy, ow, oh = ob["x"], ob["y"], ob["w"], ob["h"]
        cx = _clamp(x, ox, ox + ow)
        cy = _clamp(y, oy, oy + oh)
        dx = x - cx
        dy = y - cy
        d2 = dx * dx + dy * dy
        if d2 < r * r:
            if d2 > 1e-6:
                d = math.sqrt(d2)
                push = r - d
                x += (dx / d) * push
                y += (dy / d) * push
            else:
                # Tâm nằm bên trong hình chữ nhật -> đẩy theo cạnh gần nhất
                left_d = x - ox
                right_d = (ox + ow) - x
                top_d = y - oy
                bot_d = (oy + oh) - y
                m = min(left_d, right_d, top_d, bot_d)
                if m == left_d:
                    x = ox - r
                elif m == right_d:
                    x = ox + ow + r
                elif m == top_d:
                    y = oy - r
                else:
                    y = oy + oh + r
    x = _clamp(x, r + 10.0, ARENA_W - r - 10.0)
    y = _clamp(y, r + 10.0, ARENA_H - r - 10.0)
    return x, y


def _segment_hits_rect(x1: float, y1: float, x2: float, y2: float, ob: dict) -> float | None:
    """Trả về tham số t trong [0, 1] nơi đoạn thẳng chạm hình chữ nhật (Slab method), hoặc None."""
    ox, oy, ow, oh = ob["x"], ob["y"], ob["w"], ob["h"]
    dx = x2 - x1
    dy = y2 - y1
    tmin, tmax = 0.0, 1.0
    for p, q, lo, hi in ((dx, x1, ox, ox + ow), (dy, y1, oy, oy + oh)):
        if abs(p) < 1e-8:
            if q < lo or q > hi:
                return None
        else:
            t1 = (lo - q) / p
            t2 = (hi - q) / p
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin if 0.0 <= tmin <= 1.0 else None


def _ray_circle_t(x1: float, y1: float, x2: float, y2: float, cx: float, cy: float, r: float) -> float | None:
    """Trả về tham số t trong [0, 1] nơi tia bắn trúng hình tròn (cx, cy, r), hoặc None."""
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-6:
        return None
    t = ((cx - x1) * dx + (cy - y1) * dy) / l2
    if t < 0.0 or t > 1.0:
        return None
    px = x1 + t * dx
    py = y1 + t * dy
    if (px - cx) ** 2 + (py - cy) ** 2 <= r * r:
        return t
    return None


def _finite_float(val, default: float = 0.0) -> float:
    """Ép sang float hữu hạn; chặn NaN/Infinity từ client làm đứng phòng hoặc lỗi JSON."""
    try:
        out = float(val)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _steer_around_obstacles(
    zx: float, zy: float, tx: float, ty: float, radius: float, obs: list[dict]
) -> tuple[float, float]:
    """Tính hướng di chuyển (nx, ny) có vòng qua góc vật cản nếu đường thẳng tới mục tiêu bị chắn."""
    dx, dy = tx - zx, ty - zy
    d = math.hypot(dx, dy) or 1.0
    nx, ny = dx / d, dy / d
    blocker = None
    best_t = 2.0
    for ob in obs:
        ht = _segment_hits_rect(zx, zy, tx, ty, ob)
        if ht is not None and ht < best_t:
            best_t = ht
            blocker = ob
    if blocker is None:
        return nx, ny
    pad = radius + 22.0
    corners = (
        (blocker["x"] - pad, blocker["y"] - pad),
        (blocker["x"] + blocker["w"] + pad, blocker["y"] - pad),
        (blocker["x"] - pad, blocker["y"] + blocker["h"] + pad),
        (blocker["x"] + blocker["w"] + pad, blocker["y"] + blocker["h"] + pad),
    )
    best_c = None
    best_cost = float("inf")
    for cx, cy in corners:
        if not (24.0 <= cx <= ARENA_W - 24.0 and 24.0 <= cy <= ARENA_H - 24.0):
            continue
        cost = _dist(zx, zy, cx, cy) + _dist(cx, cy, tx, ty)
        if cost < best_cost:
            best_cost = cost
            best_c = (cx, cy)
    if best_c is None:
        return nx, ny
    cdx, cdy = best_c[0] - zx, best_c[1] - zy
    cd = math.hypot(cdx, cdy) or 1.0
    return cdx / cd, cdy / cd


class ZombieRoom(SeatedRoom):
    CHANNEL = "zombie"
    SEATS = ("1", "2", "3", "4", "5", "6")
    HAS_CLOCK = True
    FAST_TICK = True  # Hub chạy vòng lặp 15 Hz khi phòng đang ở trạng thái playing
    START_STATUS = "playing"
    DEFAULT_MODE = "outpost"
    MODES = {
        "outpost": {"label": "Căn Cứ Bỏ Hoang (10 Đợt)", "maxWaves": 10},
        "lab": {"label": "Phòng Thí Nghiệm Ngầm (15 Đợt)", "maxWaves": 15},
        "metro": {"label": "Ga Tàu Điện Tử Thần (12 Đợt)", "maxWaves": 12},
        "dock": {"label": "Bến Cảng Container (12 Đợt)", "maxWaves": 12},
        "reactor": {"label": "Lò Phản Ứng Hạt Nhân (15 Đợt)", "maxWaves": 15},
        "endless": {"label": "Tử Thủ Vô Tận (Endless)", "maxWaves": 0},
    }

    def __init__(self, code: str, mode: str = "") -> None:
        super().__init__(code, mode)
        self.rng = random.Random()
        self.seat_classes: dict[str, str] = {
            "1": "assault",
            "2": "medic",
            "3": "engineer",
            "4": "vanguard",
            "5": "assault",
            "6": "medic",
        }
        self.config: dict = {
            "difficulty": "normal",  # easy | normal | hard
        }
        # Tăng đơn điệu xuyên suốt vòng đời phòng để client không bao giờ bỏ qua event sau Rematch
        self._event_seq: int = 0
        self._last_broadcast_event_seq: int = 0
        self._last_static_ver: tuple = ()
        self._entity_seq: int = 0
        self.match_id: int = 0
        self.reset_match()

    def _seat_label(self, mark: str) -> str:
        return f"Chiến binh {mark}"

    def _seated_marks(self) -> list[str]:
        return [m for m in self.SEATS if self.seat(m) is not None]

    def _obstacles(self) -> list[dict]:
        return MAP_OBSTACLES.get(self.mode, MAP_OBSTACLES["outpost"])

    def _max_waves(self) -> int:
        return int(self.MODES.get(self.mode, self.MODES["outpost"]).get("maxWaves", 10))

    def reset_match(self) -> None:
        self.phase: str = "waiting"  # waiting | wave | shop | finished
        self.wave: int = 0
        self.max_waves: int = self._max_waves()
        self.victory: bool = False
        self.wave_remaining_to_spawn: list[str] = []
        self.spawn_timer: float = 0.0
        self.shop_deadline: float = 0.0
        self.last_tick_at: float = 0.0
        self.survivors: dict[str, dict] = {}
        self.zombies: list[dict] = []
        self.projectiles: list[dict] = []  # Đạn axit Spitter/Boss, lựu đạn nổ/băng/EMP & tên lửa M79
        self.hazards: list[dict] = []      # Vũng axit độc & vùng bão băng Cryo trên mặt đất
        self.telegraphs: list[dict] = []   # Vòng cảnh báo chiêu đặc biệt của Mini-Boss / Boss
        self.turrets: list[dict] = []      # Trụ súng tự động Sentry (có HP & đạn)
        self.mines: list[dict] = []        # Mìn từ trường đặt trên sân
        self.barrels: list[dict] = []      # Thùng phuy nhiên liệu đỏ bắn nổ chiến thuật
        self.pickups: list[dict] = []      # Vật phẩm rơi (Máu, Đạn, Tiền & Power-Up toàn đội)
        self.events: list[dict] = []       # Ring buffer hiệu ứng VFX cho client 60 FPS
        self.double_dmg_until: float = 0.0
        self.inf_ammo_until: float = 0.0
        self.total_kills: int = 0
        self.match_started_at: float = 0.0

    def _emit(self, _event_type: str, **payload) -> None:
        self._event_seq += 1
        self.events.append({"seq": self._event_seq, "t": _event_type, **payload})
        if len(self.events) > 160:
            del self.events[:-160]

    def _next_id(self) -> int:
        self._entity_seq += 1
        return self._entity_seq

    def _try_start(self) -> None:
        # Cho phép 1–6 người chọn lớp nhân vật & thêm Bot trước khi bấm Bắt đầu.
        return

    # ---- Bot management ---------------------------------------------------- #
    def add_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Thêm 1 AI Survivor Bot cho phòng chơi đơn (/api/rooms/solo)."""
        if self.bot_players():
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        if not mark:
            humans = [m for m in self._seated_marks() if not self.seat(m).bot]
            if not humans:
                mark = "2" if "2" in free else (free[1] if len(free) >= 2 else "")
            elif free:
                mark = free[0]
        if not mark or mark not in free:
            raise GameError("Không còn ghế cho máy.")
        lvl = level if level in ("easy", "normal", "hard") else "normal"
        name = f"{ZOMBIE_BOT_NAMES[0]} (Bot)"
        return self._seat_bot(mark, lvl, name, slot=0)

    def add_single_bot(self, level: str = "normal", mark: str = "") -> Player:
        if self.in_progress():
            raise GameError("Không thể thêm Bot khi trận đang diễn ra.")
        free = self.free_marks()
        if not free:
            raise GameError("Đội đã đủ 6 chiến binh.")
        target = mark if mark in free else free[0]
        if mark and mark not in free:
            raise GameError("Vị trí đó đã có người.")
        slot = 0
        while bot_uid(slot) in self.players:
            slot += 1
        lvl = level if level in ("easy", "normal", "hard") else "normal"
        name = f"{ZOMBIE_BOT_NAMES[slot % len(ZOMBIE_BOT_NAMES)]} (Bot)"
        return self._seat_bot(target, lvl, name, slot=slot)

    def remove_bot_seat(self, mark: str) -> None:
        if self.in_progress():
            raise GameError("Không thể gỡ Bot khi trận đang diễn ra.")
        p = self.seat(mark)
        if p is None or not p.bot:
            raise GameError("Ghế này không có Bot.")
        self.players.pop(p.uid, None)
        self.rematch.discard(mark)
        self.system(f"Đã gỡ {p.name} khỏi {self._seat_label(mark)}.")
        if self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    def bot_pending(self, mark: str) -> bool:
        # AI chiến đấu được step mượt ở 15 Hz ngay trong tick(); _bot_loop chỉ dùng để vote_rematch.
        return False

    def progress_token(self) -> tuple:
        return (self.status, self.phase, self.wave, self.total_kills, self.winner)

    def apply_initial_config(self, config: dict) -> None:
        if not isinstance(config, dict):
            return
        new_mode = config.get("mode")
        if new_mode in self.MODES:
            self.mode = new_mode
            self.max_waves = self._max_waves()
        diff = config.get("difficulty")
        if diff in ("easy", "normal", "hard"):
            self.config["difficulty"] = diff

    # ---- Khởi tạo trận & Đợt tấn công -------------------------------------- #
    def _spawn_positions(self) -> list[tuple[float, float]]:
        return [
            (ARENA_W * 0.42, ARENA_H * 0.42),
            (ARENA_W * 0.58, ARENA_H * 0.42),
            (ARENA_W * 0.42, ARENA_H * 0.58),
            (ARENA_W * 0.58, ARENA_H * 0.58),
            (ARENA_W * 0.50, ARENA_H * 0.36),
            (ARENA_W * 0.50, ARENA_H * 0.64),
        ]

    def _create_survivor(self, mark: str, idx: int) -> dict:
        cls_id = self.seat_classes.get(mark, "assault")
        spec = CLASSES.get(cls_id, CLASSES["assault"])
        spawns = self._spawn_positions()
        sx, sy = spawns[idx % len(spawns)]
        sx, sy = _resolve_circle_obstacles(sx, sy, PLAYER_RADIUS, self._obstacles())
        owned = list(spec["startWeapons"])
        active_w = owned[-1] if owned else "pistol"
        ammo_mag = {w: WEAPONS[w]["mag"] for w in owned}
        ammo_res = {w: WEAPONS[w]["reserve"] for w in owned}
        w_lv = {w: 1 for w in owned}
        return {
            "mark": mark,
            "cls": cls_id,
            "x": sx,
            "y": sy,
            "vx": 0.0,
            "vy": 0.0,
            "moveVx": 0.0,
            "moveVy": 0.0,
            "aim": 0.0,
            "hp": spec["hp"],
            "maxHp": spec["hp"],
            "armor": spec["armor"],
            "maxArmor": spec["armor"] + 60.0,
            "alive": True,
            "downed": False,
            "bleedout": 0.0,
            "reviveProg": 0.0,
            "weapon": active_w,
            "weapons": owned,
            "weaponLv": w_lv,
            "mag": ammo_mag,
            "reserve": ammo_res,
            "reloadUntil": 0.0,
            "reloadTotal": 1.0,
            "fireCd": 0.0,
            "firing": False,
            "dashCd": 0.0,
            "dashUntil": 0.0,
            "dashVx": 0.0,
            "dashVy": 0.0,
            "stimUntil": 0.0,
            "grenades": int(spec["startGrenades"]),
            "cryos": 1,
            "emps": 1,
            "mines": 1 if cls_id == "engineer" else 0,
            "turrets": int(spec["startTurrets"]),
            "money": 180,
            "score": 0,
            "kills": 0,
            "revives": 0,
            "perks": {k: 0 for k in PERKS},
            "readyShop": False,
        }

    def _start_match(self) -> None:
        seated = self._seated_marks()
        if not seated:
            raise GameError("Cần ít nhất 1 chiến binh để bắt đầu.")
        self.winner = ""
        self.match_id += 1
        self.reset_match()
        self.max_waves = self._max_waves()
        for idx, m in enumerate(seated):
            self.survivors[m] = self._create_survivor(m, idx)
        self.status = self.START_STATUS
        self.rematch.clear()
        now = time.time()
        self.match_started_at = now
        self.last_tick_at = now
        self._begin_wave(1)
        self.system(f"🚨 Báo động Đêm Tử Thần! Đội {len(seated)} chiến binh đã triển khai tại {self.label}.")

    def _squad_scale(self) -> dict[str, float]:
        """Hệ số cân bằng sức mạnh, số lượng & tốc độ ra chiêu của Zombie theo quy mô đội (1–6 người/bot)."""
        n_players = max(1, len(self.survivors))
        extra = max(0, n_players - 1)
        return {
            "n_players": float(n_players),
            "extra": float(extra),
            "count_mult": 1.0 + extra * 0.34,          # 1p: 1.00x -> 6p: 2.70x số quái mỗi đợt
            "hp_mult": 1.0 + extra * 0.16,             # 1p: 1.00x -> 6p: 1.80x HP quái thường
            "mini_hp_mult": 1.0 + extra * 0.30,        # 1p: 1.00x -> 6p: 2.50x HP Mini-Boss
            "boss_hp_mult": 1.0 + extra * 0.36,        # 1p: 1.00x -> 6p: 2.80x HP Boss/Titan
            "dmg_mult": 1.0 + extra * 0.08,            # 1p: 1.00x -> 6p: 1.40x sát thương
            "speed_mult": 1.0 + min(0.22, extra * 0.042),  # 1p: 1.00x -> 6p: 1.21x tốc độ
            "cd_mult": max(0.62, 1.0 - extra * 0.07),  # 1p: 1.00x -> 6p: 0.65x hồi chiêu kỹ năng
            "spawn_rate_mult": 1.0 + extra * 0.36,     # 1p: 1.00x -> 6p: 2.80x nhịp sinh quái
        }

    def _build_wave_queue(self, wave: int) -> list[str]:
        sc = self._squad_scale()
        n_players = int(sc["n_players"])
        extra = int(sc["extra"])
        diff_mult = {"easy": 0.8, "normal": 1.0, "hard": 1.3}.get(self.config.get("difficulty", "normal"), 1.0)
        base_total = 8 + wave * 4
        total = int(round(base_total * sc["count_mult"] * diff_mult))
        sp_boost = min(0.14, extra * 0.025)
        queue: list[str] = []
        for _ in range(total):
            r = self.rng.random()
            if wave >= 4 and r < 0.11 + sp_boost * 0.55:
                queue.append("brute")
            elif wave >= 3 and r < 0.24 + sp_boost * 0.85:
                queue.append("spitter")
            elif wave >= 2 and r < 0.38 + sp_boost:
                queue.append("bloater")
            elif (wave >= 2 or n_players >= 4) and r < (0.62 + sp_boost if wave >= 2 else 0.26 + sp_boost * 0.5):
                queue.append("runner")
            else:
                queue.append("walker")

        # Mốc Boss & Mini-Boss rõ ràng, bổ sung hộ tống khi phòng đông (4–6 chiến binh):
        # - Đợt 5: Chúa Tể Đột Biến (boss)
        # - Đợt 10, 15, 20...: Bạo Chúa Hủy Diệt (titan)
        # - Đợt 3, 6, 8, 9, 12, 13, 14... (không trùng đợt Boss lớn): Mini-Boss Đao Đồ Tể (butcher) hoặc Mẫu Hậu Độc Dược (queen)
        if wave >= 10 and wave % 5 == 0:
            queue.append("titan")
            if wave >= 15 or n_players >= 5:
                queue.append("butcher")
            if n_players >= 6:
                queue.append("queen")
        elif wave % 5 == 0:
            queue.append("boss")
            if n_players >= 5:
                queue.append("butcher")
            elif n_players >= 4:
                queue.append("brute")
        elif wave % 3 == 0 or (wave >= 8 and wave % 2 == 0):
            mini_kind = "butcher" if (wave % 2 == 1) else "queen"
            queue.append(mini_kind)
            if n_players >= 5 and wave >= 6:
                queue.append("queen" if mini_kind == "butcher" else "butcher")
            elif n_players >= 4:
                queue.append("brute")

        self.rng.shuffle(queue)
        return queue

    def _spawn_wave_barrels(self) -> None:
        """Sinh 4 thùng phuy nhiên liệu nổ tại các nút giao chiến thuật đầu mỗi đợt."""
        self.barrels.clear()
        obs = self._obstacles()
        spots = [
            (ARENA_W * 0.25, ARENA_H * 0.35),
            (ARENA_W * 0.75, ARENA_H * 0.35),
            (ARENA_W * 0.25, ARENA_H * 0.65),
            (ARENA_W * 0.75, ARENA_H * 0.65),
        ]
        for bx, by in spots:
            rx = bx + self.rng.uniform(-45.0, 45.0)
            ry = by + self.rng.uniform(-35.0, 35.0)
            rx, ry = _resolve_circle_obstacles(rx, ry, 24.0, obs)
            self.barrels.append({
                "id": self._next_id(),
                "x": rx,
                "y": ry,
                "hp": 35.0,
                "maxHp": 35.0,
                "r": 16.0,
                "detonated": False,
            })

    def _begin_wave(self, wave_num: int) -> None:
        self.wave = wave_num
        self.phase = "wave"
        self.shop_deadline = 0.0
        self.telegraphs.clear()
        self._spawn_wave_barrels()
        # Z7/Z16: Người chơi ngồi vào ghế giữa trận sẽ được triển khai tham chiến ở đầu đợt kế tiếp
        for idx, m in enumerate(self._seated_marks()):
            if m not in self.survivors:
                sv_new = self._create_survivor(m, idx)
                sv_new["money"] = 180 + max(0, wave_num - 1) * 140
                self.survivors[m] = sv_new
                p = self.seat(m)
                if p:
                    self.system(f"🪖 {p.name} đã nhảy dù tham chiến ở Đợt {wave_num}!")
        self.wave_remaining_to_spawn = self._build_wave_queue(wave_num)
        self.spawn_timer = 0.4
        # Hồi sinh các chiến binh đã hy sinh ở đợt trước với 75% HP
        spawns = self._spawn_positions()
        for idx, (m, sv) in enumerate(self.survivors.items()):
            sv["readyShop"] = False
            if not sv["alive"] or sv["downed"]:
                sx, sy = spawns[idx % len(spawns)]
                sx, sy = _resolve_circle_obstacles(sx, sy, PLAYER_RADIUS, self._obstacles())
                sv["x"], sv["y"] = sx, sy
                sv["alive"] = True
                sv["downed"] = False
                sv["bleedout"] = 0.0
                sv["reviveProg"] = 0.0
                sv["hp"] = round(sv["maxHp"] * 0.75, 1)
                sv["armor"] = min(sv["maxArmor"], max(sv["armor"], 20.0))
        boss_in_wave = next((k for k in ("titan", "boss", "butcher", "queen") if k in self.wave_remaining_to_spawn), "")
        has_major = boss_in_wave in ("boss", "titan")
        has_mini = boss_in_wave in ("butcher", "queen")
        boss_title = ZOMBIE_SPECS[boss_in_wave]["title"] if boss_in_wave else ""
        self._emit("wave", wave=wave_num, boss=has_major, miniBoss=has_mini, bossTitle=boss_title)
        if has_major:
            boss_note = f" ⚠️ BOSS {boss_title.upper()} XUẤT HIỆN!"
        elif has_mini:
            boss_note = f" 🔥 MINI-BOSS {boss_title.upper()} XUẤT HIỆN!"
        else:
            boss_note = ""
        self.system(f"☣️ Đợt {wave_num} bắt đầu! ({len(self.wave_remaining_to_spawn)} quái vật){boss_note}")

    def _spawn_one_zombie(self, kind: str) -> dict:
        spec = ZOMBIE_SPECS[kind]
        sc = self._squad_scale()
        diff_hp = {"easy": 0.82, "normal": 1.0, "hard": 1.28}.get(self.config.get("difficulty", "normal"), 1.0)
        wave_scale = 1.0 + (self.wave - 1) * 0.13
        if kind in ("boss", "titan"):
            hp = (spec["hp"] + self.wave * (240.0 if kind == "titan" else 195.0)) * diff_hp * sc["boss_hp_mult"]
        elif kind in ("butcher", "queen"):
            hp = (spec["hp"] + self.wave * 105.0) * diff_hp * sc["mini_hp_mult"]
        else:
            hp = spec["hp"] * diff_hp * wave_scale * sc["hp_mult"]
        # Sinh ở 4 rìa bản đồ, tránh spawn ngay sát người chơi đang đứng rìa (< 180px)
        pad = spec["radius"] + 16.0
        alive_svs = [sv for sv in self.survivors.values() if sv["alive"]]
        best_pos = (pad, pad)
        best_min_d = -1.0
        for _ in range(6):
            edge = self.rng.randint(0, 3)
            if edge == 0:
                cx, cy = self.rng.uniform(pad, ARENA_W - pad), pad
            elif edge == 1:
                cx, cy = self.rng.uniform(pad, ARENA_W - pad), ARENA_H - pad
            elif edge == 2:
                cx, cy = pad, self.rng.uniform(pad, ARENA_H - pad)
            else:
                cx, cy = ARENA_W - pad, self.rng.uniform(pad, ARENA_H - pad)
            min_d = min((_dist(cx, cy, sv["x"], sv["y"]) for sv in alive_svs), default=9999.0)
            if min_d > best_min_d:
                best_min_d = min_d
                best_pos = (cx, cy)
            if min_d >= 180.0:
                break
        x, y = _resolve_circle_obstacles(best_pos[0], best_pos[1], spec["radius"], self._obstacles())
        z_id = self._next_id()
        z = {
            "id": z_id,
            "kind": kind,
            "x": x,
            "y": y,
            "vx": 0.0,
            "vy": 0.0,
            "hp": hp,
            "maxHp": hp,
            "speed": spec["speed"] * (1.0 + min(0.38, (self.wave - 1) * 0.028)) * sc["speed_mult"],
            "radius": spec["radius"],
            "dmg": spec["dmg"] * diff_hp * sc["dmg_mult"],
            "reward": spec["reward"],
            "score": spec["score"],
            "atkCd": 0.0,
            "specialCd": self.rng.uniform(1.5, 2.8) * sc["cd_mult"],
            "flankSide": 1.0 if (z_id % 2 == 0) else -1.0,
            "flankStrength": self.rng.uniform(0.38, 0.72) if kind in ("runner", "walker") else 0.0,
            "chargeTimer": 0.0,
            "chargeVx": 0.0,
            "chargeVy": 0.0,
            "burnTimer": 0.0,
            "burnDps": 0.0,
            "burnOwner": "",
            "burnHitCd": 0.0,
            "slowTimer": 0.0,
            "stunTimer": 0.0,
            "teslaStunCd": 0.0,
            "hitFlash": 0.0,
            "enraged": False,
            "skillLabel": "",
            "skillLabelUntil": 0.0,
        }
        self.zombies.append(z)
        return z

    # ---- Chiến đấu, Đạn đạo & Kỹ năng -------------------------------------- #
    def _weapon_lv(self, sv: dict, wid: str) -> int:
        return int(sv.get("weaponLv", {}).get(wid, 1))

    def _weapon_upgrade_cost(self, wid: str, cur_lv: int) -> int:
        base = max(180, int(WEAPONS[wid]["cost"]))
        return int(round(base * (0.75 if cur_lv == 1 else 1.25)))

    def _weapon_mag_cap(self, sv: dict, wid: str) -> int:
        base = WEAPONS[wid]["mag"]
        perk_lvl = sv["perks"].get("reload", 0)
        w_lv = self._weapon_lv(sv, wid)
        return int(round(base * (1.0 + 0.30 * perk_lvl) * (1.0 + 0.20 * (w_lv - 1))))

    def _trigger_reload(self, sv: dict, now: float) -> None:
        wid = sv["weapon"]
        w = WEAPONS[wid]
        cap = self._weapon_mag_cap(sv, wid)
        if sv["mag"].get(wid, 0) >= cap or sv["reloadUntil"] > now:
            return
        if w["reserve"] != -1 and sv["reserve"].get(wid, 0) <= 0:
            return
        cls_mult = CLASSES[sv["cls"]]["reloadMult"]
        perk_mult = max(0.45, 1.0 - 0.18 * sv["perks"].get("reload", 0))
        stim_mult = 0.78 if sv.get("stimUntil", 0.0) > now else 1.0
        dur = max(0.35, w["reload"] * cls_mult * perk_mult * stim_mult)
        sv["reloadTotal"] = dur
        sv["reloadUntil"] = now + dur
        self._emit("reload", mark=sv["mark"], weapon=wid)

    def _damage_zombie(
        self,
        z: dict,
        dmg: float,
        owner_mark: str,
        kb_x: float = 0.0,
        kb_y: float = 0.0,
        emit_hit: bool = True,
    ) -> bool:
        """Gây sát thương lên zombie. Trả về True nếu zombie vừa bị hạ gục."""
        if z["hp"] <= 0:
            return False
        z["hp"] -= dmg
        z["hitFlash"] = 0.12
        if kb_x or kb_y:
            resist = 0.18 if z["kind"] in ("boss", "titan") else (0.30 if z["kind"] in ("brute", "butcher", "queen") else 1.0)
            z["x"], z["y"] = _resolve_circle_obstacles(
                z["x"] + kb_x * resist, z["y"] + kb_y * resist, z["radius"], self._obstacles()
            )
        if emit_hit:
            self._emit("hit", x=round(z["x"], 1), y=round(z["y"], 1), dmg=int(round(dmg)), crit=(dmg >= 80))
        if z["hp"] > 0:
            return False

        # Zombie bị hạ gục
        self.total_kills += 1
        sv = self.survivors.get(owner_mark)
        if sv is not None:
            sv["kills"] += 1
            sv["money"] += z["reward"]
            sv["score"] += z["score"]
            vamp_lvl = sv["perks"].get("vamp", 0)
            if vamp_lvl > 0 and sv["alive"] and not sv["downed"]:
                sv["hp"] = min(sv["maxHp"], sv["hp"] + 4.0 * vamp_lvl)
        self._emit("kill", x=round(z["x"], 1), y=round(z["y"], 1), kind=z["kind"], owner=owner_mark)

        # Bloater phát nổ tạo vũng axit độc
        if z["kind"] == "bloater":
            self.hazards.append({
                "id": self._next_id(),
                "kind": "acid",
                "x": z["x"],
                "y": z["y"],
                "radius": 68.0,
                "ttl": 6.5,
                "dps": 18.0,
            })
            self._emit("acid", x=round(z["x"], 1), y=round(z["y"], 1), radius=68)

        # Rơi vật phẩm tiếp tế & Power-Up đặc biệt từ Tinh Anh / Mini-Boss / Boss
        if z["kind"] in ("brute", "butcher", "queen", "boss", "titan") or self.rng.random() < 0.16:
            pkind = self.rng.choices(["med", "ammo", "cash"], weights=[0.38, 0.37, 0.25], k=1)[0]
            self.pickups.append({
                "id": self._next_id(),
                "kind": pkind,
                "x": z["x"],
                "y": z["y"],
                "ttl": 18.0,
            })
            # Power-Up toàn đội (Double Damage / Infinite Ammo / Tactical Nuke)
            pu_chance = 1.0 if z["kind"] in ("boss", "titan") else (0.75 if z["kind"] in ("butcher", "queen") else (0.22 if z["kind"] == "brute" else 0.0))
            if pu_chance > 0 and self.rng.random() < pu_chance:
                pu_kind = self.rng.choices(["double_dmg", "inf_ammo", "nuke"], weights=[0.42, 0.38, 0.20], k=1)[0]
                self.pickups.append({
                    "id": self._next_id(),
                    "kind": pu_kind,
                    "x": _clamp(z["x"] + 28.0, 40.0, ARENA_W - 40.0),
                    "y": z["y"],
                    "ttl": 20.0,
                })
        return True

    def _detonate_barrel(self, b: dict, owner_mark: str) -> None:
        """Kích nổ thùng phuy nhiên liệu đỏ trên sân -> 230 DMG AoE + đốt cháy + làm choáng + nổ dây chuyền!"""
        if b.get("detonated"):
            return
        b["detonated"] = True
        b["hp"] = 0.0
        radius = 155.0
        bx, by = b["x"], b["y"]
        for z in list(self.zombies):
            if z["hp"] <= 0:
                continue
            d = _dist(bx, by, z["x"], z["y"])
            if d <= radius + z["radius"]:
                falloff = max(0.45, 1.0 - d / (radius + 45.0))
                ang = math.atan2(z["y"] - by, z["x"] - bx)
                killed = self._damage_zombie(z, 230.0 * falloff, owner_mark, math.cos(ang) * 34.0, math.sin(ang) * 34.0)
                if not killed:
                    z["burnTimer"] = max(z["burnTimer"], 4.0)
                    z["burnDps"] = max(z["burnDps"], 20.0)
                    z["burnOwner"] = owner_mark
                    if z["kind"] not in ("boss", "titan"):
                        z["stunTimer"] = max(z["stunTimer"], 1.2)
        self.zombies = [z for z in self.zombies if z["hp"] > 0]
        self._emit("boom", kind="barrel", x=round(bx, 1), y=round(by, 1), radius=int(radius))
        for other in list(self.barrels):
            if not other.get("detonated") and _dist(bx, by, other["x"], other["y"]) <= radius + other["r"]:
                self._detonate_barrel(other, owner_mark)

    def _fire_weapon(self, sv: dict, now: float) -> None:
        if not sv["alive"] or sv["downed"] or sv["reloadUntil"] > now or sv["fireCd"] > now:
            return
        wid = sv["weapon"]
        w = WEAPONS[wid]
        inf_ammo = self.inf_ammo_until > now
        cur_mag = sv["mag"].get(wid, 0)
        if not inf_ammo and cur_mag <= 0:
            self._trigger_reload(sv, now)
            return

        if not inf_ammo:
            sv["mag"][wid] = max(0, cur_mag - 1)
        stim_rate = 0.84 if sv.get("stimUntil", 0.0) > now else 1.0
        eff_rate = w["rate"] * stim_rate
        # Z5: Accumulator giữ phần dư thời gian giữa các tick 15 Hz để súng bắn nhanh (SMG/Flamer/Rifle) không bị hụt DPS
        sv["fireCd"] = max(sv["fireCd"], now - 0.08) + eff_rate
        cls_spec = CLASSES[sv["cls"]]
        w_lv = self._weapon_lv(sv, wid)
        lv_mult = 1.0 + 0.28 * (w_lv - 1)
        team_mult = 1.5 if self.double_dmg_until > now else 1.0
        dmg_mult = cls_spec["dmgMult"] * (1.0 + 0.20 * sv["perks"].get("damage", 0)) * lv_mult * team_mult
        per_dmg = w["dmg"] * dmg_mult
        obs = self._obstacles()
        base_angle = sv["aim"]
        muzzle_x = sv["x"] + math.cos(base_angle) * 20.0
        muzzle_y = sv["y"] + math.sin(base_angle) * 20.0
        tracer_color = "#e879f9" if w_lv >= 3 else ("#fef08a" if w_lv == 2 and wid == "smg" else w["color"])

        # Súng phóng lựu M79 bắn đạn nổ bay nhanh theo đường thẳng
        if w.get("splash", 0.0) > 0:
            dx, dy = math.cos(base_angle), math.sin(base_angle)
            self.projectiles.append({
                "id": self._next_id(),
                "kind": "rocket",
                "owner": sv["mark"],
                "x": muzzle_x,
                "y": muzzle_y,
                "vx": dx * 560.0,
                "vy": dy * 560.0,
                "dmg": per_dmg,
                "radius": w["splash"] + (w_lv - 1) * 14.0,
                "ttl": w["range"] / 560.0,
            })
            self._emit(
                "shot",
                mark=sv["mark"],
                weapon=wid,
                lv=w_lv,
                x=round(muzzle_x, 1),
                y=round(muzzle_y, 1),
                aim=round(base_angle, 3),
                pts=[(round(muzzle_x + dx * 36.0, 1), round(muzzle_y + dy * 36.0, 1))],
                color=tracer_color,
            )
            if not inf_ammo and sv["mag"][wid] <= 0:
                self._trigger_reload(sv, now)
            return

        # Súng Hồ Quang Tesla: bắn sét giật chuyền qua tối đa 4 mục tiêu + gây choáng nhẹ & làm chậm!
        if w.get("chain", 0) > 0:
            dx, dy = math.cos(base_angle), math.sin(base_angle)
            end_x = muzzle_x + dx * w["range"]
            end_y = muzzle_y + dy * w["range"]
            wall_t = 1.0
            for ob in obs:
                ht = _segment_hits_rect(muzzle_x, muzzle_y, end_x, end_y, ob)
                if ht is not None and ht < wall_t:
                    wall_t = ht
            end_x = muzzle_x + dx * w["range"] * wall_t
            end_y = muzzle_y + dy * w["range"] * wall_t

            # Kiểm tra trúng thùng phuy nổ dọc tia sét
            for b in list(self.barrels):
                if b["hp"] > 0 and _ray_circle_t(muzzle_x, muzzle_y, end_x, end_y, b["x"], b["y"], b["r"] + 6.0) is not None:
                    self._detonate_barrel(b, sv["mark"])
            self.barrels = [b for b in self.barrels if b["hp"] > 0]

            first_hit = None
            best_t = 2.0
            for z in self.zombies:
                if z["hp"] <= 0:
                    continue
                zt = _ray_circle_t(muzzle_x, muzzle_y, end_x, end_y, z["x"], z["y"], z["radius"] + 14.0)
                if zt is not None and zt < best_t:
                    best_t = zt
                    first_hit = z

            chain_pts: list[tuple[float, float]] = [(round(muzzle_x, 1), round(muzzle_y, 1))]
            hit_ids: set[int] = set()
            if first_hit is not None:
                cur = first_hit
                max_jumps = int(w["chain"]) + (w_lv - 1)
                for hop in range(max_jumps):
                    hit_ids.add(cur["id"])
                    chain_pts.append((round(cur["x"], 1), round(cur["y"], 1)))
                    hop_dmg = per_dmg * (0.85 ** hop)
                    killed = self._damage_zombie(cur, hop_dmg, sv["mark"], emit_hit=True)
                    if not killed:
                        cur["slowTimer"] = max(cur["slowTimer"], 1.8)
                        if cur["kind"] not in ("boss", "titan") and cur.get("teslaStunCd", 0.0) <= 0.0:
                            cur["stunTimer"] = max(cur["stunTimer"], 0.38)
                            cur["teslaStunCd"] = 1.35
                    # Tìm mục tiêu kế tiếp trong bán kính 190px
                    nxt = None
                    best_d = 190.0
                    for cand in self.zombies:
                        if cand["hp"] <= 0 or cand["id"] in hit_ids:
                            continue
                        cd = _dist(cur["x"], cur["y"], cand["x"], cand["y"])
                        if cd < best_d:
                            best_d = cd
                            nxt = cand
                    if nxt is None:
                        break
                    cur = nxt
                self.zombies = [z for z in self.zombies if z["hp"] > 0]
            else:
                chain_pts.append((round(end_x, 1), round(end_y, 1)))

            self._emit("chain", mark=sv["mark"], weapon=wid, lv=w_lv, pts=chain_pts, color=tracer_color)
            if not inf_ammo and sv["mag"][wid] <= 0:
                self._trigger_reload(sv, now)
            return

        tracers: list[tuple[float, float]] = []
        dead_ids: set[int] = set()
        agg_hits: dict[int, list] = {}

        for _ in range(w["pellets"]):
            ang = base_angle + self.rng.uniform(-w["spread"] * 0.5, w["spread"] * 0.5)
            dx = math.cos(ang)
            dy = math.sin(ang)
            end_x = muzzle_x + dx * w["range"]
            end_y = muzzle_y + dy * w["range"]

            wall_t = 1.0
            for ob in obs:
                ht = _segment_hits_rect(muzzle_x, muzzle_y, end_x, end_y, ob)
                if ht is not None and ht < wall_t:
                    wall_t = ht
            end_x = muzzle_x + dx * w["range"] * wall_t
            end_y = muzzle_y + dy * w["range"] * wall_t

            # Kiểm tra bắn trúng Thùng Phuy Nổ trên bản đồ
            barrel_hit_t = None
            for b in list(self.barrels):
                if b.get("detonated") or b["hp"] <= 0:
                    continue
                bt = _ray_circle_t(muzzle_x, muzzle_y, end_x, end_y, b["x"], b["y"], b["r"] + 5.0)
                if bt is not None:
                    barrel_hit_t = bt
                    b["hp"] -= per_dmg
                    if b["hp"] <= 0:
                        self._detonate_barrel(b, sv["mark"])
                    else:
                        self._emit("barrel_hit", x=round(b["x"], 1), y=round(b["y"], 1))
                    break

            hits: list[tuple[float, dict]] = []
            for z in self.zombies:
                if z["hp"] <= 0 or z["id"] in dead_ids:
                    continue
                zt = _ray_circle_t(muzzle_x, muzzle_y, end_x, end_y, z["x"], z["y"], z["radius"] + 4.0)
                if zt is not None:
                    hits.append((zt, z))
            hits.sort(key=lambda item: item[0])

            pierced = 0
            final_t = 1.0
            for zt, z in hits:
                pierced += 1
                final_t = zt
                kb = w["knockback"] * 0.16
                killed = self._damage_zombie(z, per_dmg, sv["mark"], dx * kb, dy * kb, emit_hit=False)
                entry = agg_hits.get(z["id"])
                if entry is None:
                    agg_hits[z["id"]] = [z["x"], z["y"], per_dmg]
                else:
                    entry[0], entry[1] = z["x"], z["y"]
                    entry[2] += per_dmg
                if w["burn"] > 0 and not killed:
                    z["burnTimer"] = 3.2
                    z["burnDps"] = max(z["burnDps"], w["burn"] * dmg_mult)
                    z["burnOwner"] = sv["mark"]
                if killed:
                    dead_ids.add(z["id"])
                if pierced >= w["pierce"]:
                    break

            stop_t = final_t if pierced >= w["pierce"] else (barrel_hit_t if (barrel_hit_t is not None and pierced == 0) else 1.0)
            tx = muzzle_x + (end_x - muzzle_x) * stop_t
            ty = muzzle_y + (end_y - muzzle_y) * stop_t
            tracers.append((round(tx, 1), round(ty, 1)))

        for hx, hy, total_dmg in agg_hits.values():
            self._emit("hit", x=round(hx, 1), y=round(hy, 1), dmg=int(round(total_dmg)), crit=(total_dmg >= 80))

        self.barrels = [b for b in self.barrels if b["hp"] > 0]
        if dead_ids:
            self.zombies = [z for z in self.zombies if z["hp"] > 0]

        self._emit(
            "shot",
            mark=sv["mark"],
            weapon=wid,
            lv=w_lv,
            x=round(muzzle_x, 1),
            y=round(muzzle_y, 1),
            aim=round(base_angle, 3),
            pts=tracers[:5],
            color=tracer_color,
        )
        if not inf_ammo and sv["mag"][wid] <= 0:
            self._trigger_reload(sv, now)

    def _throw_grenade(self, sv: dict, target_x: float, target_y: float, kind: str = "grenade") -> None:
        if not sv["alive"] or sv["downed"]:
            return
        field = "grenades" if kind == "grenade" else ("cryos" if kind == "cryo" else "emps")
        if sv.get(field, 0) <= 0:
            return
        sv[field] -= 1
        dx = target_x - sv["x"]
        dy = target_y - sv["y"]
        d = math.hypot(dx, dy)
        max_throw = 390.0
        if d > max_throw and d > 1e-6:
            target_x = sv["x"] + (dx / d) * max_throw
            target_y = sv["y"] + (dy / d) * max_throw
        target_x = _clamp(target_x, 30.0, ARENA_W - 30.0)
        target_y = _clamp(target_y, 30.0, ARENA_H - 30.0)
        radius = 135.0 if kind == "grenade" else (145.0 if kind == "cryo" else 155.0)
        dmg = (195.0 if kind == "grenade" else (55.0 if kind == "cryo" else 45.0)) * (1.0 + 0.18 * sv["perks"].get("damage", 0))
        self.projectiles.append({
            "id": self._next_id(),
            "kind": kind,
            "owner": sv["mark"],
            "x": sv["x"],
            "y": sv["y"],
            "sx": sv["x"],
            "sy": sv["y"],
            "tx": target_x,
            "ty": target_y,
            "t": 0.0,
            "dur": 0.56,
            "radius": radius,
            "dmg": dmg,
        })

    def _deploy_mine(self, sv: dict) -> None:
        if not sv["alive"] or sv["downed"] or sv.get("mines", 0) <= 0:
            return
        if len(self.mines) >= 6:
            raise GameError("Đã đạt tối đa 6 mìn trên bản đồ.")
        sv["mines"] -= 1
        mx, my = _resolve_circle_obstacles(sv["x"], sv["y"], 14.0, self._obstacles())
        self.mines.append({
            "id": self._next_id(),
            "owner": sv["mark"],
            "x": mx,
            "y": my,
            "triggerR": 55.0,
            "radius": 118.0,
            "dmg": 220.0 * (1.0 + 0.18 * sv["perks"].get("damage", 0)),
        })
        self._emit("mine_set", x=round(mx, 1), y=round(my, 1), owner=sv["mark"])

    def _deploy_turret(self, sv: dict) -> None:
        if not sv["alive"] or sv["downed"] or sv["turrets"] <= 0:
            return
        if len(self.turrets) >= 8:
            raise GameError("Đã đạt tối đa 8 trụ súng trên bản đồ.")
        sv["turrets"] -= 1
        cls_mult = CLASSES[sv["cls"]]["turretMult"]
        tx = sv["x"] + math.cos(sv["aim"]) * 36.0
        ty = sv["y"] + math.sin(sv["aim"]) * 36.0
        tx, ty = _resolve_circle_obstacles(tx, ty, 16.0, self._obstacles())
        max_hp = round(180.0 * cls_mult, 1)
        self.turrets.append({
            "id": self._next_id(),
            "owner": sv["mark"],
            "x": tx,
            "y": ty,
            "aim": sv["aim"],
            "hp": max_hp,
            "maxHp": max_hp,
            "ammo": int(round(90 * cls_mult)),
            "maxAmmo": int(round(90 * cls_mult)),
            "dmg": 20.0 * cls_mult,
            "rate": 0.24 / cls_mult,
            "range": 380.0,
            "fireCd": 0.0,
        })
        self._emit("turret", x=round(tx, 1), y=round(ty, 1), owner=sv["mark"])

    def _do_dash(self, sv: dict, now: float) -> None:
        if not sv["alive"] or sv["downed"] or sv["dashCd"] > now:
            return
        dx, dy = sv["vx"], sv["vy"]
        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            dx, dy = math.cos(sv["aim"]), math.sin(sv["aim"])
        mag = math.hypot(dx, dy) or 1.0
        sv["dashVx"] = (dx / mag) * 690.0
        sv["dashVy"] = (dy / mag) * 690.0
        sv["dashUntil"] = now + 0.22
        sv["dashCd"] = now + CLASSES[sv["cls"]]["dashCd"]
        self._emit("dash", mark=sv["mark"], x=round(sv["x"], 1), y=round(sv["y"], 1))

    def _damage_survivor(
        self,
        sv: dict,
        dmg: float,
        now: float,
        sx: float | None = None,
        sy: float | None = None,
        kind: str = "melee",
    ) -> None:
        if not sv["alive"] or sv["downed"] or sv["dashUntil"] > now or dmg <= 0:
            return
        total_dmg = dmg
        shield_dmg = 0.0
        if sv["armor"] > 0:
            absorbed = min(sv["armor"], dmg * 0.65)
            sv["armor"] = max(0.0, sv["armor"] - absorbed)
            shield_dmg = absorbed
            dmg -= absorbed
        sv["hp"] -= dmg
        # Phát sự kiện hurt để client vẽ vết cào, nháy viền máu đỏ & âm thanh bị đánh
        if kind != "acid" or total_dmg >= 1.2:
            self._emit(
                "hurt",
                mark=sv["mark"],
                dmg=max(1, int(round(total_dmg))),
                shieldDmg=int(round(shield_dmg)),
                x=round(sv["x"], 1),
                y=round(sv["y"], 1),
                sx=round(sx, 1) if sx is not None else round(sv["x"], 1),
                sy=round(sy, 1) if sy is not None else round(sv["y"], 1),
                kind=kind,
            )
        if sv["hp"] <= 0:
            sv["hp"] = 0.0
            sv["firing"] = False
            others_standing = any(
                m != sv["mark"] and o["alive"] and not o["downed"]
                for m, o in self.survivors.items()
            )
            if others_standing:
                sv["downed"] = True
                sv["bleedout"] = BLEEDOUT_SECONDS
                sv["reviveProg"] = 0.0
                p = self.seat(sv["mark"])
                self.system(f"🆘 {p.name if p else sv['mark']} đã gục ngã! Chạy lại gần để cứu trong {int(BLEEDOUT_SECONDS)}s!")
                self._emit("downed", mark=sv["mark"], x=round(sv["x"], 1), y=round(sv["y"], 1))
            else:
                sv["alive"] = False
                sv["downed"] = False

    # ---- Mua sắm trong Armory Shop (Chỉ mở khi đang chờ đợt tiếp theo!) ---- #
    def _buy_item(self, sv: dict, item: str) -> None:
        if self.phase != "shop":
            raise GameError("Trạm Tiếp Tế chỉ mở mua đồ trong thời gian chờ đợt tiếp theo!")
        now = time.time()

        # Nâng cấp vũ khí (upgrade:rifle -> Mk.II / Mk.III)
        if item.startswith("upgrade:"):
            wid = item.split(":", 1)[1].strip()
            if wid not in WEAPONS or wid not in sv["weapons"]:
                raise GameError("Bạn chưa sở hữu vũ khí này.")
            cur_lv = self._weapon_lv(sv, wid)
            if cur_lv >= MAX_WEAPON_LV:
                raise GameError(f"{WEAPONS[wid]['name']} đã đạt cấp tối đa Mk.{MAX_WEAPON_LV}.")
            cost = self._weapon_upgrade_cost(wid, cur_lv)
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost} để nâng cấp {WEAPONS[wid]['name']} lên Mk.{cur_lv + 1}.")
            sv["money"] -= cost
            sv["weaponLv"][wid] = cur_lv + 1
            sv["mag"][wid] = self._weapon_mag_cap(sv, wid)
            if WEAPONS[wid]["reserve"] != -1:
                sv["reserve"][wid] = WEAPONS[wid]["reserve"]
            if sv["weapon"] == wid:
                sv["reloadUntil"] = 0.0
            self._emit("upgrade", mark=sv["mark"], weapon=wid, lv=cur_lv + 1, x=round(sv["x"], 1), y=round(sv["y"], 1))
            return

        if item in WEAPONS:
            w = WEAPONS[item]
            if item in sv["weapons"]:
                refill_cost = max(80, w["cost"] // 3)
                if sv["money"] < refill_cost:
                    raise GameError(f"Cần ${refill_cost} để nạp đầy đạn {w['name']}.")
                sv["money"] -= refill_cost
                sv["mag"][item] = self._weapon_mag_cap(sv, item)
                sv["reserve"][item] = w["reserve"]
                if sv["weapon"] == item:
                    sv["reloadUntil"] = 0.0
                return
            if sv["money"] < w["cost"]:
                raise GameError(f"Không đủ tiền (cần ${w['cost']}).")
            sv["money"] -= w["cost"]
            sv["weapons"].append(item)
            sv["weaponLv"][item] = 1
            sv["mag"][item] = self._weapon_mag_cap(sv, item)
            sv["reserve"][item] = w["reserve"]
            sv["weapon"] = item
            sv["reloadUntil"] = 0.0
            return

        if item in PERKS:
            spec = PERKS[item]
            cur = sv["perks"].get(item, 0)
            if cur >= spec["max"]:
                raise GameError("Kỹ năng này đã đạt cấp tối đa.")
            cost = spec["cost"] + cur * 110
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost} để nâng cấp {spec['name']}.")
            sv["money"] -= cost
            sv["perks"][item] = cur + 1
            if item == "armor":
                sv["maxHp"] += 30.0
                sv["hp"] = min(sv["maxHp"], sv["hp"] + 30.0)
                sv["maxArmor"] += 20.0
                sv["armor"] = min(sv["maxArmor"], sv["armor"] + 45.0)
            elif item == "reload":
                wid = sv["weapon"]
                sv["mag"][wid] = self._weapon_mag_cap(sv, wid)
                sv["reloadUntil"] = 0.0
            return

        if item == "medkit":
            cost = SHOP_ITEMS["medkit"]["cost"]
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["hp"] = min(sv["maxHp"], sv["hp"] + 65.0)
            sv["armor"] = min(sv["maxArmor"], sv["armor"] + 30.0)
            return

        if item == "shield":
            cost = SHOP_ITEMS["shield"]["cost"]
            if sv["armor"] >= sv["maxArmor"] - 0.5:
                raise GameError("Giáp (Shield) đã đầy 100%.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["armor"] = sv["maxArmor"]
            return

        if item == "ammo":
            cost = SHOP_ITEMS["ammo"]["cost"]
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            for wid in sv["weapons"]:
                sv["mag"][wid] = self._weapon_mag_cap(sv, wid)
                if WEAPONS[wid]["reserve"] != -1:
                    sv["reserve"][wid] = WEAPONS[wid]["reserve"]
            sv["reloadUntil"] = 0.0
            return

        if item == "grenade":
            cost = SHOP_ITEMS["grenade"]["cost"]
            if sv["grenades"] >= 5:
                raise GameError("Đã mang tối đa 5 lựu đạn nổ.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["grenades"] = min(5, sv["grenades"] + 2)
            return

        if item == "cryo":
            cost = SHOP_ITEMS["cryo"]["cost"]
            if sv.get("cryos", 0) >= 5:
                raise GameError("Đã mang tối đa 5 lựu đạn băng.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["cryos"] = min(5, sv.get("cryos", 0) + 2)
            return

        if item == "emp":
            cost = SHOP_ITEMS["emp"]["cost"]
            if sv.get("emps", 0) >= 5:
                raise GameError("Đã mang tối đa 5 lựu đạn EMP.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["emps"] = min(5, sv.get("emps", 0) + 2)
            return

        if item == "mine":
            cost = SHOP_ITEMS["mine"]["cost"]
            if sv.get("mines", 0) >= 4:
                raise GameError("Đã mang tối đa 4 mìn từ trường.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["mines"] = min(4, sv.get("mines", 0) + 2)
            return

        if item == "turret":
            cost = SHOP_ITEMS["turret"]["cost"]
            if sv["turrets"] >= 3:
                raise GameError("Đã mang tối đa 3 trụ súng.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["turrets"] += 1
            return

        if item == "repair":
            cost = SHOP_ITEMS["repair"]["cost"]
            my_turrets = [t for t in self.turrets if t["owner"] == sv["mark"]]
            if not my_turrets:
                raise GameError("Bạn chưa có trụ súng nào trên sân để sửa.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            for t in my_turrets:
                t["hp"] = t["maxHp"]
                t["ammo"] = t["maxAmmo"]
            return

        if item == "stim":
            cost = SHOP_ITEMS["stim"]["cost"]
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["hp"] = min(sv["maxHp"], sv["hp"] + 40.0)
            sv["dashCd"] = 0.0
            sv["stimUntil"] = max(sv.get("stimUntil", 0.0), now) + 20.0
            self._emit("stim", mark=sv["mark"], x=round(sv["x"], 1), y=round(sv["y"], 1))
            return

        raise GameError("Vật phẩm không tồn tại.")

    def _step_survivors_and_pickups(self, dt: float, now: float, obs: list[dict], allow_fire: bool) -> None:
        """Cập nhật di chuyển, thay đạn, hào quang Medic, cứu đồng đội & nhặt đồ (chạy cả trong pha Shop và Wave!)."""
        for m, sv in self.survivors.items():
            if not sv["alive"]:
                sv["moveVx"], sv["moveVy"] = 0.0, 0.0
                continue
            if sv["downed"]:
                sv["moveVx"], sv["moveVy"] = 0.0, 0.0
                if not allow_fire:
                    continue
                sv["bleedout"] -= dt
                rescuers = [
                    o for om, o in self.survivors.items()
                    if om != m and o["alive"] and not o["downed"]
                    and _dist(sv["x"], sv["y"], o["x"], o["y"]) <= REVIVE_RADIUS
                ]
                if rescuers:
                    best_rate = max(CLASSES[o["cls"]]["reviveSpeed"] for o in rescuers)
                    sv["reviveProg"] += (dt * best_rate) / REVIVE_SECONDS
                    if sv["reviveProg"] >= 1.0:
                        sv["downed"] = False
                        sv["bleedout"] = 0.0
                        sv["reviveProg"] = 0.0
                        sv["hp"] = round(sv["maxHp"] * 0.45, 1)
                        sv["armor"] = min(sv["maxArmor"], max(sv["armor"], 20.0))
                        helper = rescuers[0]
                        helper["revives"] += 1
                        helper["money"] += 85
                        helper["score"] += 250
                        p_saved = self.seat(m)
                        p_help = self.seat(helper["mark"])
                        self.system(f"💚 {p_help.name if p_help else helper['mark']} đã cứu sống {p_saved.name if p_saved else m}!")
                        self._emit("revive", mark=m, by=helper["mark"], x=round(sv["x"], 1), y=round(sv["y"], 1))
                else:
                    sv["reviveProg"] = max(0.0, sv["reviveProg"] - dt * 0.35)
                if sv["downed"] and sv["bleedout"] <= 0:
                    sv["downed"] = False
                    sv["alive"] = False
                    p = self.seat(m)
                    self.system(f"💀 {p.name if p else m} đã hy sinh (sẽ hồi sinh ở đợt tiếp theo).")
                continue

            # Hoàn thành thay đạn
            if sv["reloadUntil"] > 0 and now >= sv["reloadUntil"]:
                wid = sv["weapon"]
                cap = self._weapon_mag_cap(sv, wid)
                w = WEAPONS[wid]
                if w["reserve"] == -1:
                    sv["mag"][wid] = cap
                else:
                    need = cap - sv["mag"].get(wid, 0)
                    take = min(need, sv["reserve"].get(wid, 0))
                    sv["mag"][wid] = sv["mag"].get(wid, 0) + take
                    sv["reserve"][wid] = sv["reserve"].get(wid, 0) - take
                sv["reloadUntil"] = 0.0

            # Di chuyển (Dash hoặc đi bộ — hoạt động mượt mà cả khi đang chờ Wave sau!)
            if sv["dashUntil"] > now:
                mvx, mvy = sv["dashVx"], sv["dashVy"]
                nx = sv["x"] + mvx * dt
                ny = sv["y"] + mvy * dt
            else:
                spd = CLASSES[sv["cls"]]["speed"] * (1.0 + 0.12 * sv["perks"].get("speed", 0))
                if sv.get("stimUntil", 0.0) > now:
                    spd *= 1.25
                in_acid = any(
                    h.get("kind", "acid") == "acid" and _dist(sv["x"], sv["y"], h["x"], h["y"]) <= h["radius"]
                    for h in self.hazards
                )
                if in_acid:
                    spd *= 0.62
                vx, vy = sv["vx"], sv["vy"]
                mag = math.hypot(vx, vy)
                if mag > 1.0:
                    vx, vy = vx / mag, vy / mag
                mvx, mvy = vx * spd, vy * spd
                nx = sv["x"] + mvx * dt
                ny = sv["y"] + mvy * dt
            sv["moveVx"], sv["moveVy"] = mvx, mvy
            sv["x"], sv["y"] = _resolve_circle_obstacles(nx, ny, PLAYER_RADIUS, obs)

            # Hào quang Quân Y (Medic) hồi máu nhẹ cho đồng đội gần
            aura = CLASSES[sv["cls"]]["healAura"]
            if aura > 0:
                for om, other in self.survivors.items():
                    if other["alive"] and not other["downed"] and _dist(sv["x"], sv["y"], other["x"], other["y"]) <= 140.0:
                        other["hp"] = min(other["maxHp"], other["hp"] + aura * dt)

            if allow_fire and sv["firing"]:
                for _ in range(2):
                    if not sv["alive"] or sv["downed"] or sv["reloadUntil"] > now or sv["fireCd"] > now:
                        break
                    prev_cd = sv["fireCd"]
                    self._fire_weapon(sv, now)
                    if sv["fireCd"] <= prev_cd:
                        break

        # Cập nhật Vật phẩm rơi & Power-Up toàn đội (nhặt được cả trong pha Shop và Wave!)
        next_pickups: list[dict] = []
        for pk in self.pickups:
            pk["ttl"] -= dt
            if pk["ttl"] <= 0:
                continue
            taken = False
            for sv in self.survivors.values():
                if not sv["alive"] or sv["downed"]:
                    continue
                if _dist(sv["x"], sv["y"], pk["x"], pk["y"]) <= PLAYER_RADIUS + 22.0:
                    kind = pk["kind"]
                    if kind == "med":
                        sv["hp"] = min(sv["maxHp"], sv["hp"] + 32.0)
                    elif kind == "ammo":
                        wid = sv["weapon"]
                        if WEAPONS[wid]["reserve"] != -1:
                            max_res = WEAPONS[wid]["reserve"] * 2
                            sv["reserve"][wid] = min(max_res, sv["reserve"].get(wid, 0) + WEAPONS[wid]["mag"] * 2)
                    elif kind == "cash":
                        sv["money"] += 75
                    elif kind == "double_dmg":
                        self.double_dmg_until = max(self.double_dmg_until, now) + 12.0
                        self.system("🔥 POWER-UP: CUỒNG SÁT (+50% Sát thương toàn đội trong 12s)!")
                    elif kind == "inf_ammo":
                        self.inf_ammo_until = max(self.inf_ammo_until, now) + 10.0
                        for o in self.survivors.values():
                            ow = o["weapon"]
                            o["mag"][ow] = self._weapon_mag_cap(o, ow)
                            o["reloadUntil"] = 0.0
                        self.system("♾️ POWER-UP: VÔ HẠN ĐẠN (Toàn đội bắn không tốn đạn 10s)!")
                    elif kind == "nuke":
                        for z in list(self.zombies):
                            if z["hp"] <= 0:
                                continue
                            killed = self._damage_zombie(z, 350.0, sv["mark"], emit_hit=False)
                            if not killed and z["kind"] not in ("boss", "titan"):
                                z["stunTimer"] = max(z["stunTimer"], 2.0)
                        self.zombies = [z for z in self.zombies if z["hp"] > 0]
                        self._emit("nuke", x=round(pk["x"], 1), y=round(pk["y"], 1))
                        self.system("☢️ POWER-UP: BOM HẠT NHÂN CHIẾN THUẬT — Quét sạch 350 sát thương toàn bản đồ!")
                    self._emit("pickup", mark=sv["mark"], kind=kind, x=round(pk["x"], 1), y=round(pk["y"], 1))
                    taken = True
                    break
            if not taken:
                next_pickups.append(pk)
        self.pickups = next_pickups

    @staticmethod
    def _predict_target_pos(
        zx: float, zy: float, sv: dict, proj_speed: float, lead_factor: float = 0.72
    ) -> tuple[float, float]:
        """Dự đoán vị trí đón đầu mục tiêu đang di chuyển để Spitter/Boss ngắm chuẩn hơn."""
        d = _dist(zx, zy, sv["x"], sv["y"])
        lead_t = min(0.55, d / max(120.0, proj_speed)) * lead_factor
        px = _clamp(sv["x"] + sv.get("moveVx", 0.0) * lead_t, 36.0, ARENA_W - 36.0)
        py = _clamp(sv["y"] + sv.get("moveVy", 0.0) * lead_t, 36.0, ARENA_H - 36.0)
        return px, py

    def _choose_zombie_target(self, z: dict, standing: list[dict], downed: list[dict]) -> dict:
        """Chọn mục tiêu chiến thuật thay vì cả đàn cùng bám duy nhất 1 người gần nhất."""
        if len(standing) == 1:
            return standing[0]
        kind = z["kind"]
        zid = z["id"]

        def _score(sv: dict) -> float:
            d = _dist(z["x"], z["y"], sv["x"], sv["y"])
            mult = 1.0
            # Ưu tiên kết liễu người thấp máu (đặc biệt Runner / Butcher)
            hp_ratio = sv["hp"] / max(1.0, sv["maxHp"])
            if hp_ratio < 0.45:
                mult *= 0.76 if kind in ("runner", "butcher") else 0.86
            # Phá rối đồng đội đang chạy lại cứu người gục ngã!
            if downed and any(_dist(sv["x"], sv["y"], dn["x"], dn["y"]) < 130.0 for dn in downed):
                mult *= 0.80
            # Săn người bị tách đàn / cô lập để tránh bị tập trung hỏa lực
            nearby_mates = sum(
                1 for o in standing
                if o is not sv and _dist(sv["x"], sv["y"], o["x"], o["y"]) < 210.0
            )
            if nearby_mates == 0 and kind in ("runner", "butcher", "brute"):
                mult *= 0.84
            elif nearby_mates >= 2 and kind in ("bloater", "spitter", "queen"):
                # Quái nổ độc / phun axit thích đánh vào cụm đông người
                mult *= 0.85
            # Phân tán nhẹ theo ID để đàn quái tự chia mũi tấn công trên nhiều người chơi
            try:
                mark_idx = int(sv["mark"])
            except (TypeError, ValueError):
                mark_idx = 0
            if (zid + mark_idx) % len(standing) == 0:
                mult *= 0.86
            return d * mult

        return min(standing, key=_score)

    # ---- Vòng lặp mô phỏng 15 Hz (Server Authoritative Tick) --------------- #
    def tick(self, dt_override: float | None = None) -> bool:
        if not self.in_progress():
            return False
        now = time.time()
        dt = dt_override if dt_override is not None else min(0.12, max(0.01, now - self.last_tick_at))
        self.last_tick_at = now
        obs = self._obstacles()

        if self.phase == "shop":
            # AI Bots tự mua đồ ở đầu pha shop & người chơi VẪN DI CHUYỂN TỰ DO, nhặt đồ, đặt trụ/mìn!
            self._step_bots(dt, now)
            self._step_survivors_and_pickups(dt, now, obs, allow_fire=False)
            humans = [
                m for m in self.survivors
                if (p := self.seat(m)) is not None and not p.bot and p.connected
            ]
            all_ready = bool(humans) and all(self.survivors[m]["readyShop"] for m in humans)
            if all_ready or now >= self.shop_deadline:
                self._begin_wave(self.wave + 1)
            return True

        if self.phase != "wave":
            return False

        # 1. Step AI Survivor Bots
        self._step_bots(dt, now)

        # 2. Cập nhật vị trí chiến binh, thay đạn, hào quang Medic, cứu đồng đội & nhặt đồ
        self._step_survivors_and_pickups(dt, now, obs, allow_fire=True)

        # 3. Sinh thêm Zombie từ hàng đợi đợt hiện tại (scale mật độ & nhịp sinh theo số người chơi)
        sc = self._squad_scale()
        n_players = int(sc["n_players"])
        max_active = min(68, 12 + self.wave * 2 + n_players * 6)
        if self.wave_remaining_to_spawn and len(self.zombies) < max_active:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                burst = 2 if (n_players >= 4 and len(self.wave_remaining_to_spawn) >= 2 and len(self.zombies) + 1 < max_active) else 1
                for _ in range(burst):
                    kind = self.wave_remaining_to_spawn.pop(0)
                    self._spawn_one_zombie(kind)
                base_interval = max(0.28, 1.05 - self.wave * 0.05)
                self.spawn_timer = max(0.14, base_interval / sc["spawn_rate_mult"])

        # 4. Cập nhật Trụ súng Sentry tự động (có HP & đạn)
        next_turrets: list[dict] = []
        for t in self.turrets:
            if t["hp"] <= 0:
                self._emit("turret_boom", x=round(t["x"], 1), y=round(t["y"], 1))
                continue
            if t["ammo"] <= 0:
                continue
            next_turrets.append(t)
            if t["fireCd"] > now or not self.zombies:
                continue
            target_z = None
            best_d = t["range"]
            for z in self.zombies:
                if z["hp"] <= 0:
                    continue
                d = _dist(t["x"], t["y"], z["x"], z["y"])
                if d < best_d:
                    blocked = any(_segment_hits_rect(t["x"], t["y"], z["x"], z["y"], ob) is not None for ob in obs)
                    if not blocked:
                        best_d = d
                        target_z = z
            if target_z is not None:
                t["aim"] = math.atan2(target_z["y"] - t["y"], target_z["x"] - t["x"])
                t["fireCd"] = max(t["fireCd"], now - 0.08) + t["rate"]
                t["ammo"] -= 1
                self._damage_zombie(target_z, t["dmg"], t["owner"])
                self._emit(
                    "shot",
                    mark=t["owner"],
                    weapon="turret",
                    x=round(t["x"], 1),
                    y=round(t["y"], 1),
                    aim=round(t["aim"], 3),
                    pts=[(round(target_z["x"], 1), round(target_z["y"], 1))],
                    color="#34d399",
                )
        self.turrets = next_turrets
        self.zombies = [z for z in self.zombies if z["hp"] > 0]

        # 4b. Cập nhật Mìn Từ Trường (Proximity Laser Mines)
        next_mines: list[dict] = []
        for mn in self.mines:
            triggered = any(
                z["hp"] > 0 and _dist(mn["x"], mn["y"], z["x"], z["y"]) <= mn["triggerR"] + z["radius"]
                for z in self.zombies
            )
            if triggered:
                for b in list(self.barrels):
                    if not b.get("detonated") and _dist(mn["x"], mn["y"], b["x"], b["y"]) <= mn["radius"] + b["r"]:
                        self._detonate_barrel(b, mn["owner"])
                self.barrels = [b for b in self.barrels if b["hp"] > 0]
                for z in list(self.zombies):
                    if z["hp"] <= 0:
                        continue
                    d = _dist(mn["x"], mn["y"], z["x"], z["y"])
                    if d <= mn["radius"] + z["radius"]:
                        falloff = max(0.45, 1.0 - d / (mn["radius"] + 35.0))
                        ang = math.atan2(z["y"] - mn["y"], z["x"] - mn["x"])
                        killed = self._damage_zombie(z, mn["dmg"] * falloff, mn["owner"], math.cos(ang) * 28.0, math.sin(ang) * 28.0)
                        if not killed:
                            if z["kind"] in ("boss", "titan"):
                                z["slowTimer"] = max(z["slowTimer"], 2.0)
                            else:
                                z["stunTimer"] = max(z["stunTimer"], 1.5)
                self.zombies = [z for z in self.zombies if z["hp"] > 0]
                self._emit("boom", x=round(mn["x"], 1), y=round(mn["y"], 1), radius=int(mn["radius"]))
            else:
                next_mines.append(mn)
        self.mines = next_mines

        # 5. Cập nhật Đạn bay (Lựu đạn nổ/Băng/EMP, Đạn M79 Rocket & Cầu axit Spitter/Boss)
        next_proj: list[dict] = []
        for pr in self.projectiles:
            if pr["kind"] in ("grenade", "cryo", "emp"):
                pr["t"] += dt
                ratio = min(1.0, pr["t"] / pr["dur"])
                pr["x"] = pr["sx"] + (pr["tx"] - pr["sx"]) * ratio
                pr["y"] = pr["sy"] + (pr["ty"] - pr["sy"]) * ratio
                if ratio >= 1.0:
                    if pr["kind"] == "grenade":
                        for b in list(self.barrels):
                            if b["hp"] > 0 and _dist(pr["x"], pr["y"], b["x"], b["y"]) <= pr["radius"] + b["r"]:
                                self._detonate_barrel(b, pr["owner"])
                        self.barrels = [b for b in self.barrels if b["hp"] > 0]
                        for z in list(self.zombies):
                            d = _dist(pr["x"], pr["y"], z["x"], z["y"])
                            if d <= pr["radius"] + z["radius"]:
                                falloff = max(0.35, 1.0 - d / (pr["radius"] + 40.0))
                                ang = math.atan2(z["y"] - pr["y"], z["x"] - pr["x"])
                                self._damage_zombie(z, pr["dmg"] * falloff, pr["owner"], math.cos(ang) * 28.0, math.sin(ang) * 28.0)
                        self._emit("boom", x=round(pr["x"], 1), y=round(pr["y"], 1), radius=int(pr["radius"]))
                    elif pr["kind"] == "cryo":
                        # Lựu đạn băng tạo vùng bão tuyết làm chậm 65% trong 5.5s
                        self.hazards.append({
                            "id": self._next_id(),
                            "kind": "cryo",
                            "owner": pr["owner"],
                            "x": pr["x"],
                            "y": pr["y"],
                            "radius": pr["radius"],
                            "ttl": 5.5,
                            "dps": 14.0,
                        })
                        for z in list(self.zombies):
                            if _dist(pr["x"], pr["y"], z["x"], z["y"]) <= pr["radius"] + z["radius"]:
                                killed = self._damage_zombie(z, pr["dmg"], pr["owner"])
                                if not killed:
                                    z["slowTimer"] = max(z["slowTimer"], 4.0)
                        self._emit("cryo", x=round(pr["x"], 1), y=round(pr["y"], 1), radius=int(pr["radius"]))
                    else:
                        # Lựu đạn EMP làm choáng Stun 2.8s toàn bộ quái & ngắt chiêu Boss!
                        for z in list(self.zombies):
                            if _dist(pr["x"], pr["y"], z["x"], z["y"]) <= pr["radius"] + z["radius"]:
                                killed = self._damage_zombie(z, pr["dmg"], pr["owner"])
                                if not killed:
                                    z["chargeTimer"] = 0.0
                                    if z["kind"] in ("boss", "titan"):
                                        z["slowTimer"] = max(z["slowTimer"], 3.5)
                                        z["stunTimer"] = max(z["stunTimer"], 0.9)
                                    else:
                                        z["stunTimer"] = max(z["stunTimer"], 2.8)
                        self._emit("emp", x=round(pr["x"], 1), y=round(pr["y"], 1), radius=int(pr["radius"]))
                    self.zombies = [z for z in self.zombies if z["hp"] > 0]
                else:
                    next_proj.append(pr)
            elif pr["kind"] == "rocket":
                pr["x"] += pr["vx"] * dt
                pr["y"] += pr["vy"] * dt
                pr["ttl"] -= dt
                hit_wall = any(
                    ob["x"] <= pr["x"] <= ob["x"] + ob["w"] and ob["y"] <= pr["y"] <= ob["y"] + ob["h"]
                    for ob in obs
                )
                hit_z = any(
                    z["hp"] > 0 and _dist(pr["x"], pr["y"], z["x"], z["y"]) <= z["radius"] + 9.0
                    for z in self.zombies
                )
                hit_b = any(
                    b["hp"] > 0 and _dist(pr["x"], pr["y"], b["x"], b["y"]) <= b["r"] + 8.0
                    for b in self.barrels
                )
                out_bounds = not (0 <= pr["x"] <= ARENA_W and 0 <= pr["y"] <= ARENA_H)
                if pr["ttl"] <= 0 or hit_wall or hit_z or hit_b or out_bounds:
                    for b in list(self.barrels):
                        if b["hp"] > 0 and _dist(pr["x"], pr["y"], b["x"], b["y"]) <= pr["radius"] + b["r"]:
                            self._detonate_barrel(b, pr["owner"])
                    self.barrels = [b for b in self.barrels if b["hp"] > 0]
                    for z in list(self.zombies):
                        d = _dist(pr["x"], pr["y"], z["x"], z["y"])
                        if d <= pr["radius"] + z["radius"]:
                            falloff = max(0.4, 1.0 - d / (pr["radius"] + 36.0))
                            ang = math.atan2(z["y"] - pr["y"], z["x"] - pr["x"])
                            self._damage_zombie(z, pr["dmg"] * falloff, pr["owner"], math.cos(ang) * 24.0, math.sin(ang) * 24.0)
                    self.zombies = [z for z in self.zombies if z["hp"] > 0]
                    self._emit("boom", x=round(pr["x"], 1), y=round(pr["y"], 1), radius=int(pr["radius"]))
                else:
                    next_proj.append(pr)
            else:
                # Đạn axit Spitter / Queen / Boss / Titan
                pr["x"] += pr["vx"] * dt
                pr["y"] += pr["vy"] * dt
                pr["ttl"] -= dt
                hit_wall = any(
                    ob["x"] <= pr["x"] <= ob["x"] + ob["w"] and ob["y"] <= pr["y"] <= ob["y"] + ob["h"]
                    for ob in obs
                )
                if pr["ttl"] <= 0 or hit_wall or not (0 <= pr["x"] <= ARENA_W and 0 <= pr["y"] <= ARENA_H):
                    if pr.get("spawnAcid") and not hit_wall and 10 <= pr["x"] <= ARENA_W - 10 and 10 <= pr["y"] <= ARENA_H - 10:
                        self.hazards.append({
                            "id": self._next_id(),
                            "kind": "acid",
                            "x": pr["x"],
                            "y": pr["y"],
                            "radius": 52.0,
                            "ttl": 5.0,
                            "dps": 15.0,
                        })
                    continue
                hit_something = False
                for sv in self.survivors.values():
                    if sv["alive"] and not sv["downed"] and _dist(pr["x"], pr["y"], sv["x"], sv["y"]) <= PLAYER_RADIUS + 7.0:
                        self._damage_survivor(sv, pr["dmg"], now, sx=pr["x"], sy=pr["y"], kind="projectile")
                        hit_something = True
                        break
                if not hit_something:
                    for t in self.turrets:
                        if t["hp"] > 0 and _dist(pr["x"], pr["y"], t["x"], t["y"]) <= 18.0:
                            t["hp"] = max(0.0, t["hp"] - pr["dmg"])
                            hit_something = True
                            break
                if not hit_something:
                    next_proj.append(pr)
        self.projectiles = next_proj

        # 5b. Cập nhật Vòng Cảnh Báo Chiêu Boss / Mini-Boss (Telegraph Danger Zones)
        next_tele: list[dict] = []
        for tg in self.telegraphs:
            tg["t"] += dt
            if tg["t"] >= tg["dur"]:
                for sv in self.survivors.values():
                    if sv["alive"] and not sv["downed"] and _dist(tg["x"], tg["y"], sv["x"], sv["y"]) <= tg["radius"] + PLAYER_RADIUS * 0.5:
                        self._damage_survivor(sv, tg["dmg"], now, sx=tg["x"], sy=tg["y"], kind="boss")
                        ang = math.atan2(sv["y"] - tg["y"], sv["x"] - tg["x"])
                        sv["x"], sv["y"] = _resolve_circle_obstacles(
                            sv["x"] + math.cos(ang) * 28.0,
                            sv["y"] + math.sin(ang) * 28.0,
                            PLAYER_RADIUS,
                            obs,
                        )
                # Chiêu địa chấn / pháo kích của Boss cũng gây sát thương lên Trụ súng
                for t in self.turrets:
                    if t["hp"] > 0 and _dist(tg["x"], tg["y"], t["x"], t["y"]) <= tg["radius"] + 16.0:
                        t["hp"] = max(0.0, t["hp"] - tg["dmg"] * 1.4)
                self._emit(
                    "slam" if tg["kind"] == "slam" else "orbital",
                    x=round(tg["x"], 1),
                    y=round(tg["y"], 1),
                    radius=int(tg["radius"]),
                )
            else:
                next_tele.append(tg)
        self.telegraphs = next_tele

        # 6. Cập nhật Vũng Axit độc & Vùng Bão Băng Cryo trên mặt đất
        next_hazards: list[dict] = []
        for hz in self.hazards:
            hz["ttl"] -= dt
            if hz["ttl"] <= 0:
                continue
            next_hazards.append(hz)
            if hz.get("kind", "acid") == "cryo":
                for z in list(self.zombies):
                    if z["hp"] > 0 and _dist(z["x"], z["y"], hz["x"], hz["y"]) <= hz["radius"] + z["radius"] * 0.5:
                        z["slowTimer"] = max(z["slowTimer"], 0.45)
                        self._damage_zombie(z, hz["dps"] * dt, hz.get("owner", ""), emit_hit=False)
            else:
                for sv in self.survivors.values():
                    if sv["alive"] and not sv["downed"] and _dist(sv["x"], sv["y"], hz["x"], hz["y"]) <= hz["radius"]:
                        self._damage_survivor(sv, hz["dps"] * dt, now, sx=hz["x"], sy=hz["y"], kind="acid")
        self.hazards = next_hazards
        self.zombies = [z for z in self.zombies if z["hp"] > 0]

        # 8. Cập nhật AI & Va chạm Zombie (bọc sườn, bắn đón đầu, né Cryo, scale kỹ năng theo đội hình)
        standing = [sv for sv in self.survivors.values() if sv["alive"] and not sv["downed"]]
        downed = [sv for sv in self.survivors.values() if sv["alive"] and sv["downed"]]
        cryo_zones = [hz for hz in self.hazards if hz.get("kind") == "cryo"]
        cd_mult = sc["cd_mult"]
        dmg_mult = sc["dmg_mult"]
        for z in list(self.zombies):
            if z["hp"] <= 0:
                continue
            if z["hitFlash"] > 0:
                z["hitFlash"] = max(0.0, z["hitFlash"] - dt)
            if z["slowTimer"] > 0:
                z["slowTimer"] = max(0.0, z["slowTimer"] - dt)
            if z.get("teslaStunCd", 0.0) > 0:
                z["teslaStunCd"] = max(0.0, z["teslaStunCd"] - dt)
            if z["burnTimer"] > 0:
                z["burnTimer"] -= dt
                z["burnHitCd"] = max(0.0, z.get("burnHitCd", 0.0) - dt)
                emit_burn = z["burnHitCd"] <= 0.0
                if emit_burn:
                    z["burnHitCd"] = 0.4
                if self._damage_zombie(z, z["burnDps"] * dt, z["burnOwner"], emit_hit=emit_burn):
                    continue

            # Nếu đang bị CHOÁNG (EMP / Tesla / Mìn) -> đứng im hoàn toàn!
            if z["stunTimer"] > 0:
                z["stunTimer"] = max(0.0, z["stunTimer"] - dt)
                z["vx"], z["vy"] = 0.0, 0.0
                z["chargeTimer"] = 0.0
                continue

            if not standing:
                z["vx"], z["vy"] = 0.0, 0.0
                continue
            target_sv = self._choose_zombie_target(z, standing, downed)
            d_sv = _dist(z["x"], z["y"], target_sv["x"], target_sv["y"])

            # Kiểm tra xem có Trụ súng Sentry nào nằm sát đường hoặc rất gần -> Zombie lao vào đập Trụ!
            target_turret = None
            d_tr = float("inf")
            for t in self.turrets:
                if t["hp"] <= 0:
                    continue
                td = _dist(z["x"], z["y"], t["x"], t["y"])
                if td < d_tr:
                    d_tr = td
                    target_turret = t
            turret_aggro_r = 165.0 if z["kind"] in ("runner", "brute", "butcher", "boss", "titan") else 140.0
            attacking_turret = target_turret is not None and d_tr < min(turret_aggro_r, d_sv * 0.90)
            tx_pos = target_turret["x"] if attacking_turret else target_sv["x"]
            ty_pos = target_turret["y"] if attacking_turret else target_sv["y"]
            dx = tx_pos - z["x"]
            dy = ty_pos - z["y"]
            d = math.hypot(dx, dy) or 1.0
            nx_dir, ny_dir = dx / d, dy / d
            has_los = not any(_segment_hits_rect(z["x"], z["y"], tx_pos, ty_pos, ob) is not None for ob in obs)

            # Trạng thái Cuồng Bạo (Enrage) của Bạo Chúa Titan khi máu < 50%
            if z["kind"] == "titan" and not z["enraged"] and z["hp"] <= z["maxHp"] * 0.5:
                z["enraged"] = True
                z["speed"] *= 1.25
                z["skillLabel"] = "⚡ CUỒNG BẠO!"
                z["skillLabelUntil"] = now + 3.0
                self._emit("slam", x=round(z["x"], 1), y=round(z["y"], 1), radius=150)
                self.system("⚠️ Bạo Chúa Hủy Diệt đã kích hoạt trạng thái CUỒNG BẠO!")

            # Kỹ năng đặc biệt theo chủng Zombie / Mini-Boss / Boss (có bắn đón đầu & scale theo số người)
            z["specialCd"] -= dt
            if z["kind"] == "spitter" and 140.0 <= d <= 450.0 and has_los and z["specialCd"] <= 0:
                z["specialCd"] = self.rng.uniform(2.3, 3.4) * cd_mult
                if attacking_turret:
                    lead_x, lead_y = tx_pos, ty_pos
                else:
                    lead_x, lead_y = self._predict_target_pos(z["x"], z["y"], target_sv, 325.0, lead_factor=0.68)
                base_a = math.atan2(lead_y - z["y"], lead_x - z["x"])
                # Khi phòng đông (>= 4 người) ở wave >= 4: phun chùm 2-3 tia axit quạt hẹp!
                offsets = (-0.16, 0.0, 0.16) if (n_players >= 4 and self.wave >= 4) else (0.0,)
                for off in offsets:
                    ang = base_a + off
                    self.projectiles.append({
                        "id": self._next_id(),
                        "kind": "acid",
                        "x": z["x"],
                        "y": z["y"],
                        "vx": math.cos(ang) * 325.0,
                        "vy": math.sin(ang) * 325.0,
                        "dmg": z["dmg"],
                        "ttl": 1.65,
                        "spawnAcid": (off == 0.0 and n_players >= 3),
                    })
            elif z["kind"] == "butcher" and d <= 290.0 and z["specialCd"] <= 0:
                z["specialCd"] = 3.8 * cd_mult
                if attacking_turret:
                    lead_x, lead_y = tx_pos, ty_pos
                else:
                    lead_x, lead_y = self._predict_target_pos(z["x"], z["y"], target_sv, 355.0, lead_factor=0.72)
                ldx, ldy = lead_x - z["x"], lead_y - z["y"]
                ld = math.hypot(ldx, ldy) or 1.0
                lnx, lny = ldx / ld, ldy / ld
                z["chargeTimer"] = 0.48
                z["chargeVx"] = lnx * 355.0
                z["chargeVy"] = lny * 355.0
                z["skillLabel"] = "CHÉM XOÁY ĐỊA CHẤN"
                z["skillLabelUntil"] = now + 1.5
                tx = _clamp(z["x"] + lnx * min(ld, 125.0), 60.0, ARENA_W - 60.0)
                ty = _clamp(z["y"] + lny * min(ld, 125.0), 60.0, ARENA_H - 60.0)
                self.telegraphs.append({
                    "id": self._next_id(),
                    "kind": "slam",
                    "x": tx,
                    "y": ty,
                    "radius": 115.0 + min(24.0, (n_players - 1) * 5.0),
                    "t": 0.0,
                    "dur": max(0.52, 0.65 - (n_players - 1) * 0.025),
                    "dmg": 34.0 * dmg_mult,
                })
            elif z["kind"] == "queen" and 110.0 <= d <= 540.0 and z["specialCd"] <= 0:
                z["specialCd"] = 4.0 * cd_mult
                z["skillLabel"] = "MƯA AXIT ĐỘC"
                z["skillLabelUntil"] = now + 1.5
                if attacking_turret:
                    lead_x, lead_y = tx_pos, ty_pos
                else:
                    lead_x, lead_y = self._predict_target_pos(z["x"], z["y"], target_sv, 305.0, lead_factor=0.75)
                base_a = math.atan2(lead_y - z["y"], lead_x - z["x"])
                fan = (-0.54, -0.36, -0.18, 0.0, 0.18, 0.36, 0.54) if n_players >= 5 else (-0.42, -0.21, 0.0, 0.21, 0.42)
                for offset in fan:
                    ang = base_a + offset
                    self.projectiles.append({
                        "id": self._next_id(),
                        "kind": "acid",
                        "x": z["x"],
                        "y": z["y"],
                        "vx": math.cos(ang) * 305.0,
                        "vy": math.sin(ang) * 305.0,
                        "dmg": 18.0 * dmg_mult,
                        "ttl": 1.4,
                        "spawnAcid": (abs(offset) <= 0.22 if n_players >= 4 else offset == 0.0),
                    })
                summon_cnt = min(4, 2 + (n_players - 1) // 2)
                for _ in range(summon_cnt):
                    if len(self.zombies) < max_active:
                        self._spawn_one_zombie("runner")
            elif z["kind"] in ("brute", "boss") and 95.0 <= d <= 400.0 and z["specialCd"] <= 0:
                z["specialCd"] = (4.6 if z["kind"] == "brute" else 4.0) * cd_mult
                spd_charge = (345.0 if z["kind"] == "brute" else 330.0) * sc["speed_mult"]
                if attacking_turret:
                    lead_x, lead_y = tx_pos, ty_pos
                else:
                    lead_x, lead_y = self._predict_target_pos(z["x"], z["y"], target_sv, spd_charge, lead_factor=0.65)
                ldx, ldy = lead_x - z["x"], lead_y - z["y"]
                ld = math.hypot(ldx, ldy) or 1.0
                z["chargeTimer"] = 0.65
                z["chargeVx"] = (ldx / ld) * spd_charge
                z["chargeVy"] = (ldy / ld) * spd_charge
                if z["kind"] == "boss":
                    z["skillLabel"] = "HÚC ĐỊA CHẤN & VÒNG ĐỘC"
                    z["skillLabelUntil"] = now + 1.8
                    ring_n = 8 + min(4, max(0, n_players - 2))
                    for k in range(ring_n):
                        ang = (math.tau / ring_n) * k
                        self.projectiles.append({
                            "id": self._next_id(),
                            "kind": "acid",
                            "x": z["x"],
                            "y": z["y"],
                            "vx": math.cos(ang) * 265.0,
                            "vy": math.sin(ang) * 265.0,
                            "dmg": 16.0 * dmg_mult,
                            "ttl": 1.95,
                        })
                    # Khi đội >= 3 người, Boss gọi thêm địa chấn đón đầu vào vị trí đồng đội
                    if n_players >= 3:
                        slam_targets = list(standing)
                        self.rng.shuffle(slam_targets)
                        for st in slam_targets[:min(2, len(slam_targets))]:
                            px, py = self._predict_target_pos(z["x"], z["y"], st, 220.0, lead_factor=0.6)
                            self.telegraphs.append({
                                "id": self._next_id(),
                                "kind": "slam",
                                "x": px,
                                "y": py,
                                "radius": 92.0,
                                "t": 0.0,
                                "dur": 0.95,
                                "dmg": 32.0 * dmg_mult,
                            })
                    summon_cnt = min(4, 2 + (n_players - 1) // 2)
                    for _ in range(summon_cnt):
                        if len(self.zombies) < max_active:
                            self._spawn_one_zombie("runner")
            elif z["kind"] == "titan" and z["specialCd"] <= 0:
                z["specialCd"] = (3.1 if z["enraged"] else 4.2) * cd_mult
                z["skillLabel"] = "PHÁO KÍCH NHIỆT HẠCH"
                z["skillLabelUntil"] = now + 2.0
                targets = list(standing)
                self.rng.shuffle(targets)
                # Số vòng pháo kích scale trực tiếp theo số lượng chiến binh (tối đa 6 vòng cho đội 6 người)
                salvo = min(6, max(2, len(targets) + (1 if z["enraged"] else 0)))
                for idx_t in range(salvo):
                    tsv = targets[idx_t % len(targets)]
                    px, py = self._predict_target_pos(z["x"], z["y"], tsv, 240.0, lead_factor=0.72)
                    ox = self.rng.uniform(-44.0, 44.0) if idx_t >= len(targets) else 0.0
                    oy = self.rng.uniform(-44.0, 44.0) if idx_t >= len(targets) else 0.0
                    self.telegraphs.append({
                        "id": self._next_id(),
                        "kind": "orbital",
                        "x": _clamp(px + ox, 50.0, ARENA_W - 50.0),
                        "y": _clamp(py + oy, 50.0, ARENA_H - 50.0),
                        "radius": 90.0,
                        "t": 0.0,
                        "dur": max(0.85, (1.02 if z["enraged"] else 1.18) - (n_players - 1) * 0.02),
                        "dmg": 42.0 * dmg_mult,
                    })
                if z["enraged"]:
                    ring_n = 12 + min(4, max(0, n_players - 2))
                    for k in range(ring_n):
                        ang = (math.tau / ring_n) * k + (now % 1.0)
                        self.projectiles.append({
                            "id": self._next_id(),
                            "kind": "plasma",
                            "x": z["x"],
                            "y": z["y"],
                            "vx": math.cos(ang) * 295.0,
                            "vy": math.sin(ang) * 295.0,
                            "dmg": 20.0 * dmg_mult,
                            "ttl": 2.0,
                        })

            slow_mult = 0.35 if z["slowTimer"] > 0 else 1.0
            eff_speed = z["speed"] * slow_mult
            # Bloater khi còn < 45% máu sẽ tăng tốc lao vào nổ sát đội hình!
            if z["kind"] == "bloater" and z["hp"] < z["maxHp"] * 0.45:
                eff_speed *= 1.35

            if z["chargeTimer"] > 0:
                z["chargeTimer"] -= dt
                mvx, mvy = z["chargeVx"] * slow_mult, z["chargeVy"] * slow_mult
            elif z["kind"] in ("spitter", "queen") and has_los and d < 235.0:
                # Kiting chéo (lùi kết hợp di chuyển ngang để né đạn)
                fside = z.get("flankSide", 1.0)
                kx = -nx_dir * 0.72 + (-ny_dir * fside) * 0.68
                ky = -ny_dir * 0.72 + (nx_dir * fside) * 0.68
                km = math.hypot(kx, ky) or 1.0
                mvx, mvy = (kx / km) * eff_speed * 0.72, (ky / km) * eff_speed * 0.72
            elif z["kind"] in ("spitter", "queen") and has_los and 235.0 <= d <= 360.0:
                # Ở tầm bắn lý tưởng: di chuyển vòng ngang (strafe) gây khó cho xạ thủ
                fside = z.get("flankSide", 1.0)
                mvx, mvy = (-ny_dir * fside) * eff_speed * 0.58, (nx_dir * fside) * eff_speed * 0.58
            else:
                steer_x, steer_y = _steer_around_obstacles(z["x"], z["y"], tx_pos, ty_pos, z["radius"], obs)
                # Chiến thuật bọc sườn (flanking): Runner & một phần Walker vòng 2 cánh bao vây thay vì đi 1 hàng thẳng
                flank_str = z.get("flankStrength", 0.0)
                if flank_str > 0.0 and 105.0 < d < 420.0:
                    fside = z.get("flankSide", 1.0)
                    blend = flank_str * min(1.0, (d - 105.0) / 170.0)
                    px_f, py_f = -steer_y * fside, steer_x * fside
                    steer_x += px_f * blend
                    steer_y += py_f * blend
                # Né vũng bão băng Cryo nếu còn đường vòng
                if cryo_zones:
                    for cz in cryo_zones:
                        cdx, cdy = z["x"] - cz["x"], z["y"] - cz["y"]
                        cd = math.hypot(cdx, cdy) or 1.0
                        avoid_r = cz["radius"] + z["radius"] + 28.0
                        if cd < avoid_r:
                            cw = (avoid_r - cd) / avoid_r
                            steer_x += (cdx / cd) * cw * 1.45
                            steer_y += (cdy / cd) * cw * 1.45
                sm = math.hypot(steer_x, steer_y) or 1.0
                mvx, mvy = (steer_x / sm) * eff_speed, (steer_y / sm) * eff_speed
                if z["kind"] == "runner":
                    wobble = math.sin(now * 7.0 + z["id"]) * 0.28
                    mvx, mvy = (
                        mvx * math.cos(wobble) - mvy * math.sin(wobble),
                        mvx * math.sin(wobble) + mvy * math.cos(wobble),
                    )

            z["vx"], z["vy"] = mvx, mvy
            z["x"], z["y"] = _resolve_circle_obstacles(z["x"] + mvx * dt, z["y"] + mvy * dt, z["radius"], obs)

            # Tấn công cận chiến (đánh Chiến binh hoặc đập Trụ súng Sentry!)
            z["atkCd"] = max(0.0, z["atkCd"] - dt * slow_mult)
            if z["atkCd"] <= 0:
                if attacking_turret and target_turret is not None and d <= z["radius"] + 22.0:
                    z["atkCd"] = 0.85
                    target_turret["hp"] = max(0.0, target_turret["hp"] - z["dmg"])
                    self._emit("turret_hit", x=round(target_turret["x"], 1), y=round(target_turret["y"], 1), dmg=int(round(z["dmg"])))
                elif d_sv <= z["radius"] + PLAYER_RADIUS + 8.0:
                    z["atkCd"] = 0.85
                    self._damage_survivor(target_sv, z["dmg"], now, sx=z["x"], sy=z["y"], kind="melee")

        self.zombies = [z for z in self.zombies if z["hp"] > 0]

        # Tách nhẹ các zombie chồng lên nhau để đội hình đàn trông đẹp
        nz = len(self.zombies)
        for i in range(nz):
            zi = self.zombies[i]
            for j in range(i + 1, nz):
                zj = self.zombies[j]
                dx = zj["x"] - zi["x"]
                dy = zj["y"] - zi["y"]
                min_d = zi["radius"] + zj["radius"] - 2.0
                d2 = dx * dx + dy * dy
                if 1e-4 < d2 < min_d * min_d:
                    d = math.sqrt(d2)
                    push = (min_d - d) * 0.32
                    ux, uy = dx / d, dy / d
                    zi["x"] -= ux * push
                    zi["y"] -= uy * push
                    zj["x"] += ux * push
                    zj["y"] += uy * push

        # 9. Kiểm tra thắng / thua / hoàn thành đợt
        alive_standing = [sv for sv in self.survivors.values() if sv["alive"] and not sv["downed"]]
        if not alive_standing:
            self._finish_match(victory=False)
            return True

        if not self.wave_remaining_to_spawn and not self.zombies:
            bonus = 110 + self.wave * 35
            for sv in self.survivors.values():
                sv["money"] += bonus
                sv["score"] += 300 + self.wave * 50
            if self.max_waves > 0 and self.wave >= self.max_waves:
                self._finish_match(victory=True)
                return True
            self.phase = "shop"
            self.shop_deadline = now + SHOP_SECONDS
            self.projectiles.clear()
            self.hazards.clear()
            self.telegraphs.clear()
            self.system(f"✨ Đã dọn sạch Đợt {self.wave}! (+${bonus} thưởng) — Mở Cửa Hàng Tiếp Tế {int(SHOP_SECONDS)}s!")
            return True

        return True

    def _step_bots(self, dt: float, now: float) -> None:
        from bot_zombie import step_bot_survivor
        for p in self.bot_players():
            sv = self.survivors.get(p.mark)
            if sv is not None:
                step_bot_survivor(self, p, sv, dt, now)
        # Z3/Z15: Tạm giao survivor của người chơi mất kết nối cho AI tự vệ tới khi họ vào lại
        for m, sv in self.survivors.items():
            p = self.seat(m)
            if p is not None and not p.bot and not p.connected:
                step_bot_survivor(self, p, sv, dt, now)

    def _finish_match(self, victory: bool) -> None:
        self.victory = victory
        self.phase = "finished"
        self.status = "finished"
        self.rematch.clear()
        self.projectiles.clear()
        self.telegraphs.clear()
        if victory:
            self.winner = "SQUAD"
            for m in self.survivors:
                self.scores[m] = self.scores.get(m, 0) + 1
            self.system(f"🏆 CHIẾN THẮNG! Đội đã trụ vững qua toàn bộ {self.wave} đợt tấn công ({self.total_kills} tiêu diệt)!")
        else:
            self.winner = "ZOMBIES"
            self.system(f"💀 Toàn đội đã gục ngã tại Đợt {self.wave} ({self.total_kills} tiêu diệt).")
        self.touched = time.time()

    # ---- Hành động từ Client ----------------------------------------------- #
    def disconnect(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is not None and player.mark and self.in_progress():
            sv = self.survivors.get(player.mark)
            if sv is not None:
                sv["vx"] = 0.0
                sv["vy"] = 0.0
                sv["firing"] = False
        super().disconnect(uid)

    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        mark = player.mark
        if self.in_progress():
            # Z2: Giữa trận chỉ rút riêng người này ra khỏi đội; không hủy trận của đồng đội còn lại!
            player.mark = ""
            self.rematch.discard(mark)
            self.survivors.pop(mark, None)
            self.system(f"{player.name} rời khỏi đội hình ({self._seat_label(mark)}).")
            remaining_humans = [
                m for m in self._seated_marks()
                if (p := self.seat(m)) is not None and not p.bot
            ]
            if not remaining_humans or not self.survivors:
                self.status = "waiting"
                self.winner = ""
                self.reset_match()
                self.system("Trận đấu kết thúc vì không còn người chơi trong đội.")
            self.touched = time.time()
            return
        super().stand(uid)
        self.survivors.pop(mark, None)

    def resign(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        other_humans = [
            m for m in self._seated_marks()
            if m != player.mark and (p := self.seat(m)) is not None and not p.bot
        ]
        if other_humans:
            # Z2: Nếu còn đồng đội người thật khác đang chơi, chỉ rút người này ra thay vì kết thúc cả phòng
            mark = player.mark
            self.survivors.pop(mark, None)
            self.system(f"{player.name} rút lui khỏi chiến trường.")
            if not self.survivors:
                self._finish_match(victory=False)
            else:
                self.touched = time.time()
            return
        self._finish_match(victory=False)

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ chiến binh trong đội mới xin chơi lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        # Chỉ yêu cầu phiếu của các người chơi thực đang kết nối (và bot tự đồng ý)
        required = {
            m for m in self._seated_marks()
            if (p := self.seat(m)) is not None and (p.bot or p.connected)
        }
        if required and self.rematch >= required:
            self._start_match()
        else:
            self.system(f"{player.name} muốn chiến đấu ván mới.")

    def handle(self, uid: str, action: str, msg: dict) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn cần chọn ghế chiến binh để thao tác.")
        mark = player.mark

        if action == "config":
            if self.in_progress():
                raise GameError("Không thể đổi bản đồ khi trận đang chạy.")
            self.apply_initial_config(msg)
            self.touched = time.time()
            return

        if action == "class":
            if self.in_progress():
                raise GameError("Không thể đổi lớp nhân vật khi trận đang chạy.")
            cls_id = str(msg.get("cls", "")).strip()
            if cls_id not in CLASSES:
                raise GameError("Lớp nhân vật không hợp lệ.")
            req_mark = str(msg.get("mark", "")).strip()
            if req_mark and req_mark != mark:
                tp = self.seat(req_mark)
                if tp is None or not tp.bot:
                    raise GameError("Chỉ đổi lớp cho chính mình hoặc cho Bot.")
                self.seat_classes[req_mark] = cls_id
            else:
                self.seat_classes[mark] = cls_id
            self.touched = time.time()
            return

        if action == "add_bot":
            self.add_single_bot(level=str(msg.get("level", "normal")), mark=str(msg.get("mark", "")))
            return

        if action == "remove_bot":
            self.remove_bot_seat(str(msg.get("mark", "")))
            return

        if action == "start":
            if self.in_progress():
                raise GameError("Trận đấu đang diễn ra.")
            self._start_match()
            return

        if not self.in_progress():
            return

        sv = self.survivors.get(mark)
        if sv is None:
            return
        now = time.time()

        if action == "input":
            if sv["alive"] and not sv["downed"]:
                sv["vx"] = _clamp(_finite_float(msg.get("vx", 0.0), 0.0), -1.0, 1.0)
                sv["vy"] = _clamp(_finite_float(msg.get("vy", 0.0), 0.0), -1.0, 1.0)
                sv["aim"] = _finite_float(msg.get("aim", sv["aim"]), sv["aim"]) % math.tau
                sv["firing"] = bool(msg.get("firing", False))
                if sv["firing"] and self.phase == "wave":
                    self._fire_weapon(sv, now)
            return

        if action == "shoot":
            if self.phase == "wave" and sv["alive"] and not sv["downed"]:
                if "aim" in msg:
                    sv["aim"] = _finite_float(msg["aim"], sv["aim"]) % math.tau
                self._fire_weapon(sv, now)
            return

        if action == "reload":
            if sv["alive"] and not sv["downed"]:
                self._trigger_reload(sv, now)
            return

        if action == "switch":
            wid = str(msg.get("weapon", "")).strip()
            if wid in sv["weapons"] and wid != sv["weapon"]:
                sv["weapon"] = wid
                sv["reloadUntil"] = 0.0
            return

        if action == "dash":
            if self.phase in ("wave", "shop"):
                self._do_dash(sv, now)
            return

        if action == "grenade":
            if self.phase == "wave":
                tx = _clamp(_finite_float(msg.get("tx"), sv["x"] + math.cos(sv["aim"]) * 220.0), 0.0, ARENA_W)
                ty = _clamp(_finite_float(msg.get("ty"), sv["y"] + math.sin(sv["aim"]) * 220.0), 0.0, ARENA_H)
                gkind = str(msg.get("kind", "grenade")).strip()
                if gkind not in ("grenade", "cryo", "emp"):
                    gkind = "grenade"
                self._throw_grenade(sv, tx, ty, kind=gkind)
            return

        if action == "cryo":
            if self.phase == "wave":
                tx = _clamp(_finite_float(msg.get("tx"), sv["x"] + math.cos(sv["aim"]) * 220.0), 0.0, ARENA_W)
                ty = _clamp(_finite_float(msg.get("ty"), sv["y"] + math.sin(sv["aim"]) * 220.0), 0.0, ARENA_H)
                self._throw_grenade(sv, tx, ty, kind="cryo")
            return

        if action == "emp":
            if self.phase == "wave":
                tx = _clamp(_finite_float(msg.get("tx"), sv["x"] + math.cos(sv["aim"]) * 220.0), 0.0, ARENA_W)
                ty = _clamp(_finite_float(msg.get("ty"), sv["y"] + math.sin(sv["aim"]) * 220.0), 0.0, ARENA_H)
                self._throw_grenade(sv, tx, ty, kind="emp")
            return

        if action == "mine":
            if self.phase in ("wave", "shop"):
                self._deploy_mine(sv)
            return

        if action == "turret":
            if self.phase in ("wave", "shop"):
                self._deploy_turret(sv)
            return

        if action == "buy":
            self._buy_item(sv, str(msg.get("item", "")).strip())
            self.touched = now
            return

        if action == "ready_shop":
            if self.phase == "shop":
                sv["readyShop"] = True
            return

        raise GameError("Hành động không hợp lệ.")

    # ---- Serialize state cho Client 60 FPS --------------------------------- #
    def match_view(self, uid: str) -> dict:
        now = time.time()
        boss_list = [
            {
                "id": z["id"],
                "kind": z["kind"],
                "title": ZOMBIE_SPECS[z["kind"]].get("title", "Boss"),
                "isMini": bool(ZOMBIE_SPECS[z["kind"]].get("miniBoss", False)),
                "hp": round(z["hp"], 1),
                "maxHp": round(z["maxHp"], 1),
                "enraged": bool(z.get("enraged", False)),
                "skill": z["skillLabel"] if z.get("skillLabelUntil", 0.0) > now else "",
            }
            for z in self.zombies
            if z["kind"] in BOSS_KINDS and z["hp"] > 0
        ]
        boss_primary = boss_list[0] if boss_list else None
        sv_out = []
        for m, sv in self.survivors.items():
            p = self.seat(m)
            cls_spec = CLASSES.get(sv["cls"], CLASSES["assault"])
            reload_left = max(0.0, round(sv["reloadUntil"] - now, 2)) if sv["reloadUntil"] > now else 0.0
            sv_out.append({
                "mark": m,
                "name": p.name if p else m,
                "color": p.color if p else "#38bdf8",
                "bot": p.bot if p else False,
                "cls": sv["cls"],
                "x": round(sv["x"], 1),
                "y": round(sv["y"], 1),
                "vx": round(sv.get("moveVx", 0.0), 1),
                "vy": round(sv.get("moveVy", 0.0), 1),
                "aim": round(sv["aim"], 3),
                "hp": round(sv["hp"], 1),
                "maxHp": round(sv["maxHp"], 1),
                "armor": round(sv["armor"], 1),
                "maxArmor": round(sv["maxArmor"], 1),
                "alive": sv["alive"],
                "downed": sv["downed"],
                "bleedout": round(max(0.0, sv["bleedout"]), 1),
                "reviveProg": round(sv["reviveProg"], 2),
                "weapon": sv["weapon"],
                "weapons": list(sv["weapons"]),
                "weaponLv": dict(sv.get("weaponLv", {})),
                "mag": dict(sv["mag"]),
                "reserve": dict(sv["reserve"]),
                "reloading": reload_left > 0,
                "reloadLeft": reload_left,
                "reloadTotal": round(float(sv.get("reloadTotal", 1.0)), 2),
                "dashReady": max(0.0, round(sv["dashCd"] - now, 2)),
                "dashTotal": cls_spec["dashCd"],
                "dashing": sv["dashUntil"] > now,
                "stimLeft": max(0.0, round(sv.get("stimUntil", 0.0) - now, 1)),
                "grenades": sv["grenades"],
                "cryos": sv.get("cryos", 0),
                "emps": sv.get("emps", 0),
                "mines": sv.get("mines", 0),
                "turrets": sv["turrets"],
                "money": sv["money"],
                "score": sv["score"],
                "kills": sv["kills"],
                "revives": sv["revives"],
                "perks": dict(sv["perks"]),
                "readyShop": sv["readyShop"],
            })

        out = {
            "matchId": self.match_id,
            "phase": self.phase,
            "config": dict(self.config),
            "seatClasses": dict(self.seat_classes),
            "arena": {"w": ARENA_W, "h": ARENA_H, "obstacles": self._obstacles()},
            "wave": self.wave,
            "maxWaves": self.max_waves,
            "victory": self.victory,
            "totalKills": self.total_kills,
            "zombiesLeft": len(self.zombies) + len(self.wave_remaining_to_spawn),
            "shopLeft": max(0.0, round(self.shop_deadline - now, 1)) if self.phase == "shop" else 0.0,
            "buffs": {
                "doubleDmg": max(0.0, round(self.double_dmg_until - now, 1)),
                "infAmmo": max(0.0, round(self.inf_ammo_until - now, 1)),
            },
            "boss": boss_primary,
            "bosses": boss_list,
            "survivors": sv_out,
            "zombies": [
                {
                    "id": z["id"],
                    "kind": z["kind"],
                    "x": round(z["x"], 1),
                    "y": round(z["y"], 1),
                    "vx": round(z.get("vx", 0.0), 1),
                    "vy": round(z.get("vy", 0.0), 1),
                    "hp": round(z["hp"], 1),
                    "maxHp": round(z["maxHp"], 1),
                    "r": z["radius"],
                    "burn": z["burnTimer"] > 0,
                    "slow": z.get("slowTimer", 0.0) > 0,
                    "stun": z.get("stunTimer", 0.0) > 0,
                    "flash": z["hitFlash"] > 0,
                    "charging": z["chargeTimer"] > 0,
                    "enraged": bool(z.get("enraged", False)),
                }
                for z in self.zombies
            ],
            "projectiles": [
                {
                    "id": pr["id"],
                    "kind": pr["kind"],
                    "x": round(pr["x"], 1),
                    "y": round(pr["y"], 1),
                    "t": round(pr.get("t", 0.0) / max(0.01, pr.get("dur", 1.0)), 2) if pr["kind"] in ("grenade", "cryo", "emp") else 0.0,
                }
                for pr in self.projectiles
            ],
            "hazards": [
                {"id": h["id"], "kind": h.get("kind", "acid"), "x": round(h["x"], 1), "y": round(h["y"], 1), "r": h["radius"], "ttl": round(h["ttl"], 1)}
                for h in self.hazards
            ],
            "telegraphs": [
                {
                    "id": tg["id"],
                    "kind": tg["kind"],
                    "x": round(tg["x"], 1),
                    "y": round(tg["y"], 1),
                    "r": tg["radius"],
                    "prog": round(min(1.0, tg["t"] / max(0.05, tg["dur"])), 2),
                }
                for tg in self.telegraphs
            ],
            "turrets": [
                {
                    "id": t["id"],
                    "x": round(t["x"], 1),
                    "y": round(t["y"], 1),
                    "aim": round(t["aim"], 2),
                    "hp": round(t["hp"], 1),
                    "maxHp": round(t["maxHp"], 1),
                    "ammo": t["ammo"],
                    "maxAmmo": t["maxAmmo"],
                }
                for t in self.turrets
            ],
            "mines": [
                {"id": m["id"], "x": round(m["x"], 1), "y": round(m["y"], 1), "r": m["triggerR"]}
                for m in self.mines
            ],
            "barrels": [
                {"id": b["id"], "x": round(b["x"], 1), "y": round(b["y"], 1), "r": b["r"], "hp": round(b["hp"], 1), "maxHp": round(b["maxHp"], 1)}
                for b in self.barrels
            ],
            "pickups": [
                {"id": pk["id"], "kind": pk["kind"], "x": round(pk["x"], 1), "y": round(pk["y"], 1)}
                for pk in self.pickups
            ],
            "events": self.events[-100:],
            "catalog": _ZOMBIE_CATALOG,
            "seatedCount": len(self._seated_marks()),
            "maxSeats": len(self.SEATS),
        }
        return out

    def you_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        return {
            "uid": uid,
            "mark": player.mark if player else "",
            "name": player.name if player else "",
        }

    def shared_view(self, *, full: bool = True) -> dict:
        """Build state dùng chung 1 lần mỗi tick cho cả phòng (hỗ trợ delta frame 15 Hz)."""
        static_ver = (
            self.match_id,
            self.mode,
            self.phase,
            self.status,
            len(self.chat),
            tuple(
                (m, p.uid, p.name, p.connected, p.bot)
                for m in self.SEATS
                if (p := self.seat(m)) is not None
            ),
        )
        include_static = full or (static_ver != self._last_static_ver)
        self._last_static_ver = static_ver

        base: dict = {
            "code": self.code,
            "mode": self.mode,
            "label": self.label,
            "status": self.status,
            "winner": self.winner,
            "scores": self.scores,
            "spectators": [{"name": p.name, "color": p.color}
                           for p in self.players.values() if not p.mark and p.connected],
            "rematch": sorted(self.rematch),
        }
        if include_static:
            base["seatOrder"] = list(self.SEATS)
            base["seats"] = {m: self._seat_info(m) for m in self.SEATS}
            base["seatLabels"] = {m: self._seat_label(m) for m in self.SEATS}
            base["chat"] = self.chat[-40:]

        mv = self.match_view("")
        if not include_static:
            mv.pop("catalog", None)
            mv.pop("arena", None)
        if full:
            mv["events"] = self.events[-30:]
        else:
            last_seq = self._last_broadcast_event_seq
            mv["events"] = [e for e in self.events if e["seq"] > last_seq]
        if self.events:
            self._last_broadcast_event_seq = max(self._last_broadcast_event_seq, self.events[-1]["seq"])

        base.update(mv)
        return base


_ZOMBIE_CATALOG = {
    "classes": {k: {"label": v["label"], "hp": v["hp"], "armor": v["armor"], "speed": v["speed"]} for k, v in CLASSES.items()},
    "weapons": {
        k: {
            "name": v["name"],
            "cost": v["cost"],
            "dmg": v["dmg"],
            "rate": v["rate"],
            "mag": v["mag"],
            "pellets": v["pellets"],
            "range": v["range"],
            "pierce": v["pierce"],
            "splash": v.get("splash", 0.0),
            "burn": v.get("burn", 0.0),
            "chain": v.get("chain", 0),
            "color": v["color"],
        }
        for k, v in WEAPONS.items()
    },
    "weaponOrder": list(WEAPON_ORDER),
    "maxWeaponLv": MAX_WEAPON_LV,
    "perks": PERKS,
    "items": SHOP_ITEMS,
}
