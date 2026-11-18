"""AI Bot cho trò Cờ Cá Ngựa (Ludo) với 3 mức: Dễ, Thường, Khó."""

from __future__ import annotations

import random

from bots import Bot
from ludo import START_OFFSET, TRACK_LEN


class LudoBot(Bot):
    CHANNEL = "ludo"
    THINK_DELAY = {"easy": 0.45, "normal": 0.65, "hard": 0.8}

    def actions(self, room, mark: str):
        if not room.in_progress() or room.turn != mark:
            return []
        if room.phase == "roll":
            return [("roll", {})]
        if room.phase != "move" or not room.legal_moves:
            return []

        rng = random.Random()
        moves = list(room.legal_moves)
        if len(moves) == 1:
            mv = moves[0]
            return [("move", {"piece": mv.piece, "kind": mv.kind})]

        if self.level == "easy":
            # Mức dễ: ưu tiên nhẹ ăn quân/vào chuồng, còn lại chọn ngẫu nhiên.
            if rng.random() < 0.55:
                mv = rng.choice(moves)
                return [("move", {"piece": mv.piece, "kind": mv.kind})]
            best = max(moves, key=lambda m: self._score_simple(m) + rng.uniform(-25, 25))
            return [("move", {"piece": best.piece, "kind": best.kind})]

        if self.level == "normal":
            best = max(moves, key=lambda m: self._score_normal(room, mark, m) + rng.uniform(-8, 8))
            return [("move", {"piece": best.piece, "kind": best.kind})]

        # Mức khó: đánh giá rủi ro bị đá & đá hậu + giá trị quân địch bị đá
        best = max(moves, key=lambda m: self._score_hard(room, mark, m) + rng.uniform(-2, 2))
        return [("move", {"piece": best.piece, "kind": best.kind})]

    @staticmethod
    def _score_simple(mv) -> float:
        if mv.kind in ("enter_home", "climb_home"):
            return 100.0
        if mv.kind in ("kick", "kick_back", "deploy_kick"):
            return 85.0
        if mv.kind == "deploy":
            return 60.0
        return float(mv.to_pos)

    @staticmethod
    def _score_normal(room, mark: str, mv) -> float:
        if mv.kind in ("kick", "kick_back", "deploy_kick"):
            enemy_pos = 0
            if mv.kicked_color and mv.kicked_piece >= 0:
                enemy_pos = max(0, room.pieces[mv.kicked_color][mv.kicked_piece])
            return 135.0 + enemy_pos * 1.5
        if mv.kind == "enter_home":
            return 125.0 + (mv.to_pos - 55) * 4.0
        if mv.kind == "climb_home":
            return 120.0 + (mv.to_pos - 55) * 3.0
        if mv.kind == "deploy":
            return 90.0
        return 20.0 + mv.to_pos * 0.9

    @staticmethod
    def _danger_at(room, mark: str, global_idx: int | None) -> float:
        """Ước lượng mức độ nguy hiểm nếu đứng ở ô global_idx."""
        if global_idx is None:
            return 0.0
        back_kick = bool(room.config.get("backKick", True))
        risk = 0.0
        for opp in room.active_seats:
            if opp == mark or opp in room.eliminated:
                continue
            for opp_pos in room.pieces.get(opp, []):
                if not (0 <= opp_pos < TRACK_LEN):
                    continue
                opp_g = (START_OFFSET[opp] + opp_pos) % TRACK_LEN
                # Đối thủ ở phía sau mình 1..6 bước -> có thể đá tiến
                fwd_dist = (global_idx - opp_g) % TRACK_LEN
                if 1 <= fwd_dist <= 6:
                    risk += 24.0
                # Đối thủ ở phía trước mình 1..6 bước (và không vượt quá cửa chuồng) -> có thể Đá Hậu
                if back_kick:
                    bwd_dist = (opp_g - global_idx) % TRACK_LEN
                    if 1 <= bwd_dist <= 6 and opp_pos - bwd_dist >= 0:
                        risk += 16.0
        return risk

    def _score_hard(self, room, mark: str, mv) -> float:
        score = self._score_normal(room, mark, mv)
        # Thưởng nếu né khỏi ô đang gặp nguy hiểm
        if mv.from_global is not None:
            score += self._danger_at(room, mark, mv.from_global) * 0.85
        # Phạt nếu bước tới ô có nguy cơ bị đá / đá hậu (trừ khi vừa đá để lấy thêm lượt)
        if mv.to_global is not None:
            penalty = self._danger_at(room, mark, mv.to_global)
            if mv.kind in ("kick", "kick_back", "deploy_kick"):
                penalty *= 0.35
            score -= penalty
        # Rời chuồng đích sớm hoặc đưa quân gần cửa chuồng về đích an toàn
        if mv.kind == "move" and mv.to_pos == 55:
            score += 45.0
        return score
