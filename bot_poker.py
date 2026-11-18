"""Máy chơi Xì Tố (No-Limit Texas Hold'em AI Bot).

Hỗ trợ cả bàn Cash và Giải đấu với 3 mức khó (easy / normal / hard) và các
tính cách khác nhau (Đánh chắc, Hay bluff, Hổ báo) dựa trên sức mạnh tay bài,
pot odds, vị trí và tình huống bàn. Máy chỉ đọc bài riêng của chính mình và
thông tin công khai trên bàn — tuyệt đối không nhìn trộm bài đối thủ.
"""

from __future__ import annotations

from bots import Bot
from poker import FLOP, PREFLOP, RIVER, TURN
from poker_hand import (
    FLUSH,
    FULL_HOUSE,
    HIGH_CARD,
    ONE_PAIR,
    QUADS,
    STRAIGHT,
    STRAIGHT_FLUSH,
    TRIPS,
    TWO_PAIR,
    best_hand,
)

# (Tên hiển thị, tính cách: tag | bluff | lag)
BOT_PROFILES: tuple[tuple[str, str], ...] = (
    ("Minh Chắc", "tag"),
    ("Lan Bịp", "bluff"),
    ("Hùng Hổ", "lag"),
    ("Bác Năm", "tag"),
    ("Tú Liều", "bluff"),
)

_PERSONA_CFG = {
    "tag": {"loose": -0.05, "aggr": 0.10, "bluff": 0.08},
    "bluff": {"loose": 0.04, "aggr": 0.16, "bluff": 0.28},
    "lag": {"loose": 0.09, "aggr": 0.22, "bluff": 0.18},
}


def preflop_strength(hole: list) -> float:
    """Ước lượng sức mạnh 2 lá tẩy preflop theo thang [0.0, 1.0]."""
    if len(hole) < 2:
        return 0.25
    r1, s1 = hole[0].value, hole[0].suit
    r2, s2 = hole[1].value, hole[1].suit
    hi, lo = (r1, r2) if r1 >= r2 else (r2, r1)
    suited = s1 == s2
    gap = hi - lo

    if hi == lo:
        # AA -> ~0.98, KK -> ~0.93, QQ -> ~0.88, JJ -> ~0.83, 22 -> ~0.52
        return min(0.99, 0.48 + (hi - 2) * 0.042)

    score = 0.22 + (hi - 6) * 0.025 + (lo - 2) * 0.014
    if suited:
        score += 0.065
    if gap == 1:
        score += 0.055
    elif gap == 2:
        score += 0.03
    elif gap >= 4:
        score -= 0.055

    # Bonus cho các hand bài cao (AK, AQ, KQ, AJ, QJ)
    if hi >= 12 and lo >= 10:
        score += 0.10
    if hi == 14 and lo >= 12:
        score += 0.09

    return max(0.08, min(0.92, score))


def _draw_bonus(cards: list[tuple[int, str]], street: str) -> float:
    """Cộng equity cho bài chờ Thùng hoặc Sảnh ở Flop / Turn."""
    if street not in (FLOP, TURN) or len(cards) < 5:
        return 0.0
    bonus = 0.0
    suit_counts: dict[str, int] = {}
    for _, s in cards:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    if max(suit_counts.values(), default=0) == 4:
        bonus += 0.17 if street == FLOP else 0.11

    uniq = sorted({r for r, _ in cards})
    if 14 in uniq:
        uniq = [1] + uniq
    for i in range(len(uniq) - 3):
        span = uniq[i + 3] - uniq[i]
        if span == 3:
            bonus += 0.14 if street == FLOP else 0.09
            break
        if span == 4:
            bonus += 0.07 if street == FLOP else 0.04
            break
    return min(0.24, bonus)


def postflop_strength(hole: list, board: list, street: str) -> float:
    """Ước lượng sức mạnh sau khi có bài chung theo thang [0.0, 1.0]."""
    hole_tuples = [c.as_tuple() for c in hole]
    board_tuples = [c.as_tuple() for c in board]
    all_cards = hole_tuples + board_tuples
    if len(all_cards) < 5:
        return preflop_strength(hole)

    best = best_hand(all_cards)
    cat = best.category
    tb_top = best.tiebreak[0] if best.tiebreak else 7

    base_map = {
        HIGH_CARD: 0.16 + max(0, tb_top - 7) * 0.015,
        ONE_PAIR: 0.42 + (tb_top - 2) * 0.018,
        TWO_PAIR: 0.67 + (tb_top - 2) * 0.008,
        TRIPS: 0.78 + (tb_top - 2) * 0.006,
        STRAIGHT: 0.85,
        FLUSH: 0.89,
        FULL_HOUSE: 0.94,
        QUADS: 0.98,
        STRAIGHT_FLUSH: 0.995,
    }
    strength = base_map.get(cat, 0.30)

    # Nếu lá cao trên bàn tự tạo bài mà 2 lá tẩy không đóng góp đáng kể -> hạ nhẹ
    if len(board_tuples) == 5:
        board_only = best_hand(board_tuples)
        if board_only.key() == best.key():
            strength = min(strength, 0.36)

    # Đếm đôi tạo từ bài chung vs bài riêng
    if cat == ONE_PAIR:
        board_ranks = [r for r, _ in board_tuples]
        hole_ranks = [r for r, _ in hole_tuples]
        if any(r in board_ranks for r in hole_ranks):
            top_board = max(board_ranks, default=0)
            if max(r for r in hole_ranks if r in board_ranks) >= top_board:
                strength += 0.06   # Top pair
        elif hole_ranks[0] == hole_ranks[1] and hole_ranks[0] > max(board_ranks, default=0):
            strength += 0.10       # Overpair

    strength += _draw_bonus(all_cards, street)
    return max(0.05, min(0.995, strength))


class PokerBot(Bot):
    CHANNEL = "poker"
    THINK_DELAY = {"easy": 0.48, "normal": 0.72, "hard": 0.92}

    def _persona_for(self, room, mark: str) -> str:
        player = room.seat(mark)
        name = player.name if player else ""
        for prof_name, persona in BOT_PROFILES:
            if name.startswith(prof_name):
                return persona
        idx = list(room.SEATS).index(mark) if mark in room.SEATS else 0
        return BOT_PROFILES[idx % len(BOT_PROFILES)][1]

    def _decide_raise_amount(self, room, opts: dict, strength: float, persona: str) -> int:
        min_to = opts["minTo"]
        max_to = opts["maxTo"]
        pot = max(room.bb, opts["pot"])
        cur = opts["currentBet"]

        if room.street == PREFLOP and cur <= room.bb:
            target = int(room.bb * self.rng.choice([2.5, 3, 3.5]))
        elif cur == 0:
            frac = 0.45 if strength < 0.75 else self.rng.uniform(0.60, 0.85)
            if persona == "lag":
                frac += 0.15
            target = int(pot * frac)
        else:
            mult = 2.6 if strength < 0.82 else 3.2
            target = int(cur + max(room.min_raise, (cur - opts["myBet"]) * (mult - 1.0)))

        # Làm tròn theo bước SB cho gọn mắt giống người chơi thật
        step = max(50, room.sb)
        target = ((target + step // 2) // step) * step
        target = max(min_to, min(max_to, target))

        # Nếu đã dồn gần hết stack (>65% maxTo) thì đẩy All-in luôn cho dứt khoát
        if target >= max_to * 0.68 and (strength >= 0.74 or persona != "tag"):
            return max_to
        return target

    def _choose_action(self, room, mark: str) -> list[tuple[str, dict]]:
        if room.phase == "ritvote":
            persona = self._persona_for(room, mark)
            yes_prob = 0.75 if persona == "tag" else 0.45
            return [("rit", {"yes": self.rng.random() < yes_prob})]

        if room.phase != "betting" or room.actor != mark:
            return []

        st = room.state.get(mark)
        if st is None or not st.live or st.all_in:
            return []

        opts = room._action_options(mark)
        persona = self._persona_for(room, mark)
        pcfg = _PERSONA_CFG.get(persona, _PERSONA_CFG["tag"])

        if room.street == PREFLOP:
            strength = preflop_strength(st.hole)
        else:
            strength = postflop_strength(st.hole, room.board, room.street)

        # Điều chỉnh theo số người còn live trong pot (nhiều người cần bài mạnh hơn)
        live_count = max(2, len(room._live()))
        strength -= (live_count - 2) * 0.035

        # Áp lực vị trí (Button / SB đánh thoáng hơn một chút)
        if mark == room.button:
            strength += 0.04

        # Short stack ở giải đấu hoặc cash (< 12 BB): sẵn sàng shove với bài khá
        bb_stack = (st.chips + st.bet) / max(1, room.bb)
        if bb_stack <= 12 and strength >= 0.54 and opts["canRaise"]:
            return [("allin", {})]

        # Mức khó tác động lên độ chuẩn xác
        if self.level == "easy":
            strength += self.rng.uniform(-0.14, 0.14)
        elif self.level == "normal":
            strength += self.rng.uniform(-0.06, 0.06)
        else:
            strength += self.rng.uniform(-0.02, 0.025)

        strength += pcfg["loose"]
        to_call = opts["toCall"]
        pot = max(1, opts["pot"])
        pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0

        # ---- Chưa có ai cược / được Check ----
        if opts["canCheck"]:
            want_bet = strength >= 0.62 - pcfg["aggr"] * 0.35
            is_bluff = (
                not want_bet
                and room.street != PREFLOP
                and self.rng.random() < pcfg["bluff"] * (0.6 if self.level == "easy" else 1.0)
            )
            if (want_bet or is_bluff) and opts["canRaise"]:
                amt = self._decide_raise_amount(room, opts, strength, persona)
                if amt >= opts["maxTo"]:
                    return [("allin", {})]
                return [("bet", {"amount": amt})]
            return [("check", {})]

        # ---- Đang phải Call một mức Bet / Raise ----
        # Nếu bài rất mạnh -> có xu hướng Raise/Tố lại
        raise_thresh = 0.78 - pcfg["aggr"] * 0.25
        if self.level == "easy":
            raise_thresh += 0.06
        if opts["canRaise"] and (strength >= raise_thresh or (strength < 0.35 and self.rng.random() < pcfg["bluff"] * 0.45)):
            amt = self._decide_raise_amount(room, opts, strength, persona)
            if amt >= opts["maxTo"]:
                return [("allin", {})]
            return [("raise", {"amount": amt})]

        # Ngưỡng Call theo pot odds + tính cách
        call_floor = max(0.30, pot_odds + 0.18 - pcfg["loose"])
        if self.level == "easy":
            call_floor -= 0.08   # máy dễ hay theo rộng (calling station)
        elif self.level == "hard":
            # Với stack call all-in lớn, máy khó siết chặt ngưỡng theo
            if to_call > st.chips * 0.55 and strength < 0.70:
                call_floor = max(call_floor, 0.68)

        # Đã bỏ quá nhiều vào pot hoặc lượng cần theo rất nhỏ so với stack
        if to_call <= room.bb and strength >= 0.28:
            return [("call", {})]
        if strength >= call_floor:
            return [("call", {})]
        return [("fold", {})]

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        try:
            acts = self._choose_action(room, mark)
            if acts:
                return acts
        except Exception:
            pass

        # Fallback an toàn tuyệt đối để ván poker không bao giờ treo bàn
        if room.phase == "ritvote":
            return [("rit", {"yes": True})]
        if room.phase == "betting" and room.actor == mark:
            opts = room._action_options(mark)
            return [("check", {})] if opts["canCheck"] else [("fold", {})]
        return []
