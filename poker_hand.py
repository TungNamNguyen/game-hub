"""Đánh giá tay bài Poker (Texas Hold'em) — thuần Python, không I/O.

Giống nguyên tắc của ``games.py``: module này không phụ thuộc framework nào,
nên luật so bài test được độc lập, tách khỏi mọi thứ về phòng/socket.

Một lá bài là tuple ``(rank, suit)``:
  - rank: int 2-14 (11=J, 12=Q, 13=K, 14=A)
  - suit: một trong "S", "H", "D", "C" (bích, cơ, rô, chuồn)

``best_hand(cards)`` nhận 5-7 lá (2 bài riêng + tối đa 5 bài chung) và trả về
một ``HandScore`` so sánh được bằng so sánh tuple thường (càng lớn càng mạnh).
Không cần bảng tra cứu ngoài — duyệt hết C(7,5)=21 tổ hợp con 5 lá là đủ nhanh
cho một bàn 6 người so bài vài lần mỗi ván.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "SHDC"
RANK_VALUE = {ch: i + 2 for i, ch in enumerate(RANKS)}
RANK_LABEL = {v: k for k, v in RANK_VALUE.items()}

# Thứ hạng loại tay bài, cao hơn thắng. Dùng số để so sánh tuple cho gọn.
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
TRIPS = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
QUADS = 7
STRAIGHT_FLUSH = 8

# Tên tay bài dùng thuật ngữ tiếng Anh chuẩn của poker — người chơi online
# quen "Full House", "Flush" hơn là "Cù lũ", "Thùng".
CATEGORY_NAME = {
    HIGH_CARD: "High Card", ONE_PAIR: "Pair", TWO_PAIR: "Two Pair",
    TRIPS: "Three of a Kind", STRAIGHT: "Straight", FLUSH: "Flush",
    FULL_HOUSE: "Full House", QUADS: "Four of a Kind", STRAIGHT_FLUSH: "Straight Flush",
}

SUIT_GLYPH = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}


def fresh_deck() -> list[tuple[int, str]]:
    """Bộ 52 lá, chưa xáo."""
    return [(RANK_VALUE[r], s) for r in RANKS for s in SUITS]


@dataclass(frozen=True)
class HandScore:
    """So sánh được trực tiếp: điểm cao hơn thắng, bằng điểm thì hòa (chia pot).

    ``category`` là loại tay (0-8), ``tiebreak`` là tuple các giá trị để so
    khi cùng loại (ví dụ Full nhà: (giá trị bộ ba, giá trị đôi)). So sánh toàn
    bộ bằng cách so (category, tiebreak) — Python so tuple theo thứ tự phần tử.
    """
    category: int
    tiebreak: tuple[int, ...]
    cards: tuple[tuple[int, str], ...]   # 5 lá tạo nên tay bài này, để hiển thị

    def key(self) -> tuple:
        return (self.category, self.tiebreak)

    def __lt__(self, other: "HandScore") -> bool:
        return self.key() < other.key()

    def __eq__(self, other) -> bool:
        return isinstance(other, HandScore) and self.key() == other.key()

    @property
    def label(self) -> str:
        return CATEGORY_NAME[self.category]


def _straight_high(values: list[int]) -> int | None:
    """Giá trị lá cao nhất của sảnh nếu 5 giá trị (đã unique, giảm dần) tạo
    thành một sảnh liên tiếp, kể cả sảnh A-2-3-4-5 (bánh)."""
    uniq = sorted(set(values), reverse=True)
    if len(uniq) < 5:
        return None
    # A-5-4-3-2 ("bánh"): A được tính là 1 ở đáy sảnh.
    if set([14, 5, 4, 3, 2]).issubset(uniq):
        wheel = True
    else:
        wheel = False
    for i in range(len(uniq) - 4):
        window = uniq[i:i + 5]
        if window[0] - window[4] == 4:
            return window[0]
    if wheel:
        return 5
    return None


def score_five(cards: list[tuple[int, str]]) -> HandScore:
    """Chấm điểm ĐÚNG 5 lá."""
    values = sorted((c[0] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(values)

    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    # Nhóm theo (số lượng giảm dần, giá trị giảm dần) — vd FullHouse: [(3,v1),(2,v2)]
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    shape = [g[1] for g in groups]

    ordered_cards = tuple(sorted(cards, key=lambda c: -c[0]))

    if is_flush and straight_high:
        return HandScore(STRAIGHT_FLUSH, (straight_high,), ordered_cards)
    if shape == [4, 1]:
        quad, kicker = groups[0][0], groups[1][0]
        return HandScore(QUADS, (quad, kicker), ordered_cards)
    if shape == [3, 2]:
        trips, pair = groups[0][0], groups[1][0]
        return HandScore(FULL_HOUSE, (trips, pair), ordered_cards)
    if is_flush:
        return HandScore(FLUSH, tuple(values), ordered_cards)
    if straight_high:
        return HandScore(STRAIGHT, (straight_high,), ordered_cards)
    if shape == [3, 1, 1]:
        trips = groups[0][0]
        kickers = tuple(sorted((g[0] for g in groups[1:]), reverse=True))
        return HandScore(TRIPS, (trips,) + kickers, ordered_cards)
    if shape == [2, 2, 1]:
        pairs = tuple(sorted((g[0] for g in groups[:2]), reverse=True))
        kicker = groups[2][0]
        return HandScore(TWO_PAIR, pairs + (kicker,), ordered_cards)
    if shape == [2, 1, 1, 1]:
        pair = groups[0][0]
        kickers = tuple(sorted((g[0] for g in groups[1:]), reverse=True))
        return HandScore(ONE_PAIR, (pair,) + kickers, ordered_cards)
    return HandScore(HIGH_CARD, tuple(values), ordered_cards)


def best_hand(cards: list[tuple[int, str]]) -> HandScore:
    """Tay 5 lá mạnh nhất rút ra từ 5-7 lá cho sẵn."""
    if len(cards) < 5:
        raise ValueError("Cần ít nhất 5 lá để chấm điểm.")
    if len(cards) == 5:
        return score_five(list(cards))
    best: HandScore | None = None
    for combo in combinations(cards, 5):
        score = score_five(list(combo))
        if best is None or score.key() > best.key():
            best = score
    assert best is not None
    return best


DISPLAY_RANK = {10: "10", 11: "J", 12: "Q", 13: "K", 14: "A"}


def rank_label(value: int) -> str:
    """Nhãn hiển thị: 10 viết là "10" (không phải "T") cho người chơi phổ thông."""
    return DISPLAY_RANK.get(value, str(value))


def card_label(card: tuple[int, str]) -> str:
    value, suit = card
    return f"{rank_label(value)}{SUIT_GLYPH.get(suit, suit)}"


RANK_WORD = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
             8: "Eight", 9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King",
             14: "Ace"}
RANK_PLURAL = {**{v: f"{w}s" for v, w in RANK_WORD.items()}, 6: "Sixes"}


def describe(score: HandScore) -> str:
    """Tên tay bài đầy đủ theo cách các site poker online hiển thị:
    "Full House, Kings full of Sevens", "Straight, Nine high"..."""
    t = score.tiebreak
    w, p = RANK_WORD, RANK_PLURAL
    if score.category == STRAIGHT_FLUSH:
        return "Royal Flush" if t[0] == 14 else f"Straight Flush, {w[t[0]]} high"
    if score.category == QUADS:
        return f"Four of a Kind, {p[t[0]]}"
    if score.category == FULL_HOUSE:
        return f"Full House, {p[t[0]]} full of {p[t[1]]}"
    if score.category == FLUSH:
        return f"Flush, {w[t[0]]} high"
    if score.category == STRAIGHT:
        return f"Straight, {w[t[0]]} high"
    if score.category == TRIPS:
        return f"Three of a Kind, {p[t[0]]}"
    if score.category == TWO_PAIR:
        return f"Two Pair, {p[t[0]]} and {p[t[1]]}"
    if score.category == ONE_PAIR:
        return f"Pair of {p[t[0]]}"
    return f"High Card, {w[t[0]]}"


def describe_cards(hole: list[tuple[int, str]], board: list[tuple[int, str]]) -> str:
    """Tay bài hiện tại của một người, hiện dưới hai lá tẩy. Trước flop chỉ có
    2 lá nên không chấm 5 lá được — mô tả kiểu "Pocket Kings", "A-K suited"."""
    if len(hole) < 2:
        return ""
    if len(hole) + len(board) < 5:
        (v1, s1), (v2, s2) = sorted(hole, key=lambda c: -c[0])
        if v1 == v2:
            return f"Pocket {RANK_PLURAL[v1]}"
        suited = "suited" if s1 == s2 else "offsuit"
        return f"{rank_label(v1)}-{rank_label(v2)} {suited}"
    return describe(best_hand(list(hole) + list(board)))
