"""Máy chơi cờ vua.

Dùng phần alpha-beta + Transposition Table + Killer Moves + Quiescence dùng chung
ở bots.py; ở đây cài phần "hiểu cờ vua": giá trị quân, bảng vị trí, đánh giá thế
trận (tapered eval, tốt thông, cột mở, an toàn vua), và sách khai cuộc chuẩn.
"""

from __future__ import annotations

import random
import chessgame as ch
from bots import Bot, BotError, Position, search_best

# Đơn vị: centipawn (tốt = 100), quy ước chuẩn của cờ vua máy.
VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}

# Bảng vị trí viết theo góc nhìn quân TRẮNG, index 0 = a8 (khớp cách đánh index
# của chessgame). Quân Đen tra cùng bảng nhưng lật dọc.
PAWN_TABLE = (
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
)
KNIGHT_TABLE = (
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
)
BISHOP_TABLE = (
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
)
ROOK_TABLE = (
      0,  0,  0,  0,  0,  0,  0,  0,
      5, 10, 10, 10, 10, 10, 10,  5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
      0,  0,  0,  5,  5,  0,  0,  0,
)
QUEEN_TABLE = (
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
)
KING_EARLY_TABLE = (
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
)
KING_LATE_TABLE = (
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
)
TABLES = {"P": PAWN_TABLE, "N": KNIGHT_TABLE, "B": BISHOP_TABLE,
          "R": ROOK_TABLE, "Q": QUEEN_TABLE}

# Điểm thưởng Tốt thông theo hàng (từ góc nhìn quân Trắng)
PASSED_PAWN_BONUS = (0, 130, 80, 50, 30, 15, 0, 0)
BISHOP_PAIR = 30
DOUBLED_PAWN = -18

# Hằng số Zobrist Hashing cho cờ vua
_RNG = random.Random(2026)
CHESS_PIECES = ("wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK")
ZOBRIST_PIECES = {p: [_RNG.getrandbits(64) for _ in range(64)] for p in CHESS_PIECES}
ZOBRIST_SIDE = _RNG.getrandbits(64)
ZOBRIST_CASTLING = {c: _RNG.getrandbits(64) for c in ("K", "Q", "k", "q")}
ZOBRIST_EP = [_RNG.getrandbits(64) for _ in range(65)]


def compute_chess_hash(board: list[str], colour: str, castling: set[str], ep: int) -> int:
    h = ZOBRIST_SIDE if colour == "w" else 0
    for sq, p in enumerate(board):
        if p:
            h ^= ZOBRIST_PIECES[p][sq]
    for c in castling:
        h ^= ZOBRIST_CASTLING[c]
    if 0 <= ep < 64:
        h ^= ZOBRIST_EP[ep]
    return h


def _flip(index: int) -> int:
    """Lật dọc để quân Đen tra cùng bảng vị trí với quân Trắng."""
    return index ^ 56


def evaluate(board: list[str], side: str) -> int:
    """Điểm thế cờ nâng cao theo góc nhìn ``side`` ("w"/"b"), đơn vị centipawn.
    Bao gồm tapered eval, tốt thông, cột mở cho xe, cặp tượng, và lá chắn bảo vệ vua.
    """
    material = {"w": 0, "b": 0}
    placement = {"w": 0, "b": 0}
    bishops = {"w": 0, "b": 0}
    rooks: dict[str, list[int]] = {"w": [], "b": []}
    pawn_squares: dict[str, list[int]] = {"w": [], "b": []}
    pawn_files: dict[str, dict[int, int]] = {"w": {}, "b": {}}
    heavy = 0
    kings: dict[str, int] = {}

    for index, piece in enumerate(board):
        if not piece:
            continue
        colour, kind = piece[0], piece[1]
        material[colour] += VALUE[kind]
        if kind == "K":
            kings[colour] = index
            continue
        if kind != "P":
            heavy += VALUE[kind]
        if kind == "B":
            bishops[colour] += 1
        elif kind == "R":
            rooks[colour].append(index)
        elif kind == "P":
            pawn_squares[colour].append(index)
            file_no = index % 8
            pawn_files[colour][file_no] = pawn_files[colour].get(file_no, 0) + 1
        table = TABLES[kind]
        placement[colour] += table[index if colour == "w" else _flip(index)]

    # Tapered king evaluation: nội suy mượt mà giữa trung cuộc và tàn cuộc
    phase = max(0.0, min(1.0, heavy / 2600.0))
    for colour, index in kings.items():
        early = KING_EARLY_TABLE[index if colour == "w" else _flip(index)]
        late = KING_LATE_TABLE[index if colour == "w" else _flip(index)]
        placement[colour] += int(phase * early + (1.0 - phase) * late)

    score = 0
    for colour in ("w", "b"):
        sign = 1 if colour == side else -1
        enemy = "b" if colour == "w" else "w"
        val = material[colour] + placement[colour]

        # Thưởng cặp tượng
        if bishops[colour] >= 2:
            val += BISHOP_PAIR

        # Phạt tốt chồng
        for count in pawn_files[colour].values():
            if count > 1:
                val += DOUBLED_PAWN * (count - 1)

        # Thưởng Tốt thông (Passed Pawn)
        for p_sq in pawn_squares[colour]:
            row, col = divmod(p_sq, 8)
            # Kiểm tra xem có tốt địch chặn đường phía trước ở cùng cột hoặc cột kề không
            is_passed = True
            for ep_sq in pawn_squares[enemy]:
                erow, ecol = divmod(ep_sq, 8)
                if abs(ecol - col) <= 1:
                    if colour == "w" and erow < row:
                        is_passed = False
                        break
                    elif colour == "b" and erow > row:
                        is_passed = False
                        break
            if is_passed:
                val += PASSED_PAWN_BONUS[row if colour == "w" else (7 - row)]

        # Thưởng Xe trên cột mở (không có tốt) hoặc nửa mở (chỉ có tốt địch)
        for r_sq in rooks[colour]:
            col = r_sq % 8
            my_pawns = pawn_files[colour].get(col, 0)
            enemy_pawns = pawn_files[enemy].get(col, 0)
            if my_pawns == 0 and enemy_pawns == 0:
                val += 25  # Cột mở hoàn toàn
            elif my_pawns == 0:
                val += 14  # Cột nửa mở

        # Thưởng lá chắn Tốt bảo vệ Vua ở trung cuộc
        if phase > 0.4 and colour in kings:
            k_sq = kings[colour]
            k_row, k_col = divmod(k_sq, 8)
            home_rank = 7 if colour == "w" else 0
            # Vua đã nhập thành cánh vua (g1/g8) hoặc cánh hậu (c1/c8)
            if k_row == home_rank and k_col in (6, 7):
                shield_row = 6 if colour == "w" else 1
                shield_intact = sum(1 for c in (5, 6, 7)
                                    if board[shield_row * 8 + c] == colour + "P")
                val += shield_intact * 12
            elif k_row == home_rank and k_col in (1, 2):
                shield_row = 6 if colour == "w" else 1
                shield_intact = sum(1 for c in (0, 1, 2)
                                    if board[shield_row * 8 + c] == colour + "P")
                val += shield_intact * 12

        score += sign * val
    return score


class ChessPosition(Position):
    """Bọc trạng thái cờ vua cho khung tìm kiếm ở bots.py."""

    __slots__ = ("board", "colour", "castling", "ep", "_moves", "_hash")

    def __init__(self, board, colour, castling, ep, h=None):
        self.board = board
        self.colour = colour
        self.castling = castling
        self.ep = ep
        self._moves = None
        self._hash = h if h is not None else compute_chess_hash(board, colour, castling, ep)

    def hash_key(self) -> int:
        return self._hash

    def _flat(self):
        """Nước đi dạng phẳng (frm, to, flag, promo) để sắp xếp và chơi thử."""
        if self._moves is None:
            table = ch.legal_moves(self.board, self.colour, self.castling, self.ep)
            flat = []
            for frm, options in table.items():
                for option in options:
                    flat.append((frm, option["to"], option["flag"],
                                 "Q" if option["promo"] else ""))
            self._moves = flat
        return self._moves

    def moves(self):
        return list(self._flat())

    def quiescence_moves(self):
        """Chỉ sinh các nước ăn quân hoặc phong cấp, phục vụ Quiescence Search."""
        if self._moves is not None:
            return [m for m in self._moves if self.is_capture(m) or m[3]]

        # Sinh nhanh chỉ các nước ăn quân từ bàn cờ
        caps = []
        enemy = ch.other_color(self.colour)
        for frm, piece in enumerate(self.board):
            if not piece or piece[0] != self.colour:
                continue
            for to, flag in ch.piece_targets(self.board, frm, self.ep, self.castling):
                is_cap = bool(self.board[to]) or flag == "ep"
                is_promo = (piece[1] == "P" and (to // 8 in (0, 7)))
                if not (is_cap or is_promo):
                    continue
                after, _, _, _ = ch.apply_move(self.board, self.castling, frm, to, flag)
                if not ch.in_check(after, self.colour):
                    caps.append((frm, to, flag, "Q" if is_promo else ""))
        return caps

    def play(self, move):
        frm, to, flag, promo = move
        board, castling, ep, captured = ch.apply_move(
            self.board, self.castling, frm, to, flag, promo or "Q")

        # Cập nhật hash nhanh
        next_colour = ch.other_color(self.colour)
        p = self.board[frm]
        h = self._hash ^ ZOBRIST_PIECES[p][frm] ^ ZOBRIST_SIDE
        new_piece = (self.colour + promo) if promo else p
        h ^= ZOBRIST_PIECES[new_piece][to]
        if captured:
            victim_sq = (to + (8 if self.colour == "w" else -8)) if flag == "ep" else to
            h ^= ZOBRIST_PIECES[captured][victim_sq]

        return ChessPosition(board, next_colour, castling, ep,
                             h=compute_chess_hash(board, next_colour, castling, ep))

    def score(self):
        return evaluate(self.board, self.colour)

    def is_capture(self, move):
        return bool(self.board[move[1]]) or move[2] == "ep"

    def order(self, move):
        frm, to, flag, promo = move
        victim = self.board[to]
        if victim:
            # MVV-LVA: ăn quân to bằng quân nhỏ là ưu tiên số một
            return 10_000 + VALUE[victim[1]] * 10 - VALUE[self.board[frm][1]]
        if promo:
            return 9_000
        if flag == "ep":
            return 8_500
        if flag in ("castleK", "castleQ"):
            return 500
        return 0

    def in_check(self):
        return ch.in_check(self.board, self.colour)

    def loss_on_no_move(self):
        return False


# Sách khai cuộc chuẩn (Opening Book)
# Key: tuple các nước ((frm, to), ...) đã đi trước đó.
# Value: list các ((frm, to), trọng số)
CHESS_BOOK: dict[tuple[tuple[int, int], ...], list[tuple[tuple[int, int], int]]] = {
    # Nước 1: Trắng
    (): [
        ((52, 36), 50),   # 1. e4
        ((51, 35), 35),   # 1. d4
        ((50, 34), 10),   # 1. c4
        ((62, 45), 5),    # 1. Nf3
    ],
    # Nước 1: Đen đáp lại 1. e4
    ((52, 36),): [
        ((12, 28), 45),   # 1... e5 (King's Pawn)
        ((10, 26), 40),   # 1... c5 (Sicilian)
        ((12, 20), 10),   # 1... e6 (French)
        ((10, 18), 5),    # 1... c6 (Caro-Kann)
    ],
    # Nước 1: Đen đáp lại 1. d4
    ((51, 35),): [
        ((11, 27), 50),   # 1... d5
        ((6, 21), 40),    # 1... Nf6
        ((12, 20), 10),   # 1... e6
    ],
    # 1. e4 e5 -> Trắng
    ((52, 36), (12, 28)): [
        ((62, 45), 90),   # 2. Nf3
        ((57, 42), 10),   # 2. Nc3
    ],
    # 1. e4 e5 2. Nf3 -> Đen
    ((52, 36), (12, 28), (62, 45)): [
        ((1, 18), 85),    # 2... Nc6
        ((6, 21), 15),    # 2... Nf6 (Petrov)
    ],
    # 1. e4 e5 2. Nf3 Nc6 -> Trắng
    ((52, 36), (12, 28), (62, 45), (1, 18)): [
        ((61, 34), 55),   # 3. Bc4 (Italian Game)
        ((61, 25), 40),   # 3. Bb5 (Ruy Lopez)
        ((51, 35), 5),    # 3. d4 (Scotch)
    ],
    # 1. e4 e5 2. Nf3 Nc6 3. Bc4 -> Đen
    ((52, 36), (12, 28), (62, 45), (1, 18), (61, 34)): [
        ((5, 26), 55),    # 3... Bc5
        ((6, 21), 45),    # 3... Nf6
    ],
    # 1. e4 c5 -> Trắng
    ((52, 36), (10, 26)): [
        ((62, 45), 85),   # 2. Nf3
        ((57, 42), 15),   # 2. Nc3
    ],
    # 1. e4 c5 2. Nf3 -> Đen
    ((52, 36), (10, 26), (62, 45)): [
        ((11, 19), 45),   # 2... d6
        ((1, 18), 35),    # 2... Nc6
        ((12, 20), 20),   # 2... e6
    ],
    # 1. d4 d5 -> Trắng
    ((51, 35), (11, 27)): [
        ((50, 34), 85),   # 2. c4 (Queen's Gambit)
        ((62, 45), 15),   # 2. Nf3
    ],
    # 1. d4 d5 2. c4 -> Đen
    ((51, 35), (11, 27), (50, 34)): [
        ((12, 20), 60),   # 2... e6 (QGD)
        ((10, 18), 30),   # 2... c6 (Slav)
        ((27, 34), 10),   # 2... dxc4 (QGA)
    ],
    # 1. d4 Nf6 -> Trắng
    ((51, 35), (6, 21)): [
        ((50, 34), 80),   # 2. c4
        ((62, 45), 20),   # 2. Nf3
    ],
}


class ChessBot(Bot):
    CHANNEL = "chess"

    MAX_DEPTH = {"easy": 2, "normal": 4, "hard": 6}
    TIME_BUDGET = {"easy": 0.25, "normal": 0.8, "hard": 1.8}
    THINK_DELAY = {"easy": 0.45, "normal": 0.45, "hard": 0.3}
    BLUNDER = {"easy": 0.4, "normal": 0.0, "hard": 0.0}
    JITTER = {"easy": 35, "normal": 8, "hard": 2}

    def _book_move(self, room, colour: str) -> tuple[int, int] | None:
        """Tra sách khai cuộc. Trả về (frm, to) nếu khớp hoặc None."""
        history = tuple((m["from"], m["to"]) for m in room.moves)
        candidates = CHESS_BOOK.get(history)
        if not candidates:
            return None

        # Lấy danh sách nước hợp lệ hiện tại
        legal = ch.legal_moves(room.board, colour, room.castling, room.ep)

        valid_moves = []
        for (frm, to), weight in candidates:
            if frm in legal and any(opt["to"] == to for opt in legal[frm]):
                valid_moves.append(((frm, to), weight))

        if not valid_moves:
            return None

        if self.level == "easy" and self.rng.random() < 0.4:
            return None  # Mức dễ thỉnh thoảng bỏ qua sách để tự đánh

        if self.level == "hard":
            # Mức khó: chọn nước có trọng số cao nhất
            return max(valid_moves, key=lambda p: p[1])[0]

        # Mức thường: chọn ngẫu nhiên theo trọng số
        moves, weights = zip(*valid_moves)
        return self.rng.choices(moves, weights=weights, k=1)[0]

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        if room.status != "playing":
            raise BotError("Chưa tới lượt máy đi.")
        colour = room.color_of(mark)

        # 1. Thử đi theo sách khai cuộc (0ms CPU)
        book = self._book_move(room, colour)
        if book is not None:
            frm, to = book
            # Kiểm tra xem có cần phong cấp không
            promo = "Q" if (room.board[frm][1] == "P" and to // 8 in (0, 7)) else ""
            payload = {"from": frm, "to": to}
            if promo:
                payload["promo"] = promo
            return [("move", payload)]

        # 2. Tìm kiếm Alpha-Beta với TT và Heuristics
        pos = ChessPosition(list(room.board), colour, set(room.castling), room.ep)
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

        frm, to, _flag, promo = move
        payload = {"from": frm, "to": to}
        if promo:
            payload["promo"] = promo
        return [("move", payload)]
