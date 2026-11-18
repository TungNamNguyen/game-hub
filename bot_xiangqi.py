"""Máy chơi cờ tướng nâng cao.

Dùng chung phần alpha-beta + Transposition Table + Killer Moves + Quiescence ở bots.py;
ở đây cài đặt toàn bộ tri thức cờ tướng chuyên sâu:
  * Bảng điểm vị trí chuẩn (Piece-Square Tables 9x10) cho Xe, Pháo, Mã, Binh, Sĩ, Tượng, Tướng.
  * Đánh giá chân Mã bị cản, Pháo đầu / Pháo trống uy hiếp cửu cung, liên kết Sĩ - Tượng.
  * Zobrist Hashing và bộ sinh nước ăn quân siêu tốc cho Quiescence Search.
  * Sách khai cuộc chuẩn: Pháo đầu (Trung Pháo), Bình phong mã, Tiên nhân chỉ lộ, Thuận pháo.
"""

from __future__ import annotations

import random
import xiangqi as xq
from bots import Bot, BotError, Position, search_best

# Giá trị cơ bản (centipawn-style, Binh = 100)
VALUE = {"R": 950, "C": 480, "H": 430, "A": 220, "E": 220, "P": 100, "K": 0}

# Pháo/Mã đổi giá trị theo giai đoạn tàn cuộc
ENDGAME_LIMIT = 2400
CANNON_ENDGAME = 0.85   # Pháo yếu dần khi thưa ngòi
HORSE_ENDGAME = 1.15    # Mã mạnh lên khi bàn thoáng ít cản chân

# --------------------------------------------------------------------------- #
# Bảng điểm vị trí (Piece-Square Tables 9x10 theo góc nhìn quân ĐỎ)
# Row 0: Đáy đối phương, Row 4: Bờ sông địch, Row 5: Bờ sông ta, Row 9: Đáy quân ta.
# --------------------------------------------------------------------------- #
ROOK_PST = (
    15, 20, 20, 25, 25, 25, 20, 20, 15,   # Row 0
    25, 30, 35, 35, 35, 35, 35, 30, 25,   # Row 1 (Hạ cửu cung địch)
    20, 25, 30, 30, 30, 30, 30, 25, 20,   # Row 2 (Kẹp cổ địch)
    15, 20, 25, 25, 25, 25, 25, 20, 15,   # Row 3
    20, 25, 30, 30, 30, 30, 30, 25, 20,   # Row 4 (Áp hà)
    15, 20, 25, 25, 25, 25, 25, 20, 15,   # Row 5 (Tuần hà)
     5, 10, 10, 15, 15, 15, 10, 10,  5,   # Row 6
     0,  5,  5, 10, 10, 10,  5,  5,  0,   # Row 7
    -5,  5,  5, 10, 10, 10,  5,  5, -5,   # Row 8
   -10,  0,  5, 10, 10, 10,  5,  0,-10,   # Row 9 (Xuất phát)
)

CANNON_PST = (
     0,  5,  5, 10, 15, 10,  5,  5,  0,   # Row 0
     5, 10, 10, 15, 25, 15, 10, 10,  5,   # Row 1
    10, 15, 15, 20, 30, 20, 15, 15, 10,   # Row 2
    10, 15, 20, 25, 30, 25, 20, 15, 10,   # Row 3
    15, 20, 20, 25, 35, 25, 20, 20, 15,   # Row 4 (Bờ sông địch)
    15, 20, 20, 25, 35, 25, 20, 20, 15,   # Row 5 (Tuần hà)
     5, 10, 15, 20, 25, 20, 15, 10,  5,   # Row 6
     0,  5,  5, 10, 30, 10,  5,  5,  0,   # Row 7 (Vị trí Pháo đầu cột giữa)
     0,  0,  0,  5, 15,  5,  0,  0,  0,   # Row 8
     0,  0,  0,  5, 10,  5,  0,  0,  0,   # Row 9
)

HORSE_PST = (
   -20,-15,-10, -5, -5, -5,-10,-15,-20,   # Row 0
   -15,  5, 25, 35, 20, 35, 25,  5,-15,   # Row 1 (Ngoạ tào)
   -10, 15, 30, 45, 35, 45, 30, 15,-10,   # Row 2 (Điếu ngư mã)
   -10, 20, 30, 35, 35, 35, 30, 20,-10,   # Row 3
    -5, 20, 25, 30, 30, 30, 25, 20, -5,   # Row 4 (Qua sông)
    -5, 15, 20, 25, 25, 25, 20, 15, -5,   # Row 5 (Bàn hà)
   -10, 10, 20, 15, 20, 15, 20, 10,-10,   # Row 6
   -15,  5, 20, 10, 15, 10, 20,  5,-15,   # Row 7 (Chính mã)
   -20,  0,  5,  5,  5,  5,  5,  0,-20,   # Row 8
   -25,  0,-10,  0,  0,  0,-10,  0,-25,   # Row 9 (Vị trí ban đầu)
)

SOLDIER_PST = (
    50, 50, 60, 60, 60, 60, 60, 50, 50,   # Row 0 (Binh lụt)
    90,110,130,160,170,160,130,110, 90,   # Row 1 (Áp sát cửu cung)
    80,100,120,140,150,140,120,100, 80,   # Row 2
    70, 80,100,120,125,120,100, 80, 70,   # Row 3
    65, 75, 80, 85, 90, 85, 80, 75, 65,   # Row 4 (Vừa qua sông)
     0,  0, 15,  0, 25,  0, 15,  0,  0,   # Row 5 (Bờ sông ta)
     0,  0, 10,  0, 15,  0, 10,  0,  0,   # Row 6 (Chưa đi)
     0,  0,  0,  0,  0,  0,  0,  0,  0,   # Row 7
     0,  0,  0,  0,  0,  0,  0,  0,  0,   # Row 8
     0,  0,  0,  0,  0,  0,  0,  0,  0,   # Row 9
)

ADVISOR_PST = (
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0, 10,  0, 10,  0,  0,  0,   # Row 7
     0,  0,  0,  0, 20,  0,  0,  0,  0,   # Row 8 (Tâm cung)
     0,  0,  0, 10,  0, 10,  0,  0,  0,   # Row 9 (Đáy cung)
)

ELEPHANT_PST = (
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0, 15,  0,  0,  0, 15,  0,  0,   # Row 5 (Tượng tuần hà)
     0,  0,  0,  0,  0,  0,  0,  0,  0,   # Row 6
     0,  0,  0,  0, 25,  0,  0,  0,  0,   # Row 7 (Tâm tượng)
     0,  0,  0,  0,  0,  0,  0,  0,  0,   # Row 8
     0,  0, 10,  0,  0,  0, 10,  0,  0,   # Row 9
)

KING_PST = (
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,-15,-15,-15,  0,  0,  0,   # Row 7
     0,  0,  0, -5,  0, -5,  0,  0,  0,   # Row 8
     0,  0,  0, 10, 15, 10,  0,  0,  0,   # Row 9 (Đáy cung an toàn)
)

XQ_TABLES = {
    "R": ROOK_PST, "C": CANNON_PST, "H": HORSE_PST, "P": SOLDIER_PST,
    "A": ADVISOR_PST, "E": ELEPHANT_PST, "K": KING_PST,
}

# Hằng số Zobrist Hashing cho cờ tướng
_XQ_RNG = random.Random(2026)
XQ_PIECES = ("rR", "rC", "rH", "rE", "rA", "rP", "rK",
             "bR", "bC", "bH", "bE", "bA", "bP", "bK")
ZOBRIST_XQ = {p: [_XQ_RNG.getrandbits(64) for _ in range(90)] for p in XQ_PIECES}
ZOBRIST_XQ_SIDE = _XQ_RNG.getrandbits(64)


def compute_xq_hash(board: list[str], colour: str) -> int:
    h = ZOBRIST_XQ_SIDE if colour == xq.RED else 0
    for sq, p in enumerate(board):
        if p:
            h ^= ZOBRIST_XQ[p][sq]
    return h


def _flip_xq(index: int) -> int:
    """Lật dọc 9x10 để quân Đen tra cùng bảng vị trí với quân Đỏ."""
    row, col = divmod(index, xq.COLS)
    return (9 - row) * xq.COLS + col


def _fast_xq_captures(board: list[str], color: str) -> list[tuple[int, int]]:
    """Sinh siêu tốc chỉ các nước ăn quân hợp lệ cho Quiescence Search."""
    enemy = xq.other_color(color)
    caps: list[tuple[int, int]] = []
    for frm, piece in enumerate(board):
        if not piece or piece[0] != color:
            continue
        kind = piece[1]
        r, c = divmod(frm, xq.COLS)
        if kind == "P":
            step = -1 if color == xq.RED else 1
            nr = r + step
            if xq.on_board(nr, c) and board[nr * xq.COLS + c].startswith(enemy):
                caps.append((frm, nr * xq.COLS + c))
            if xq.crossed_river(color, r):
                for dc in (-1, 1):
                    nc = c + dc
                    if xq.on_board(r, nc) and board[r * xq.COLS + nc].startswith(enemy):
                        caps.append((frm, r * xq.COLS + nc))
        elif kind == "H":
            for dr, dc, lr, lc in xq.HORSE_STEPS:
                tr, tc = r + dr, c + dc
                if xq.on_board(tr, tc) and board[tr * xq.COLS + tc].startswith(enemy):
                    if not board[(r + lr) * xq.COLS + (c + lc)]:
                        caps.append((frm, tr * xq.COLS + tc))
        elif kind == "R":
            for dr, dc in xq.ORTHOGONALS:
                tr, tc = r + dr, c + dc
                while xq.on_board(tr, tc):
                    p = board[tr * xq.COLS + tc]
                    if p:
                        if p.startswith(enemy):
                            caps.append((frm, tr * xq.COLS + tc))
                        break
                    tr += dr
                    tc += dc
        elif kind == "C":
            for dr, dc in xq.ORTHOGONALS:
                tr, tc = r + dr, c + dc
                screen = False
                while xq.on_board(tr, tc):
                    p = board[tr * xq.COLS + tc]
                    if p:
                        if not screen:
                            screen = True
                        else:
                            if p.startswith(enemy):
                                caps.append((frm, tr * xq.COLS + tc))
                            break
                    tr += dr
                    tc += dc
        elif kind == "E":
            for dr, dc in xq.DIAGONALS:
                tr, tc = r + 2 * dr, c + 2 * dc
                if xq.on_board(tr, tc) and xq.own_half(color, tr):
                    if not board[(r + dr) * xq.COLS + (c + dc)] and board[tr * xq.COLS + tc].startswith(enemy):
                        caps.append((frm, tr * xq.COLS + tc))
        elif kind in ("A", "K"):
            steps = xq.DIAGONALS if kind == "A" else xq.ORTHOGONALS
            for dr, dc in steps:
                tr, tc = r + dr, c + dc
                if xq.in_palace(color, tr, tc) and board[tr * xq.COLS + tc].startswith(enemy):
                    caps.append((frm, tr * xq.COLS + tc))

    legal_caps = []
    for frm, to in caps:
        after, _ = xq.apply_move(board, frm, to)
        if not xq.in_check(after, color):
            legal_caps.append((frm, to))
    return legal_caps


def evaluate(board: list[str], side: str) -> int:
    """Điểm thế cờ cờ tướng chi tiết theo góc nhìn ``side`` ("r"/"b")."""
    heavy = sum(VALUE[p[1]] for p in board if p and p[1] in ("R", "C", "H"))
    endgame = heavy <= ENDGAME_LIMIT
    totals = {xq.RED: 0, xq.BLACK: 0}
    advisors = {xq.RED: 0, xq.BLACK: 0}
    elephants = {xq.RED: 0, xq.BLACK: 0}
    chariots = {xq.RED: 0, xq.BLACK: 0}
    cannons: dict[str, list[int]] = {xq.RED: [], xq.BLACK: []}
    kings: dict[str, int] = {}

    for index, piece in enumerate(board):
        if not piece:
            continue
        colour, kind = piece[0], piece[1]
        r, c = divmod(index, xq.COLS)
        value = VALUE[kind]

        if endgame:
            if kind == "C":
                value = int(value * CANNON_ENDGAME)
            elif kind == "H":
                value = int(value * HORSE_ENDGAME)

        # Tra bảng Piece-Square Table
        pst_index = index if colour == xq.RED else _flip_xq(index)
        value += XQ_TABLES[kind][pst_index]

        # Đếm quân để xét phòng thủ và thế cờ
        if kind == "A":
            advisors[colour] += 1
        elif kind == "E":
            elephants[colour] += 1
        elif kind == "R":
            chariots[colour] += 1
        elif kind == "C":
            cannons[colour].append(index)
        elif kind == "K":
            kings[colour] = index
        elif kind == "H":
            # Phạt chân Mã bị cản
            blocked_legs = 0
            for dr, dc, lr, lc in xq.HORSE_STEPS:
                if not xq.on_board(r + dr, c + dc):
                    continue
                if board[(r + lr) * xq.COLS + (c + lc)]:
                    blocked_legs += 1
            value -= blocked_legs * 4

        totals[colour] += value

    # Đánh giá tương quan chiến thuật giữa hai bên
    for colour in (xq.RED, xq.BLACK):
        enemy = xq.other_color(colour)

        # 1. Thưởng liên kết Sĩ - Tượng phòng thủ
        if advisors[colour] == 2 and elephants[colour] == 2:
            totals[colour] += 35
        # Mất Sĩ khi đối phương còn Xe là điểm yếu chí mạng
        if advisors[colour] <= 1 and chariots[enemy] >= 1:
            totals[colour] -= (2 - advisors[colour]) * 30

        # 2. Uy hiếp Pháo đầu / Pháo trống trung lộ
        if enemy in kings:
            e_king_col = kings[enemy] % xq.COLS
            for c_sq in cannons[colour]:
                c_row, c_col = divmod(c_sq, xq.COLS)
                if c_col == e_king_col and c_col == 4:  # Cùng ở cột trung lộ (cột 4)
                    low_r, high_r = sorted((c_row, kings[enemy] // xq.COLS))
                    screens = sum(1 for mid_r in range(low_r + 1, high_r)
                                  if board[mid_r * xq.COLS + 4])
                    if screens == 1:
                        totals[colour] += 35  # Pháo đầu đóng chặt
                    elif screens == 0:
                        totals[colour] += 120 # Pháo trống chiếu thẳng mặt!

    # Đang chiếu đối phương
    foe = xq.other_color(side)
    if xq.in_check(board, foe):
        totals[side] += 25

    return totals[side] - totals[foe]


class XiangqiPosition(Position):
    """Bọc trạng thái cờ tướng cho khung tìm kiếm ở bots.py."""

    __slots__ = ("board", "colour", "_moves", "_hash")

    def __init__(self, board, colour, h=None):
        self.board = board
        self.colour = colour
        self._moves = None
        self._hash = h if h is not None else compute_xq_hash(board, colour)

    def hash_key(self) -> int:
        return self._hash

    def _flat(self):
        if self._moves is None:
            table = xq.legal_moves(self.board, self.colour)
            self._moves = [(frm, to) for frm, tos in table.items() for to in tos]
        return self._moves

    def moves(self):
        return list(self._flat())

    def quiescence_moves(self):
        """Chỉ sinh các nước ăn quân để Quiescence Search chạy nhanh gấp 10 lần."""
        if self._moves is not None:
            return [m for m in self._moves if self.is_capture(m)]
        return _fast_xq_captures(self.board, self.colour)

    def play(self, move):
        frm, to = move
        p = self.board[frm]
        captured = self.board[to]
        board, _ = xq.apply_move(self.board, frm, to)

        # Cập nhật hash Zobrist nhanh
        next_colour = xq.other_color(self.colour)
        h = self._hash ^ ZOBRIST_XQ[p][frm] ^ ZOBRIST_XQ[p][to] ^ ZOBRIST_XQ_SIDE
        if captured:
            h ^= ZOBRIST_XQ[captured][to]

        return XiangqiPosition(board, next_colour, h=h)

    def score(self):
        return evaluate(self.board, self.colour)

    def is_capture(self, move):
        return bool(self.board[move[1]])

    def order(self, move):
        frm, to = move
        victim = self.board[to]
        if victim:
            return 10_000 + VALUE[victim[1]] * 10 - VALUE[self.board[frm][1]]
        p = self.board[frm][1]
        return {"R": 60, "C": 50, "H": 40, "P": 25}.get(p, 0)

    def in_check(self):
        return xq.in_check(self.board, self.colour)

    def loss_on_no_move(self):
        return True


# Sách khai cuộc cờ tướng chuẩn (Opening Book)
# Key: tuple các nước ((frm, to), ...) đã đi
# Value: list các ((frm, to), trọng số)
XIANGQI_BOOK: dict[tuple[tuple[int, int], ...], list[tuple[tuple[int, int], int]]] = {
    # Nước 1: Đỏ mở màn
    (): [
        ((70, 67), 60),  # Pháo 2 bình 5 (Trung pháo)
        ((64, 67), 30),  # Pháo 8 bình 5 (Trung pháo)
        ((56, 47), 20),  # Binh 7 tấn 1 (Tiên nhân chỉ lộ)
        ((60, 51), 20),  # Binh 3 tấn 1
        ((88, 71), 15),  # Mã 2 tấn 3 (Khởi mã)
        ((82, 65), 15),  # Mã 8 tấn 7
    ],
    # 1. Pháo 2 bình 5 (70->67) -> Đen đáp lại
    ((70, 67),): [
        ((1, 20), 60),   # Mã 8 tấn 7 (Bình phong mã)
        ((7, 24), 25),   # Mã 2 tấn 3
        ((25, 22), 20),  # Pháo 8 bình 5 (Thuận pháo)
        ((19, 22), 15),  # Pháo 2 bình 5 (Nghịch pháo)
    ],
    # 1. Pháo 8 bình 5 (64->67) -> Đen đáp lại
    ((64, 67),): [
        ((7, 24), 60),   # Mã 2 tấn 3 (Bình phong mã)
        ((1, 20), 25),   # Mã 8 tấn 7
        ((19, 22), 20),  # Pháo 2 bình 5 (Thuận pháo)
    ],
    # 1. Pháo 2 bình 5, Mã 8 tấn 7 -> Đỏ
    ((70, 67), (1, 20)): [
        ((88, 71), 75),  # 2. Mã 2 tấn 3
        ((89, 88), 25),  # 2. Xe 1 bình 2
    ],
    # 1. Pháo 8 bình 5, Mã 2 tấn 3 -> Đỏ
    ((64, 67), (7, 24)): [
        ((82, 65), 75),  # 2. Mã 8 tấn 7
        ((81, 82), 25),  # 2. Xe 9 bình 8
    ],
    # 1. Pháo 2 bình 5, Mã 8 tấn 7, 2. Mã 2 tấn 3 -> Đen
    ((70, 67), (1, 20), (88, 71)): [
        ((8, 7), 55),    # 2... Xe 9 bình 8
        ((7, 24), 35),   # 2... Mã 2 tấn 3 (Song mã)
        ((29, 38), 10),  # 2... Binh 7 tấn 1
    ],
    # 1. Binh 7 tấn 1 (56->47) -> Đen đáp lại
    ((56, 47),): [
        ((29, 38), 50),  # 1... Binh 7 tấn 1 (Đối binh)
        ((19, 22), 30),  # 1... Pháo 2 bình 5
        ((7, 24), 20),   # 1... Mã 2 tấn 3
    ],
}


class XiangqiBot(Bot):
    CHANNEL = "xiangqi"

    MAX_DEPTH = {"easy": 2, "normal": 4, "hard": 6}
    TIME_BUDGET = {"easy": 0.25, "normal": 0.8, "hard": 1.8}
    THINK_DELAY = {"easy": 0.45, "normal": 0.45, "hard": 0.3}
    BLUNDER = {"easy": 0.4, "normal": 0.0, "hard": 0.0}
    JITTER = {"easy": 40, "normal": 10, "hard": 3}

    def _book_move(self, room, colour: str) -> tuple[int, int] | None:
        """Tra sách khai cuộc cờ tướng. Trả về (frm, to) hoặc None."""
        history = tuple((m["from"], m["to"]) for m in room.moves)
        candidates = XIANGQI_BOOK.get(history)
        if not candidates:
            return None

        legal = xq.legal_moves(room.board, colour)
        valid_moves = []
        for (frm, to), weight in candidates:
            if frm in legal and to in legal[frm]:
                valid_moves.append(((frm, to), weight))

        if not valid_moves:
            return None

        if self.level == "easy" and self.rng.random() < 0.4:
            return None

        if self.level == "hard":
            return max(valid_moves, key=lambda p: p[1])[0]

        moves, weights = zip(*valid_moves)
        return self.rng.choices(moves, weights=weights, k=1)[0]

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        if room.status != "playing":
            raise BotError("Chưa tới lượt máy đi.")
        colour = room.color_of(mark)

        # 1. Sách khai cuộc (0ms)
        book = self._book_move(room, colour)
        if book is not None:
            frm, to = book
            return [("move", {"from": frm, "to": to})]

        # 2. Tìm kiếm Alpha-Beta với Zobrist TT và Heuristics
        pos = XiangqiPosition(list(room.board), colour)
        move, _score, _depth = search_best(
            pos,
            max_depth=self.MAX_DEPTH.get(self.level, 4),
            budget=self.budget,
            rng=self.rng,
            blunder=self.BLUNDER.get(self.level, 0.0),
            jitter=self.JITTER.get(self.level, 0),
        )
        if move is None:
            raise BotError("Máy không tìm được nước đi hợp lệ.")

        frm, to = move
        return [("move", {"from": frm, "to": to})]
