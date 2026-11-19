"""Đêm Tử Thần (Zombie Outbreak) — Game bắn súng sinh tồn Zombie Multiplayer (1–4 người Co-op & AI Bots).

Lấy cảm hứng từ các cơ chế xuất sắc nhất của Left 4 Dead 2, Killing Floor 2, CoD Zombies & Alien Swarm:
  - 6 chủng Zombie & Boss Đột Biến (Walker, Runner, Bloater Axit, Spitter Xạ Độc, Brute Húc, Abomination Boss)
  - 4 lớp Chiến Binh (Assault, Medic, Engineer, Vanguard) & 6 loại vũ khí + 5 Perk nâng cấp
  - Cơ chế Gục Ngã (Downed 15s) & Đồng đội cứu thương (Revive 2.5s), Lướt né (Dash), Lựu đạn & Trụ súng Sentry
  - Pha Tiếp Tế giữa các đợt (Armory Shop 12s) để mua súng, đạn, giáp, trụ súng và nâng cấp kỹ năng
  - Chạy mô phỏng authoritative ở 15 Hz phía server và nội suy 60 FPS mượt mà ở client Canvas 2.5D
"""
from __future__ import annotations

import math
import random
import time

from games import GameError, Player, SeatedRoom, bot_uid

ARENA_W = 1400.0
ARENA_H = 900.0
PLAYER_RADIUS = 17.0
SHOP_SECONDS = 12.0
BLEEDOUT_SECONDS = 15.0
REVIVE_SECONDS = 2.5
REVIVE_RADIUS = 72.0

ZOMBIE_BOT_NAMES = ("Biệt Kích", "Sói Đêm", "Quân Y 09", "Thiết Giáp")

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
        "color": "#facc15",
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
        "color": "#f97316",
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
        "color": "#22d3ee",
    },
}

WEAPON_ORDER = ("pistol", "smg", "shotgun", "rifle", "flamer", "railgun")

PERKS: dict[str, dict] = {
    "damage": {"name": "Đạn Xuyên Phá", "cost": 200, "max": 3},
    "reload": {"name": "Băng Đạn Lớn", "cost": 180, "max": 3},
    "speed": {"name": "Giày Chiến Thuật", "cost": 170, "max": 3},
    "armor": {"name": "Giáp Nano", "cost": 190, "max": 3},
    "vamp": {"name": "Đạn Hút Máu", "cost": 240, "max": 3},
}

SHOP_ITEMS: dict[str, dict] = {
    "medkit": {"name": "Túi Máu & Giáp", "cost": 120},
    "ammo": {"name": "Tiếp Đạn Toàn Bộ", "cost": 100},
    "grenade": {"name": "Lựu Đạn Nổ (+2)", "cost": 140},
    "turret": {"name": "Trụ Súng Sentry (+1)", "cost": 280},
}

ZOMBIE_SPECS: dict[str, dict] = {
    "walker": {"hp": 58.0, "speed": 84.0, "radius": 16.0, "dmg": 14.0, "reward": 26, "score": 100},
    "runner": {"hp": 38.0, "speed": 166.0, "radius": 13.0, "dmg": 12.0, "reward": 34, "score": 140},
    "bloater": {"hp": 115.0, "speed": 68.0, "radius": 22.0, "dmg": 18.0, "reward": 52, "score": 220},
    "spitter": {"hp": 72.0, "speed": 80.0, "radius": 15.0, "dmg": 12.0, "reward": 50, "score": 210},
    "brute": {"hp": 290.0, "speed": 74.0, "radius": 26.0, "dmg": 28.0, "reward": 98, "score": 420},
    "boss": {"hp": 1250.0, "speed": 80.0, "radius": 38.0, "dmg": 36.0, "reward": 420, "score": 1500},
}

# Các chướng ngại vật hình chữ nhật (x, y, w, h, kind) tạo chiến thuật vòng vây cho 3 bản đồ
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


class ZombieRoom(SeatedRoom):
    CHANNEL = "zombie"
    SEATS = ("1", "2", "3", "4")
    HAS_CLOCK = True
    FAST_TICK = True  # Hub chạy vòng lặp 15 Hz khi phòng đang ở trạng thái playing
    START_STATUS = "playing"
    DEFAULT_MODE = "outpost"
    MODES = {
        "outpost": {"label": "Căn Cứ Bỏ Hoang (10 Đợt)", "maxWaves": 10},
        "lab": {"label": "Phòng Thí Nghiệm Ngầm (15 Đợt)", "maxWaves": 15},
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
        }
        self.config: dict = {
            "difficulty": "normal",  # easy | normal | hard
        }
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
        self.projectiles: list[dict] = []  # Đạn axit Spitter/Boss & lựu đạn bay
        self.hazards: list[dict] = []      # Vũng axit độc trên mặt đất
        self.turrets: list[dict] = []      # Trụ súng tự động Sentry
        self.pickups: list[dict] = []      # Vật phẩm rơi (Máu, Đạn, Tiền)
        self.events: list[dict] = []       # Ring buffer hiệu ứng VFX cho client 60 FPS
        self._event_seq: int = 0
        self._entity_seq: int = 0
        self.total_kills: int = 0
        self.match_started_at: float = 0.0

    def _emit(self, _event_type: str, **payload) -> None:
        self._event_seq += 1
        self.events.append({"seq": self._event_seq, "t": _event_type, **payload})
        if len(self.events) > 90:
            del self.events[:-90]

    def _next_id(self) -> int:
        self._entity_seq += 1
        return self._entity_seq

    def _try_start(self) -> None:
        # Cho phép 1–4 người chọn lớp nhân vật & thêm Bot trước khi bấm Bắt đầu.
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
            raise GameError("Đội đã đủ 4 chiến binh.")
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
            (ARENA_W * 0.44, ARENA_H * 0.44),
            (ARENA_W * 0.56, ARENA_H * 0.44),
            (ARENA_W * 0.44, ARENA_H * 0.56),
            (ARENA_W * 0.56, ARENA_H * 0.56),
        ]

    def _create_survivor(self, mark: str, idx: int) -> dict:
        cls_id = self.seat_classes.get(mark, "assault")
        spec = CLASSES.get(cls_id, CLASSES["assault"])
        sx, sy = self._spawn_positions()[idx % 4]
        sx, sy = _resolve_circle_obstacles(sx, sy, PLAYER_RADIUS, self._obstacles())
        owned = list(spec["startWeapons"])
        active_w = owned[-1] if owned else "pistol"
        ammo_mag = {w: WEAPONS[w]["mag"] for w in owned}
        ammo_res = {w: WEAPONS[w]["reserve"] for w in owned}
        return {
            "mark": mark,
            "cls": cls_id,
            "x": sx,
            "y": sy,
            "vx": 0.0,
            "vy": 0.0,
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
            "mag": ammo_mag,
            "reserve": ammo_res,
            "reloadUntil": 0.0,
            "fireCd": 0.0,
            "firing": False,
            "dashCd": 0.0,
            "dashUntil": 0.0,
            "dashVx": 0.0,
            "dashVy": 0.0,
            "grenades": int(spec["startGrenades"]),
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

    def _build_wave_queue(self, wave: int) -> list[str]:
        n_players = max(1, len(self.survivors))
        diff_mult = {"easy": 0.8, "normal": 1.0, "hard": 1.3}.get(self.config.get("difficulty", "normal"), 1.0)
        total = int(round((8 + wave * 4 + (n_players - 1) * 3) * diff_mult))
        queue: list[str] = []
        for _ in range(total):
            r = self.rng.random()
            if wave >= 4 and r < 0.11:
                queue.append("brute")
            elif wave >= 3 and r < 0.24:
                queue.append("spitter")
            elif wave >= 2 and r < 0.38:
                queue.append("bloater")
            elif wave >= 2 and r < 0.62:
                queue.append("runner")
            else:
                queue.append("walker")
        if wave % 5 == 0:
            queue.append("boss")
        self.rng.shuffle(queue)
        return queue

    def _begin_wave(self, wave_num: int) -> None:
        self.wave = wave_num
        self.phase = "wave"
        self.shop_deadline = 0.0
        self.wave_remaining_to_spawn = self._build_wave_queue(wave_num)
        self.spawn_timer = 0.4
        # Hồi sinh các chiến binh đã hy sinh ở đợt trước với 70% HP
        spawns = self._spawn_positions()
        for idx, (m, sv) in enumerate(self.survivors.items()):
            sv["readyShop"] = False
            if not sv["alive"] or sv["downed"]:
                sx, sy = spawns[idx % 4]
                sx, sy = _resolve_circle_obstacles(sx, sy, PLAYER_RADIUS, self._obstacles())
                sv["x"], sv["y"] = sx, sy
                sv["alive"] = True
                sv["downed"] = False
                sv["bleedout"] = 0.0
                sv["reviveProg"] = 0.0
                sv["hp"] = round(sv["maxHp"] * 0.75, 1)
                sv["armor"] = max(sv["armor"], 20.0)
        has_boss = "boss" in self.wave_remaining_to_spawn
        self._emit("wave", wave=wave_num, boss=has_boss)
        boss_note = " ⚠️ CHÚA TỂ ĐỘT BIẾN XUẤT HIỆN!" if has_boss else ""
        self.system(f"☣️ Đợt {wave_num} bắt đầu! ({len(self.wave_remaining_to_spawn)} quái vật){boss_note}")

    def _spawn_one_zombie(self, kind: str) -> dict:
        spec = ZOMBIE_SPECS[kind]
        diff_hp = {"easy": 0.82, "normal": 1.0, "hard": 1.28}.get(self.config.get("difficulty", "normal"), 1.0)
        wave_scale = 1.0 + (self.wave - 1) * 0.12
        player_scale = 1.0 + max(0, len(self.survivors) - 1) * 0.16
        hp = spec["hp"] * diff_hp * wave_scale * (player_scale if kind == "boss" else 1.0)
        if kind == "boss":
            hp = (spec["hp"] + self.wave * 180.0) * diff_hp * player_scale
        # Sinh ở 4 rìa bản đồ
        edge = self.rng.randint(0, 3)
        pad = spec["radius"] + 16.0
        if edge == 0:
            x, y = self.rng.uniform(pad, ARENA_W - pad), pad
        elif edge == 1:
            x, y = self.rng.uniform(pad, ARENA_W - pad), ARENA_H - pad
        elif edge == 2:
            x, y = pad, self.rng.uniform(pad, ARENA_H - pad)
        else:
            x, y = ARENA_W - pad, self.rng.uniform(pad, ARENA_H - pad)
        x, y = _resolve_circle_obstacles(x, y, spec["radius"], self._obstacles())
        z = {
            "id": self._next_id(),
            "kind": kind,
            "x": x,
            "y": y,
            "vx": 0.0,
            "vy": 0.0,
            "hp": hp,
            "maxHp": hp,
            "speed": spec["speed"] * (1.0 + min(0.35, (self.wave - 1) * 0.025)),
            "radius": spec["radius"],
            "dmg": spec["dmg"] * diff_hp,
            "reward": spec["reward"],
            "score": spec["score"],
            "atkCd": 0.0,
            "specialCd": self.rng.uniform(1.8, 3.5),
            "chargeTimer": 0.0,
            "chargeVx": 0.0,
            "chargeVy": 0.0,
            "burnTimer": 0.0,
            "burnDps": 0.0,
            "burnOwner": "",
            "hitFlash": 0.0,
        }
        self.zombies.append(z)
        return z

    # ---- Chiến đấu, Đạn đạo & Kỹ năng -------------------------------------- #
    def _weapon_mag_cap(self, sv: dict, wid: str) -> int:
        base = WEAPONS[wid]["mag"]
        lvl = sv["perks"].get("reload", 0)
        return int(round(base * (1.0 + 0.30 * lvl)))

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
        sv["reloadUntil"] = now + w["reload"] * cls_mult * perk_mult
        self._emit("reload", mark=sv["mark"], weapon=wid)

    def _damage_zombie(self, z: dict, dmg: float, owner_mark: str, kb_x: float = 0.0, kb_y: float = 0.0) -> bool:
        """Gây sát thương lên zombie. Trả về True nếu zombie vừa bị hạ gục."""
        if z["hp"] <= 0:
            return False
        z["hp"] -= dmg
        z["hitFlash"] = 0.12
        if kb_x or kb_y:
            resist = 0.25 if z["kind"] in ("brute", "boss") else 1.0
            z["x"], z["y"] = _resolve_circle_obstacles(
                z["x"] + kb_x * resist, z["y"] + kb_y * resist, z["radius"], self._obstacles()
            )
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
                "x": z["x"],
                "y": z["y"],
                "radius": 68.0,
                "ttl": 6.5,
                "dps": 18.0,
            })
            self._emit("acid", x=round(z["x"], 1), y=round(z["y"], 1), radius=68)

        # Rơi vật phẩm tiếp tế (tỷ lệ 16% hoặc 100% từ Brute/Boss)
        if z["kind"] in ("brute", "boss") or self.rng.random() < 0.16:
            pkind = self.rng.choices(["med", "ammo", "cash"], weights=[0.38, 0.37, 0.25], k=1)[0]
            self.pickups.append({
                "id": self._next_id(),
                "kind": pkind,
                "x": z["x"],
                "y": z["y"],
                "ttl": 16.0,
            })
        return True

    def _fire_weapon(self, sv: dict, now: float) -> None:
        if not sv["alive"] or sv["downed"] or sv["reloadUntil"] > now or sv["fireCd"] > now:
            return
        wid = sv["weapon"]
        w = WEAPONS[wid]
        cur_mag = sv["mag"].get(wid, 0)
        if cur_mag <= 0:
            self._trigger_reload(sv, now)
            return

        sv["mag"][wid] = cur_mag - 1
        sv["fireCd"] = now + w["rate"]
        cls_spec = CLASSES[sv["cls"]]
        dmg_mult = cls_spec["dmgMult"] * (1.0 + 0.20 * sv["perks"].get("damage", 0))
        per_dmg = w["dmg"] * dmg_mult
        obs = self._obstacles()
        base_angle = sv["aim"]
        muzzle_x = sv["x"] + math.cos(base_angle) * 20.0
        muzzle_y = sv["y"] + math.sin(base_angle) * 20.0

        tracers: list[tuple[float, float]] = []
        dead_ids: set[int] = set()

        for _ in range(w["pellets"]):
            ang = base_angle + self.rng.uniform(-w["spread"] * 0.5, w["spread"] * 0.5)
            dx = math.cos(ang)
            dy = math.sin(ang)
            end_x = muzzle_x + dx * w["range"]
            end_y = muzzle_y + dy * w["range"]

            # Kiểm tra va chạm tường / vật cản
            wall_t = 1.0
            for ob in obs:
                ht = _segment_hits_rect(muzzle_x, muzzle_y, end_x, end_y, ob)
                if ht is not None and ht < wall_t:
                    wall_t = ht
            end_x = muzzle_x + dx * w["range"] * wall_t
            end_y = muzzle_y + dy * w["range"] * wall_t

            # Kiểm tra trúng zombie dọc theo tia bắn (hỗ trợ đạn xuyên pierce)
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
                killed = self._damage_zombie(z, per_dmg, sv["mark"], dx * kb, dy * kb)
                if w["burn"] > 0 and not killed:
                    z["burnTimer"] = 3.2
                    z["burnDps"] = max(z["burnDps"], w["burn"] * dmg_mult)
                    z["burnOwner"] = sv["mark"]
                if killed:
                    dead_ids.add(z["id"])
                if pierced >= w["pierce"]:
                    break

            tx = muzzle_x + (end_x - muzzle_x) * (final_t if pierced >= w["pierce"] else 1.0)
            ty = muzzle_y + (end_y - muzzle_y) * (final_t if pierced >= w["pierce"] else 1.0)
            tracers.append((round(tx, 1), round(ty, 1)))

        if dead_ids:
            self.zombies = [z for z in self.zombies if z["hp"] > 0]

        self._emit(
            "shot",
            mark=sv["mark"],
            weapon=wid,
            x=round(muzzle_x, 1),
            y=round(muzzle_y, 1),
            aim=round(base_angle, 3),
            pts=tracers[:4],
            color=w["color"],
        )
        if sv["mag"][wid] <= 0:
            self._trigger_reload(sv, now)

    def _throw_grenade(self, sv: dict, target_x: float, target_y: float) -> None:
        if not sv["alive"] or sv["downed"] or sv["grenades"] <= 0:
            return
        sv["grenades"] -= 1
        dx = target_x - sv["x"]
        dy = target_y - sv["y"]
        d = math.hypot(dx, dy)
        max_throw = 380.0
        if d > max_throw and d > 1e-6:
            target_x = sv["x"] + (dx / d) * max_throw
            target_y = sv["y"] + (dy / d) * max_throw
        target_x = _clamp(target_x, 30.0, ARENA_W - 30.0)
        target_y = _clamp(target_y, 30.0, ARENA_H - 30.0)
        self.projectiles.append({
            "id": self._next_id(),
            "kind": "grenade",
            "owner": sv["mark"],
            "x": sv["x"],
            "y": sv["y"],
            "sx": sv["x"],
            "sy": sv["y"],
            "tx": target_x,
            "ty": target_y,
            "t": 0.0,
            "dur": 0.58,
            "radius": 135.0,
            "dmg": 195.0 * (1.0 + 0.18 * sv["perks"].get("damage", 0)),
        })

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
        self.turrets.append({
            "id": self._next_id(),
            "owner": sv["mark"],
            "x": tx,
            "y": ty,
            "aim": sv["aim"],
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

    def _damage_survivor(self, sv: dict, dmg: float, now: float) -> None:
        if not sv["alive"] or sv["downed"] or sv["dashUntil"] > now:
            return
        if sv["armor"] > 0:
            absorbed = min(sv["armor"], dmg * 0.65)
            sv["armor"] = max(0.0, sv["armor"] - absorbed)
            dmg -= absorbed
        sv["hp"] -= dmg
        if sv["hp"] <= 0:
            sv["hp"] = 0.0
            sv["firing"] = False
            # Nếu còn đồng đội khác đứng vững -> rơi vào trạng thái Gục Ngã (Downed) chờ cứu!
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

    # ---- Mua sắm trong Armory Shop ----------------------------------------- #
    def _buy_item(self, sv: dict, item: str) -> None:
        if not sv["alive"] and self.phase != "shop":
            raise GameError("Bạn chưa thể mua đồ lúc này.")

        if item in WEAPONS:
            w = WEAPONS[item]
            if item in sv["weapons"]:
                # Đã có súng -> nạp đầy đạn với nửa giá (tối thiểu 80$)
                refill_cost = max(80, w["cost"] // 3)
                if sv["money"] < refill_cost:
                    raise GameError(f"Cần ${refill_cost} để nạp đầy đạn {w['name']}.")
                sv["money"] -= refill_cost
                sv["mag"][item] = self._weapon_mag_cap(sv, item)
                sv["reserve"][item] = w["reserve"]
                return
            if sv["money"] < w["cost"]:
                raise GameError(f"Không đủ tiền (cần ${w['cost']}).")
            sv["money"] -= w["cost"]
            sv["weapons"].append(item)
            sv["mag"][item] = self._weapon_mag_cap(sv, item)
            sv["reserve"][item] = w["reserve"]
            sv["weapon"] = item
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
                sv["armor"] = min(sv["maxArmor"], sv["armor"] + 45.0)
            elif item == "reload":
                wid = sv["weapon"]
                sv["mag"][wid] = self._weapon_mag_cap(sv, wid)
            return

        if item == "medkit":
            cost = SHOP_ITEMS["medkit"]["cost"]
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["hp"] = min(sv["maxHp"], sv["hp"] + 65.0)
            sv["armor"] = min(sv["maxArmor"], sv["armor"] + 30.0)
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
            return

        if item == "grenade":
            cost = SHOP_ITEMS["grenade"]["cost"]
            if sv["grenades"] >= 5:
                raise GameError("Đã mang tối đa 5 lựu đạn.")
            if sv["money"] < cost:
                raise GameError(f"Cần ${cost}.")
            sv["money"] -= cost
            sv["grenades"] = min(5, sv["grenades"] + 2)
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

        raise GameError("Vật phẩm không tồn tại.")

    # ---- Vòng lặp mô phỏng 15 Hz (Server Authoritative Tick) --------------- #
    def tick(self, dt_override: float | None = None) -> bool:
        if not self.in_progress():
            return False
        now = time.time()
        dt = dt_override if dt_override is not None else min(0.12, max(0.01, now - self.last_tick_at))
        self.last_tick_at = now

        if self.phase == "shop":
            # AI Bots tự mua đồ ở đầu pha shop
            self._step_bots(dt, now)
            humans = [m for m in self.survivors if (p := self.seat(m)) is not None and not p.bot]
            all_ready = bool(humans) and all(self.survivors[m]["readyShop"] for m in humans)
            if all_ready or now >= self.shop_deadline:
                self._begin_wave(self.wave + 1)
            return True

        if self.phase != "wave":
            return False

        # 1. Step AI Survivor Bots
        self._step_bots(dt, now)

        obs = self._obstacles()

        # 2. Cập nhật vị trí chiến binh, thay đạn, hào quang Medic, cứu đồng đội
        for m, sv in self.survivors.items():
            if not sv["alive"]:
                continue
            if sv["downed"]:
                sv["bleedout"] -= dt
                # Tìm đồng đội đang đứng trong vòng cứu
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
                        sv["armor"] = max(sv["armor"], 20.0)
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

            # Di chuyển (Dash hoặc đi bộ)
            if sv["dashUntil"] > now:
                nx = sv["x"] + sv["dashVx"] * dt
                ny = sv["y"] + sv["dashVy"] * dt
            else:
                spd = CLASSES[sv["cls"]]["speed"] * (1.0 + 0.12 * sv["perks"].get("speed", 0))
                # Bị chậm lại khi đứng trên vũng axit
                in_acid = any(_dist(sv["x"], sv["y"], h["x"], h["y"]) <= h["radius"] for h in self.hazards)
                if in_acid:
                    spd *= 0.62
                vx, vy = sv["vx"], sv["vy"]
                mag = math.hypot(vx, vy)
                if mag > 1.0:
                    vx, vy = vx / mag, vy / mag
                nx = sv["x"] + vx * spd * dt
                ny = sv["y"] + vy * spd * dt
            sv["x"], sv["y"] = _resolve_circle_obstacles(nx, ny, PLAYER_RADIUS, obs)

            # Hào quang Quân Y (Medic) hồi máu nhẹ cho đồng đội gần
            aura = CLASSES[sv["cls"]]["healAura"]
            if aura > 0:
                for om, other in self.survivors.items():
                    if other["alive"] and not other["downed"] and _dist(sv["x"], sv["y"], other["x"], other["y"]) <= 140.0:
                        other["hp"] = min(other["maxHp"], other["hp"] + aura * dt)

            # Bắn liên thanh khi giữ cò
            if sv["firing"]:
                self._fire_weapon(sv, now)

        # 3. Sinh thêm Zombie từ hàng đợi đợt hiện tại
        max_active = min(38, 12 + self.wave * 2 + len(self.survivors) * 3)
        if self.wave_remaining_to_spawn and len(self.zombies) < max_active:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                kind = self.wave_remaining_to_spawn.pop(0)
                self._spawn_one_zombie(kind)
                self.spawn_timer = max(0.28, 1.05 - self.wave * 0.05)

        # 4. Cập nhật Trụ súng Sentry tự động
        next_turrets: list[dict] = []
        for t in self.turrets:
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
                t["fireCd"] = now + t["rate"]
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

        # 5. Cập nhật Đạn bay (Lựu đạn & Cầu axit Spitter/Boss)
        next_proj: list[dict] = []
        for pr in self.projectiles:
            if pr["kind"] == "grenade":
                pr["t"] += dt
                ratio = min(1.0, pr["t"] / pr["dur"])
                pr["x"] = pr["sx"] + (pr["tx"] - pr["sx"]) * ratio
                pr["y"] = pr["sy"] + (pr["ty"] - pr["sy"]) * ratio
                if ratio >= 1.0:
                    # Nổ tung diện rộng!
                    for z in list(self.zombies):
                        d = _dist(pr["x"], pr["y"], z["x"], z["y"])
                        if d <= pr["radius"] + z["radius"]:
                            falloff = max(0.35, 1.0 - d / (pr["radius"] + 40.0))
                            ang = math.atan2(z["y"] - pr["y"], z["x"] - pr["x"])
                            self._damage_zombie(z, pr["dmg"] * falloff, pr["owner"], math.cos(ang) * 28.0, math.sin(ang) * 28.0)
                    self.zombies = [z for z in self.zombies if z["hp"] > 0]
                    self._emit("boom", x=round(pr["x"], 1), y=round(pr["y"], 1), radius=int(pr["radius"]))
                else:
                    next_proj.append(pr)
            else:
                # Đạn axit Spitter / Boss
                pr["x"] += pr["vx"] * dt
                pr["y"] += pr["vy"] * dt
                pr["ttl"] -= dt
                hit_wall = any(
                    ob["x"] <= pr["x"] <= ob["x"] + ob["w"] and ob["y"] <= pr["y"] <= ob["y"] + ob["h"]
                    for ob in obs
                )
                if pr["ttl"] <= 0 or hit_wall or not (0 <= pr["x"] <= ARENA_W and 0 <= pr["y"] <= ARENA_H):
                    continue
                hit_player = False
                for sv in self.survivors.values():
                    if sv["alive"] and not sv["downed"] and _dist(pr["x"], pr["y"], sv["x"], sv["y"]) <= PLAYER_RADIUS + 7.0:
                        self._damage_survivor(sv, pr["dmg"], now)
                        hit_player = True
                        break
                if not hit_player:
                    next_proj.append(pr)
        self.projectiles = next_proj

        # 6. Cập nhật Vũng Axit độc trên mặt đất
        next_hazards: list[dict] = []
        for hz in self.hazards:
            hz["ttl"] -= dt
            if hz["ttl"] <= 0:
                continue
            next_hazards.append(hz)
            for sv in self.survivors.values():
                if sv["alive"] and not sv["downed"] and _dist(sv["x"], sv["y"], hz["x"], hz["y"]) <= hz["radius"]:
                    self._damage_survivor(sv, hz["dps"] * dt, now)
        self.hazards = next_hazards

        # 7. Cập nhật Vật phẩm rơi (Pickups)
        next_pickups: list[dict] = []
        for pk in self.pickups:
            pk["ttl"] -= dt
            if pk["ttl"] <= 0:
                continue
            taken = False
            for sv in self.survivors.values():
                if not sv["alive"] or sv["downed"]:
                    continue
                if _dist(sv["x"], sv["y"], pk["x"], pk["y"]) <= PLAYER_RADIUS + 20.0:
                    if pk["kind"] == "med":
                        sv["hp"] = min(sv["maxHp"], sv["hp"] + 32.0)
                    elif pk["kind"] == "ammo":
                        wid = sv["weapon"]
                        if WEAPONS[wid]["reserve"] != -1:
                            sv["reserve"][wid] = sv["reserve"].get(wid, 0) + WEAPONS[wid]["mag"] * 2
                    else:
                        sv["money"] += 75
                    self._emit("pickup", mark=sv["mark"], kind=pk["kind"], x=round(pk["x"], 1), y=round(pk["y"], 1))
                    taken = True
                    break
            if not taken:
                next_pickups.append(pk)
        self.pickups = next_pickups

        # 8. Cập nhật AI & Va chạm Zombie
        standing = [sv for sv in self.survivors.values() if sv["alive"] and not sv["downed"]]
        for z in list(self.zombies):
            if z["hp"] <= 0:
                continue
            if z["hitFlash"] > 0:
                z["hitFlash"] = max(0.0, z["hitFlash"] - dt)
            if z["burnTimer"] > 0:
                z["burnTimer"] -= dt
                if self._damage_zombie(z, z["burnDps"] * dt, z["burnOwner"]):
                    continue

            if not standing:
                continue
            target_sv = min(standing, key=lambda s: _dist(z["x"], z["y"], s["x"], s["y"]))
            dx = target_sv["x"] - z["x"]
            dy = target_sv["y"] - z["y"]
            d = math.hypot(dx, dy) or 1.0
            nx_dir, ny_dir = dx / d, dy / d

            # Kỹ năng đặc biệt theo chủng Zombie
            z["specialCd"] -= dt
            if z["kind"] == "spitter" and 160.0 <= d <= 420.0 and z["specialCd"] <= 0:
                z["specialCd"] = self.rng.uniform(2.6, 3.8)
                self.projectiles.append({
                    "id": self._next_id(),
                    "kind": "acid",
                    "x": z["x"],
                    "y": z["y"],
                    "vx": nx_dir * 310.0,
                    "vy": ny_dir * 310.0,
                    "dmg": z["dmg"],
                    "ttl": 1.6,
                })
            elif z["kind"] in ("brute", "boss") and 95.0 <= d <= 360.0 and z["specialCd"] <= 0:
                z["specialCd"] = 4.8 if z["kind"] == "brute" else 4.2
                z["chargeTimer"] = 0.65
                spd_charge = 330.0 if z["kind"] == "brute" else 310.0
                z["chargeVx"] = nx_dir * spd_charge
                z["chargeVy"] = ny_dir * spd_charge
                if z["kind"] == "boss":
                    # Boss bắn vòng đạn độc 8 hướng & gọi thêm 2 Runner
                    for k in range(8):
                        ang = (math.tau / 8.0) * k
                        self.projectiles.append({
                            "id": self._next_id(),
                            "kind": "acid",
                            "x": z["x"],
                            "y": z["y"],
                            "vx": math.cos(ang) * 250.0,
                            "vy": math.sin(ang) * 250.0,
                            "dmg": 15.0,
                            "ttl": 1.9,
                        })
                    if len(self.zombies) < 34:
                        self._spawn_one_zombie("runner")
                        self._spawn_one_zombie("runner")

            if z["chargeTimer"] > 0:
                z["chargeTimer"] -= dt
                mvx, mvy = z["chargeVx"], z["chargeVy"]
            elif z["kind"] == "spitter" and d < 220.0:
                mvx, mvy = -nx_dir * z["speed"] * 0.55, -ny_dir * z["speed"] * 0.55
            else:
                # Lách nhẹ sang bên nếu bị kẹt vật cản
                mvx, mvy = nx_dir * z["speed"], ny_dir * z["speed"]
                if z["kind"] == "runner":
                    wobble = math.sin(now * 7.0 + z["id"]) * 0.35
                    mvx, mvy = (
                        mvx * math.cos(wobble) - mvy * math.sin(wobble),
                        mvx * math.sin(wobble) + mvy * math.cos(wobble),
                    )

            z["vx"], z["vy"] = mvx, mvy
            z["x"], z["y"] = _resolve_circle_obstacles(z["x"] + mvx * dt, z["y"] + mvy * dt, z["radius"], obs)

            # Tấn công cận chiến
            z["atkCd"] = max(0.0, z["atkCd"] - dt)
            if d <= z["radius"] + PLAYER_RADIUS + 8.0 and z["atkCd"] <= 0:
                z["atkCd"] = 0.85
                self._damage_survivor(target_sv, z["dmg"], now)

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
            # Hoàn thành đợt hiện tại!
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
            self.system(f"✨ Đã dọn sạch Đợt {self.wave}! (+${bonus} thưởng) — Mở Cửa Hàng Tiếp Tế {int(SHOP_SECONDS)}s!")
            return True

        return True

    def _step_bots(self, dt: float, now: float) -> None:
        from bot_zombie import step_bot_survivor
        for p in self.bot_players():
            sv = self.survivors.get(p.mark)
            if sv is not None:
                step_bot_survivor(self, p, sv, dt, now)

    def _finish_match(self, victory: bool) -> None:
        self.victory = victory
        self.phase = "finished"
        self.status = "finished"
        self.rematch.clear()
        self.projectiles.clear()
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
    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        mark = player.mark
        super().stand(uid)
        self.survivors.pop(mark, None)

    def resign(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        self._finish_match(victory=False)

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ chiến binh trong đội mới xin chơi lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        seated = set(self._seated_marks())
        if seated and self.rematch >= seated:
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
                sv["vx"] = _clamp(float(msg.get("vx", 0.0)), -1.0, 1.0)
                sv["vy"] = _clamp(float(msg.get("vy", 0.0)), -1.0, 1.0)
                sv["aim"] = float(msg.get("aim", sv["aim"]))
                sv["firing"] = bool(msg.get("firing", False))
                if sv["firing"] and self.phase == "wave":
                    self._fire_weapon(sv, now)
            return

        if action == "shoot":
            if self.phase == "wave" and sv["alive"] and not sv["downed"]:
                if "aim" in msg:
                    sv["aim"] = float(msg["aim"])
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
            if self.phase == "wave":
                self._do_dash(sv, now)
            return

        if action == "grenade":
            if self.phase == "wave":
                tx = float(msg.get("tx", sv["x"] + math.cos(sv["aim"]) * 220.0))
                ty = float(msg.get("ty", sv["y"] + math.sin(sv["aim"]) * 220.0))
                self._throw_grenade(sv, tx, ty)
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
        boss_z = next((z for z in self.zombies if z["kind"] == "boss" and z["hp"] > 0), None)
        sv_out = []
        for m, sv in self.survivors.items():
            p = self.seat(m)
            sv_out.append({
                "mark": m,
                "name": p.name if p else m,
                "color": p.color if p else "#38bdf8",
                "bot": p.bot if p else False,
                "cls": sv["cls"],
                "x": round(sv["x"], 1),
                "y": round(sv["y"], 1),
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
                "mag": dict(sv["mag"]),
                "reserve": dict(sv["reserve"]),
                "reloading": sv["reloadUntil"] > now,
                "dashReady": max(0.0, round(sv["dashCd"] - now, 2)),
                "dashing": sv["dashUntil"] > now,
                "grenades": sv["grenades"],
                "turrets": sv["turrets"],
                "money": sv["money"],
                "score": sv["score"],
                "kills": sv["kills"],
                "revives": sv["revives"],
                "perks": dict(sv["perks"]),
                "readyShop": sv["readyShop"],
            })

        return {
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
            "boss": {
                "hp": round(boss_z["hp"], 1),
                "maxHp": round(boss_z["maxHp"], 1),
            } if boss_z else None,
            "survivors": sv_out,
            "zombies": [
                {
                    "id": z["id"],
                    "kind": z["kind"],
                    "x": round(z["x"], 1),
                    "y": round(z["y"], 1),
                    "hp": round(z["hp"], 1),
                    "maxHp": round(z["maxHp"], 1),
                    "r": z["radius"],
                    "burn": z["burnTimer"] > 0,
                    "flash": z["hitFlash"] > 0,
                    "charging": z["chargeTimer"] > 0,
                }
                for z in self.zombies
            ],
            "projectiles": [
                {
                    "id": pr["id"],
                    "kind": pr["kind"],
                    "x": round(pr["x"], 1),
                    "y": round(pr["y"], 1),
                    "t": round(pr.get("t", 0.0) / max(0.01, pr.get("dur", 1.0)), 2) if pr["kind"] == "grenade" else 0.0,
                }
                for pr in self.projectiles
            ],
            "hazards": [
                {"id": h["id"], "x": round(h["x"], 1), "y": round(h["y"], 1), "r": h["radius"], "ttl": round(h["ttl"], 1)}
                for h in self.hazards
            ],
            "turrets": [
                {"id": t["id"], "x": round(t["x"], 1), "y": round(t["y"], 1), "aim": round(t["aim"], 2), "ammo": t["ammo"], "maxAmmo": t["maxAmmo"]}
                for t in self.turrets
            ],
            "pickups": [
                {"id": pk["id"], "kind": pk["kind"], "x": round(pk["x"], 1), "y": round(pk["y"], 1)}
                for pk in self.pickups
            ],
            "events": self.events[-30:],
            "catalog": {
                "classes": {k: {"label": v["label"], "hp": v["hp"], "armor": v["armor"], "speed": v["speed"]} for k, v in CLASSES.items()},
                "weapons": {k: {"name": v["name"], "cost": v["cost"], "dmg": v["dmg"], "mag": v["mag"], "color": v["color"]} for k, v in WEAPONS.items()},
                "weaponOrder": list(WEAPON_ORDER),
                "perks": PERKS,
                "items": SHOP_ITEMS,
            },
            "seatedCount": len(self._seated_marks()),
        }
