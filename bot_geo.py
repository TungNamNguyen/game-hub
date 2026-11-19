"""Bot cho trò Địa Đồ (GeoGuessr) — hỗ trợ đủ 3 thể thức (Classic, Streak, Duel/Team) & 8 bản đồ."""
from __future__ import annotations

import math
import random

from bots import Bot
from geoguessr import (
    FALLBACK_STREET_POOLS,
    LANDMARK_POOLS,
    extract_region,
    haversine_km,
    normalize_difficulty,
)


def _offset_coords(lat: float, lng: float, dist_km: float, bearing_rad: float) -> tuple[float, float]:
    """Dịch chuyển tọa độ (lat, lng) đi ``dist_km`` theo góc ``bearing_rad`` trên mặt cầu."""
    dlat = (dist_km * math.cos(bearing_rad)) / 111.32
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    dlng = (dist_km * math.sin(bearing_rad)) / (111.32 * cos_lat)
    nlat = max(-85.0, min(85.0, lat + dlat))
    nlng = ((lng + dlng + 180.0) % 360.0) - 180.0
    return round(nlat, 5), round(nlng, 5)


class GeoBot(Bot):
    CHANNEL = "geo"

    @property
    def think_delay(self) -> float:
        return {"easy": 1.8, "normal": 1.5, "hard": 1.2}.get(self.level, 1.5)

    def _mode_pool(self, mode: str) -> list[dict]:
        pool: list[dict] = []
        pool.extend(LANDMARK_POOLS.get(mode) or [])
        pool.extend(FALLBACK_STREET_POOLS.get(mode) or [])
        if not pool:
            pool.extend(LANDMARK_POOLS.get("world") or [])
            pool.extend(FALLBACK_STREET_POOLS.get("world") or [])
        return pool

    def _pick_near_distance(
        self,
        rng: random.Random,
        target: dict,
        pool: list[dict],
        desired_km: float,
    ) -> tuple[float, float]:
        """Chọn một tọa độ đất liền thật trong pool gần khoảng cách mục tiêu để tránh ghim ra biển."""
        t_lat, t_lng = float(target["lat"]), float(target["lng"])
        if desired_km <= 35.0 or not pool:
            jitter = max(0.2, desired_km)
            return _offset_coords(t_lat, t_lng, jitter, rng.uniform(0.0, math.tau))

        # Lấy mẫu tối đa 160 ứng viên để tính nhanh (<1ms)
        sample = pool if len(pool) <= 160 else rng.sample(pool, 160)
        scored: list[tuple[float, dict, float]] = []
        for item in sample:
            d = haversine_km(t_lat, t_lng, item["lat"], item["lng"])
            if d < 0.05:
                continue
            scored.append((abs(d - desired_km), item, d))
        if not scored:
            return _offset_coords(t_lat, t_lng, desired_km, rng.uniform(0.0, math.tau))

        scored.sort(key=lambda x: x[0])
        top = scored[: min(5, len(scored))]
        _, chosen, chosen_dist = rng.choice(top)

        # Nếu ứng viên tốt nhất vẫn lệch quá xa khoảng cách mong muốn, nội suy dọc đường nối về phía đáp án
        if chosen_dist > desired_km * 1.8 and chosen_dist > 1.0:
            ratio = min(1.0, desired_km / chosen_dist)
            lat = t_lat + (chosen["lat"] - t_lat) * ratio
            dlng = ((chosen["lng"] - t_lng + 180.0) % 360.0) - 180.0
            lng = ((t_lng + dlng * ratio + 180.0) % 360.0) - 180.0
            return _offset_coords(lat, lng, min(12.0, desired_km * 0.15), rng.uniform(0.0, math.tau))

        jitter = min(18.0, desired_km * 0.12)
        return _offset_coords(chosen["lat"], chosen["lng"], jitter, rng.uniform(0.0, math.tau))

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        if not room.in_progress() or room.phase != "guessing":
            return []
        if mark in room.guesses:
            return []
        fmt = room.config.get("format", "classic")
        if fmt == "streak" and mark in room.eliminated:
            return []
        target = room._current_target()
        if target is None:
            return []

        rng = random.Random()
        mode = room.mode
        pool = self._mode_pool(mode)
        max_err = room._max_error_km()
        is_landmark = normalize_difficulty(room.config.get("difficulty", "global")) == "landmark"
        t_lat, t_lng = float(target["lat"]), float(target["lng"])

        if fmt == "streak":
            base_acc = {"easy": 0.55, "normal": 0.75, "hard": 0.90}.get(self.level, 0.75)
            if is_landmark:
                base_acc = min(0.95, base_acc + 0.05)
            target_reg = extract_region(target, mode).lower()
            near_km = 45.0 if mode == "vietnam" else 90.0

            if rng.random() < base_acc:
                # Đoán đúng quốc gia / địa phương
                same_reg = [
                    x for x in pool
                    if extract_region(x, mode).lower() == target_reg
                ]
                if same_reg and self.level != "hard":
                    anchor = rng.choice(same_reg)
                    lat, lng = _offset_coords(anchor["lat"], anchor["lng"], rng.uniform(0.5, 8.0), rng.uniform(0.0, math.tau))
                else:
                    lat, lng = _offset_coords(t_lat, t_lng, rng.uniform(0.3, near_km * 0.45), rng.uniform(0.0, math.tau))
                return [("guess", {"lat": lat, "lng": lng})]

            # Đoán nhầm sang khu vực/quốc gia khác gần đó trong cùng bản đồ
            diff_reg = [
                x for x in pool
                if extract_region(x, mode).lower() != target_reg
                and haversine_km(t_lat, t_lng, x["lat"], x["lng"]) > near_km * 1.4
            ]
            if diff_reg:
                sample = diff_reg if len(diff_reg) <= 80 else rng.sample(diff_reg, 80)
                sample.sort(key=lambda x: haversine_km(t_lat, t_lng, x["lat"], x["lng"]))
                pick = rng.choice(sample[: min(12, len(sample))])
                lat, lng = _offset_coords(pick["lat"], pick["lng"], rng.uniform(1.0, 15.0), rng.uniform(0.0, math.tau))
            else:
                lat, lng = _offset_coords(t_lat, t_lng, max(near_km * 2.5, max_err * 0.15), rng.uniform(0.0, math.tau))
            return [("guess", {"lat": lat, "lng": lng})]

        # Chế độ Classic & Duel / Team: tính sai số mục tiêu theo độ khó & thang bản đồ
        bands = {
            "easy": (0.04, 0.22),
            "normal": (0.015, 0.08),
            "hard": (0.002, 0.03),
        }
        lo, hi = bands.get(self.level, (0.015, 0.08))
        if is_landmark:
            lo *= 0.65
            hi *= 0.65
        # Dùng phân bố nghiêng nhẹ về giữa dải để điểm số tự nhiên như người chơi thật
        ratio = rng.triangular(lo, hi, (lo + hi) * 0.45)
        desired_km = max(0.3, ratio * max_err)
        lat, lng = self._pick_near_distance(rng, target, pool, desired_km)
        return [("guess", {"lat": lat, "lng": lng})]
