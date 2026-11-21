"""Luật cờ vua đầy đủ.

Có đủ những thứ hay bị bỏ qua ở bản "cờ vua đơn giản": nhập thành hai bên, bắt
tốt qua đường (en passant), phong cấp, chiếu / chiếu hết / hết nước (stalemate),
luật 50 nước, lặp vị trí 3 lần, và thiếu quân không thể thắng.

Tên file là ``chessgame.py`` chứ không phải ``chess.py`` để không che gói
``chess`` trên PyPI nếu sau này ai đó cài nó vào cùng môi trường.

Quy ước toạ độ: bàn là list 64 phần tử, index 0 = a8, index 63 = h1. Nghĩa là
``row = index // 8`` đếm từ trên xuống (row 0 = hàng 8) và ``col = index % 8``
đếm từ trái sang (col 0 = cột a). Cách này khớp trực tiếp với thứ tự vẽ của
CSS grid ở frontend nên không cần đổi hệ ở giữa.

Quân được ghi bằng 2 ký tự: màu ("w"/"b") + loại ("K","Q","R","B","N","P"), ô
trống là chuỗi rỗng.

Module này là Python thuần, không I/O, không framework — luật chơi test được
độc lập.
"""

from __future__ import annotations

import time

from games import GameError, SeatedRoom, int_field, other_mark

FILES = "abcdefgh"
WHITE, BLACK = "w", "b"
PROMOTIONS = ("Q", "R", "B", "N")

# Giá trị chỉ dùng để sắp xếp danh sách quân đã bắt cho dễ đọc.
PIECE_ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4, "K": 5}

KNIGHT_STEPS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
DIAGONALS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
ORTHOGONALS = ((-1, 0), (1, 0), (0, -1), (0, 1))
ALL_STEPS = DIAGONALS + ORTHOGONALS

# Ô của vua và xe lúc đầu, dùng cho nhập thành và cho việc thu hồi quyền nhập
# thành khi một trong hai quân đó rời chỗ (hoặc bị ăn).
E1, A1, H1 = 60, 56, 63
E8, A8, H8 = 4, 0, 7


def on_board(row: int, col: int) -> bool:
    return 0 <= row < 8 and 0 <= col < 8


def other_color(color: str) -> str:
    return BLACK if color == WHITE else WHITE


def square_name(index: int) -> str:
    row, col = divmod(index, 8)
    return f"{FILES[col]}{8 - row}"


def start_board() -> list[str]:
    back = ("R", "N", "B", "Q", "K", "B", "N", "R")
    board = [""] * 64
    for col, kind in enumerate(back):
        board[col] = "b" + kind
        board[8 + col] = "bP"
        board[48 + col] = "wP"
        board[56 + col] = "w" + kind
    return board


def king_index(board: list[str], color: str) -> int:
    target = color + "K"
    for index, piece in enumerate(board):
        if piece == target:
            return index
    return -1


# --------------------------------------------------------------------------- #
# ô bị tấn công
# --------------------------------------------------------------------------- #
def square_attacked(board: list[str], index: int, by_color: str) -> bool:
    """Ô ``index`` có đang bị quân màu ``by_color`` tấn công không.

    Dò ngược từ ô cần kiểm tra ra ngoài (thay vì sinh hết nước đi của đối
    phương) để hàm này đủ nhanh cho việc lọc nước đi hợp lệ, vốn gọi nó rất
    nhiều lần cho mỗi nước.
    """
    row, col = divmod(index, 8)

    # Tốt: chỉ ăn chéo. Tốt trắng đi lên (row giảm) nên tốt trắng ăn được ô này
    # phải đứng ở hàng dưới nó.
    pawn_row = row + (1 if by_color == WHITE else -1)
    for dc in (-1, 1):
        if on_board(pawn_row, col + dc) and board[pawn_row * 8 + col + dc] == by_color + "P":
            return True

    for dr, dc in KNIGHT_STEPS:
        r, c = row + dr, col + dc
        if on_board(r, c) and board[r * 8 + c] == by_color + "N":
            return True

    for dr, dc in ALL_STEPS:
        r, c = row + dr, col + dc
        if on_board(r, c) and board[r * 8 + c] == by_color + "K":
            return True

    for steps, kinds in ((ORTHOGONALS, ("R", "Q")), (DIAGONALS, ("B", "Q"))):
        for dr, dc in steps:
            r, c = row + dr, col + dc
            while on_board(r, c):
                piece = board[r * 8 + c]
                if piece:
                    if piece[0] == by_color and piece[1] in kinds:
                        return True
                    break
                r += dr
                c += dc
    return False


def in_check(board: list[str], color: str) -> bool:
    king = king_index(board, color)
    return king >= 0 and square_attacked(board, king, other_color(color))


# --------------------------------------------------------------------------- #
# sinh nước đi
# --------------------------------------------------------------------------- #
def piece_targets(board: list[str], index: int, ep: int,
                  castling: set[str]) -> list[tuple[int, str]]:
    """Nước đi thô của quân ở ``index``: [(ô đích, cờ hiệu)].

    Cờ hiệu: "" thường, "double" tốt đi hai ô, "ep" bắt tốt qua đường,
    "castleK"/"castleQ" nhập thành. CHƯA kiểm tra vua của chính mình có bị
    chiếu sau nước đi hay không — việc đó do ``legal_moves`` lo.
    """
    piece = board[index]
    if not piece:
        return []
    color, kind = piece[0], piece[1]
    row, col = divmod(index, 8)
    out: list[tuple[int, str]] = []

    def enemy_or_empty(target: int) -> bool:
        return not board[target] or board[target][0] != color

    if kind == "P":
        step = -1 if color == WHITE else 1
        home_row = 6 if color == WHITE else 1
        ahead = row + step
        if on_board(ahead, col) and not board[ahead * 8 + col]:
            out.append((ahead * 8 + col, ""))
            jump = row + 2 * step
            if row == home_row and not board[jump * 8 + col]:
                out.append((jump * 8 + col, "double"))
        for dc in (-1, 1):
            r, c = ahead, col + dc
            if not on_board(r, c):
                continue
            target = r * 8 + c
            if board[target]:
                if board[target][0] != color:
                    out.append((target, ""))
            elif target == ep:
                out.append((target, "ep"))
        return out

    if kind == "N":
        for dr, dc in KNIGHT_STEPS:
            r, c = row + dr, col + dc
            if on_board(r, c) and enemy_or_empty(r * 8 + c):
                out.append((r * 8 + c, ""))
        return out

    if kind == "K":
        for dr, dc in ALL_STEPS:
            r, c = row + dr, col + dc
            if on_board(r, c) and enemy_or_empty(r * 8 + c):
                out.append((r * 8 + c, ""))
        # Nhập thành: ở đây chỉ xét ô trống và quân còn đúng chỗ. Điều kiện "vua
        # không bị chiếu và không đi qua ô bị tấn công" nằm ở legal_moves, vì
        # nó cần dò ô trung gian chứ không chỉ ô đích.
        if index == E1 and color == WHITE:
            if "K" in castling and board[H1] == "wR" and not board[61] and not board[62]:
                out.append((62, "castleK"))
            if ("Q" in castling and board[A1] == "wR"
                    and not board[59] and not board[58] and not board[57]):
                out.append((58, "castleQ"))
        elif index == E8 and color == BLACK:
            if "k" in castling and board[H8] == "bR" and not board[5] and not board[6]:
                out.append((6, "castleK"))
            if ("q" in castling and board[A8] == "bR"
                    and not board[3] and not board[2] and not board[1]):
                out.append((2, "castleQ"))
        return out

    steps = ORTHOGONALS if kind == "R" else DIAGONALS if kind == "B" else ALL_STEPS
    for dr, dc in steps:
        r, c = row + dr, col + dc
        while on_board(r, c):
            target = r * 8 + c
            if board[target]:
                if board[target][0] != color:
                    out.append((target, ""))
                break
            out.append((target, ""))
            r += dr
            c += dc
    return out


def apply_move(board: list[str], castling: set[str], frm: int, to: int,
               flag: str, promo: str = "Q") -> tuple[list[str], set[str], int, str]:
    """Thực hiện nước đi trên BẢN COPY. Trả về (bàn mới, quyền nhập thành mới,
    ô bắt tốt qua đường mới, quân bị ăn)."""
    board = list(board)
    castling = set(castling)
    piece = board[frm]
    color, kind = piece[0], piece[1]

    if flag == "ep":
        # Tốt bị bắt không nằm ở ô đích mà ở ngay sau nó.
        victim = to + (8 if color == WHITE else -8)
        captured = board[victim]
        board[victim] = ""
    else:
        captured = board[to]

    board[to] = piece
    board[frm] = ""

    new_ep = (frm + to) // 2 if flag == "double" else -1

    if kind == "P":
        last_row = 0 if color == WHITE else 7
        if to // 8 == last_row:
            board[to] = color + (promo if promo in PROMOTIONS else "Q")

    if flag == "castleK":
        if color == WHITE:
            board[H1], board[61] = "", "wR"
        else:
            board[H8], board[5] = "", "bR"
    elif flag == "castleQ":
        if color == WHITE:
            board[A1], board[59] = "", "wR"
        else:
            board[A8], board[3] = "", "bR"

    if kind == "K":
        castling -= {"K", "Q"} if color == WHITE else {"k", "q"}
    # Xe rời ô gốc hoặc bị ăn ngay tại ô gốc thì mất quyền bên đó.
    for square, right in ((H1, "K"), (A1, "Q"), (H8, "k"), (A8, "q")):
        if frm == square or to == square:
            castling.discard(right)

    return board, castling, new_ep, captured


def legal_moves(board: list[str], color: str, castling: set[str],
                ep: int) -> dict[int, list[dict]]:
    """Toàn bộ nước đi hợp lệ của ``color``: {ô đi -> [{to, flag, promo}]}."""
    checked_now = in_check(board, color)
    enemy = other_color(color)
    out: dict[int, list[dict]] = {}
    for frm, piece in enumerate(board):
        if not piece or piece[0] != color:
            continue
        moves = []
        for to, flag in piece_targets(board, frm, ep, castling):
            if flag in ("castleK", "castleQ"):
                # Không được nhập thành khi đang bị chiếu, cũng không được đi
                # xuyên qua ô bị kiểm soát.
                if checked_now or square_attacked(board, (frm + to) // 2, enemy):
                    continue
            after, _, _, _ = apply_move(board, castling, frm, to, flag)
            if in_check(after, color):
                continue
            last_row = 0 if color == WHITE else 7
            moves.append({"to": to, "flag": flag,
                          "promo": piece[1] == "P" and to // 8 == last_row})
        if moves:
            out[frm] = moves
    return out


# --------------------------------------------------------------------------- #
# ký hiệu nước đi (SAN)
# --------------------------------------------------------------------------- #
def move_san(board: list[str], frm: int, to: int, flag: str, promo: str,
             legal: dict[int, list[dict]], after: list[str],
             after_castling: set[str], after_ep: int) -> str:
    """Ký hiệu đại số chuẩn, ví dụ "Nf3", "exd5", "O-O", "Qh5#"."""
    piece = board[frm]
    color, kind = piece[0], piece[1]
    captured = bool(board[to]) or flag == "ep"

    if flag == "castleK":
        text = "O-O"
    elif flag == "castleQ":
        text = "O-O-O"
    elif kind == "P":
        text = (FILES[frm % 8] + "x" if captured else "") + square_name(to)
        if promo in PROMOTIONS:
            text += "=" + promo
    else:
        # Phân biệt khi hai quân cùng loại đều đi được tới ô đích.
        rivals = [f for f, moves in legal.items()
                  if f != frm and board[f] == piece and any(m["to"] == to for m in moves)]
        hint = ""
        if rivals:
            if all(f % 8 != frm % 8 for f in rivals):
                hint = FILES[frm % 8]
            elif all(f // 8 != frm // 8 for f in rivals):
                hint = str(8 - frm // 8)
            else:
                hint = square_name(frm)
        text = kind + hint + ("x" if captured else "") + square_name(to)

    enemy = other_color(color)
    if in_check(after, enemy):
        text += "#" if not legal_moves(after, enemy, after_castling, after_ep) else "+"
    return text


# --------------------------------------------------------------------------- #
# điều kiện hòa
# --------------------------------------------------------------------------- #
def insufficient_material(board: list[str]) -> bool:
    """Không bên nào còn đủ quân để chiếu hết, dù cố tình."""
    pieces = [p for p in board if p]
    kinds = [p[1] for p in pieces]
    if len(pieces) == 2:
        return True                                  # vua đối vua
    if len(pieces) == 3 and ("N" in kinds or "B" in kinds):
        return True                                  # vua + một quân nhẹ
    if len(pieces) == 4 and kinds.count("B") == 2:
        squares = [i for i, p in enumerate(board) if p and p[1] == "B"]
        # Hai tượng cùng màu ô thì không thể phủ hết bàn -> không chiếu hết được.
        return (sum(divmod(squares[0], 8)) % 2) == (sum(divmod(squares[1], 8)) % 2)
    return False


def position_key(board: list[str], color: str, castling: set[str], ep: int) -> str:
    """Khoá so sánh vị trí cho luật lặp 3 lần.

    Quân luôn là 2 ký tự, ô trống là ".", nên chuỗi giải mã được một cách duy
    nhất và không có hai vị trí khác nhau nào cho ra cùng khoá.
    """
    cells = "".join(p or "." for p in board)
    return f"{cells}|{color}|{''.join(sorted(castling))}|{ep}"


# --------------------------------------------------------------------------- #
# phòng
# --------------------------------------------------------------------------- #
class ChessRoom(SeatedRoom):
    """Ván cờ vua trong khung phòng hai ghế của hub.

    Ghế vẫn là "X"/"O" như mọi game khác, nhưng MÀU quân đổi qua lại sau mỗi
    ván (``white_mark``): cờ vua bắt buộc Trắng đi trước, nên muốn công bằng
    thì phải đổi màu chứ không thể đổi người đi trước như caro. Vì vậy
    ``first_turn`` của lớp cha không được dùng ở đây.
    """

    CHANNEL = "chess"
    START_STATUS = "playing"
    HAS_CLOCK = True
    DEFAULT_MODE = "standard"
    MODES = {
        "standard": {"label": "Cờ vua chuẩn 8x8"},
    }
    CLOCK_PRESETS = {
        "none": (0, 0),
        "180+2": (180, 2),
        "600+0": (600, 0),
        "900+5": (900, 5),
    }

    def __init__(self, code: str, mode: str = "") -> None:
        self.match_no = 0
        self.white_mark = "X"
        self.clock_preset = "none"
        self.clock_initial = 0.0
        self.clock_increment = 0.0
        self.clock_remain: dict[str, float] = {"X": 0.0, "O": 0.0}
        self.turn_started_at = 0.0
        super().__init__(code, mode)
        self.reset_match()

    def apply_initial_config(self, config: dict) -> None:
        preset = str((config or {}).get("clock", "none"))
        if preset in self.CLOCK_PRESETS:
            init, inc = self.CLOCK_PRESETS[preset]
            self.clock_preset = preset
            self.clock_initial = float(init)
            self.clock_increment = float(inc)
            self.clock_remain = {"X": float(init), "O": float(init)}
            self.turn_started_at = time.time() if self.status == "playing" and init > 0 else 0.0

    # ---- tiện ích ---------------------------------------------------------- #
    def color_of(self, mark: str) -> str:
        return WHITE if mark == self.white_mark else BLACK

    def mark_of(self, color: str) -> str:
        return self.white_mark if color == WHITE else other_mark(self.white_mark)

    def _seat_label(self, mark: str) -> str:
        return "Trắng" if mark == self.white_mark else "Đen"

    # ---- vòng đời ván ------------------------------------------------------ #
    def reset_match(self) -> None:
        # Ván 1: X trắng. Ván 2: O trắng. Cứ thế đổi để không ai luôn đi trước.
        self.white_mark = "X" if self.match_no % 2 == 0 else "O"
        self.board = start_board()
        self.castling = {"K", "Q", "k", "q"}
        self.ep = -1
        self.halfmove = 0
        self.turn = self.white_mark
        self.moves: list[dict] = []
        self.last_move = (-1, -1)
        self.captured: dict[str, list[str]] = {"X": [], "O": []}
        self.draw_offer = ""
        self.undo_offer = ""
        self._undo_stack: list[dict] = []
        self.note = ""
        self.seen: dict[str, int] = {}
        init = float(getattr(self, "clock_initial", 0.0))
        self.clock_remain = {"X": init, "O": init}
        self.turn_started_at = time.time() if self.status == "playing" and init > 0 else 0.0
        self._refresh()
        self._remember()

    def on_match_start(self) -> None:
        self.match_no += 1
        if self.clock_initial > 0:
            self.turn_started_at = time.time()
        white = self.seat(self.white_mark)
        self.system(f"Ván mới. {white.name if white else 'Trắng'} cầm quân Trắng, đi trước.")

    def _refresh(self) -> None:
        """Tính lại nước đi hợp lệ và trạng thái chiếu của bên tới lượt."""
        color = self.color_of(self.turn)
        self.legal = legal_moves(self.board, color, self.castling, self.ep)
        self.check = in_check(self.board, color)

    def progress_token(self) -> tuple:
        return super().progress_token() + (len(self.moves),)

    def _remember(self) -> int:
        """Ghi nhận vị trí hiện tại, trả về số lần nó đã xuất hiện (theo luật FIDE về ô ep)."""
        has_legal_ep = any(
            m.get("flag") == "ep"
            for moves in self.legal.values()
            for m in moves
        )
        ep_key = self.ep if has_legal_ep else -1
        key = position_key(self.board, self.color_of(self.turn), self.castling, ep_key)
        self.seen[key] = self.seen.get(key, 0) + 1
        return self.seen[key]

    # ---- đồng hồ thi đấu -------------------------------------------------- #
    def _spend_clock(self, mark: str) -> float:
        now = time.time()
        if self.clock_initial > 0 and self.turn_started_at > 0:
            elapsed = max(0.0, now - self.turn_started_at)
            self.clock_remain[mark] = max(0.0, self.clock_remain.get(mark, self.clock_initial) - elapsed)
        return now

    def tick(self) -> bool:
        if self.status != "playing" or self.clock_initial <= 0 or self.turn_started_at <= 0:
            return False
        rem = self.clock_remain.get(self.turn, self.clock_initial) - max(0.0, time.time() - self.turn_started_at)
        if rem <= 0:
            self.clock_remain[self.turn] = 0.0
            loser = self.seat(self.turn)
            winner = other_mark(self.turn)
            loser_name = loser.name if loser else self._seat_label(self.turn)
            self.note = f"{loser_name} hết thời gian suy nghĩ."
            self.system(f"{loser_name} hết giờ! {self._seat_label(winner)} thắng.")
            self.finish(winner)
            return True
        return False

    # ---- hành động --------------------------------------------------------- #
    def handle(self, uid: str, action: str, msg: dict) -> None:
        if action == "move":
            self.move(uid, int_field(msg, "from", -1), int_field(msg, "to", -1),
                      str(msg.get("promo", "")).upper()[:1])
        elif action == "draw":
            self.offer_draw(uid)
        elif action == "draw-accept":
            self.accept_draw(uid)
        elif action == "draw-decline":
            self.decline_draw(uid)
        elif action == "undo":
            self.request_undo(uid)
        elif action == "undo-accept":
            self.accept_undo(uid)
        elif action == "undo-decline":
            self.decline_undo(uid)
        else:
            raise GameError("Hành động không hợp lệ.")

    def _seated(self, uid: str):
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn chỉ đang xem, không đi được.")
        return player

    def move(self, uid: str, frm: int, to: int, promo: str) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if player.mark != self.turn:
            raise GameError("Chưa tới lượt bạn.")

        options = self.legal.get(frm)
        if not options:
            raise GameError("Quân này không có nước đi nào.")
        chosen = next((m for m in options if m["to"] == to), None)
        if chosen is None:
            raise GameError("Nước đi không hợp lệ.")

        if chosen["promo"]:
            promo = promo if promo in PROMOTIONS else "Q"
        else:
            promo = ""

        now = self._spend_clock(player.mark)
        if self.clock_initial > 0 and self.clock_remain.get(player.mark, 0.0) <= 0:
            winner = other_mark(player.mark)
            self.note = f"{player.name} hết thời gian suy nghĩ."
            self.system(f"{player.name} hết giờ! {self._seat_label(winner)} thắng.")
            self.finish(winner)
            return

        self._undo_stack.append({
            "board": list(self.board),
            "castling": set(self.castling),
            "ep": self.ep,
            "halfmove": self.halfmove,
            "turn": self.turn,
            "last_move": self.last_move,
            "captured": {"X": list(self.captured["X"]), "O": list(self.captured["O"])},
            "moves_len": len(self.moves),
            "seen": dict(self.seen),
            "clock_remain": dict(self.clock_remain),
        })

        piece = self.board[frm]
        after, after_castling, after_ep, captured = apply_move(
            self.board, self.castling, frm, to, chosen["flag"], promo or "Q")
        san = move_san(self.board, frm, to, chosen["flag"], promo, self.legal,
                       after, after_castling, after_ep)

        if captured:
            self.captured[player.mark].append(captured)
            self.captured[player.mark].sort(key=lambda p: PIECE_ORDER.get(p[1], 9))

        # Đồng hồ 50 nước chỉ reset khi có tốt đi hoặc có quân bị ăn.
        self.halfmove = 0 if (piece[1] == "P" or captured) else self.halfmove + 1
        self.board, self.castling, self.ep = after, after_castling, after_ep
        self.last_move = (frm, to)
        self.moves.append({"san": san, "mark": player.mark, "from": frm, "to": to,
                           "ts": time.time()})
        self.turn = other_mark(player.mark)
        self.draw_offer = ""
        self.undo_offer = ""
        self.touched = time.time()
        if self.clock_initial > 0:
            self.clock_remain[player.mark] = self.clock_remain.get(player.mark, 0.0) + self.clock_increment
            self.turn_started_at = now

        self._refresh()
        repeats = self._remember()
        self._settle(player, repeats)

    def _settle(self, mover, repeats: int) -> None:
        """Kiểm tra mọi cách ván có thể kết thúc, sau khi đã đổi lượt."""
        if not self.legal:
            if self.check:
                self.note = f"Chiếu hết ở nước {len(self.moves)}."
                self.system(f"{mover.name} chiếu hết!")
                self.finish(mover.mark)
            else:
                self.note = "Hết nước đi mà không bị chiếu (stalemate)."
                self.system("Hòa: bên tới lượt hết nước đi.")
                self.finish("draw")
            return
        if self.halfmove >= 100:
            self.note = "Luật 50 nước: 50 nước liền không ăn quân, không đi tốt."
            self.system("Hòa theo luật 50 nước.")
            self.finish("draw")
            return
        if insufficient_material(self.board):
            self.note = "Hai bên không còn đủ quân để chiếu hết."
            self.system("Hòa vì thiếu quân.")
            self.finish("draw")
            return
        if repeats >= 3:
            self.note = "Vị trí lặp lại 3 lần."
            self.system("Hòa vì lặp vị trí 3 lần.")
            self.finish("draw")
            return
        if self.check:
            seat = self.seat(self.turn)
            self.system(f"{seat.name if seat else self.turn} bị chiếu.")

    # ---- xin hòa ----------------------------------------------------------- #
    def offer_draw(self, uid: str) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if self.draw_offer and self.draw_offer != player.mark:
            self.accept_draw(uid)
            return
        if self.draw_offer == player.mark:
            self.draw_offer = ""
            self.system(f"{player.name} rút lại đề nghị hòa.")
        else:
            self.draw_offer = player.mark
            self.system(f"{player.name} đề nghị hòa.")
        self.touched = time.time()

    def accept_draw(self, uid: str) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if not self.draw_offer or self.draw_offer == player.mark:
            raise GameError("Không có đề nghị hòa nào để đồng ý.")
        self.draw_offer = ""
        self.note = "Hai bên đồng ý hòa."
        self.system(f"{player.name} đồng ý hòa. Ván hòa.")
        self.finish("draw")

    def decline_draw(self, uid: str) -> None:
        player = self._seated(uid)
        if not self.draw_offer or self.draw_offer == player.mark:
            return
        self.draw_offer = ""
        self.system(f"{player.name} từ chối hòa.")
        self.touched = time.time()

    # ---- xin đi lại (Undo) ------------------------------------------------- #
    def _apply_undo_plies(self, plies: int) -> None:
        if self.clock_initial > 0:
            self._spend_clock(self.turn)
        snap = None
        for _ in range(plies):
            if self._undo_stack:
                snap = self._undo_stack.pop()
        if snap is None:
            return
        self.board = snap["board"]
        self.castling = snap["castling"]
        self.ep = snap["ep"]
        self.halfmove = snap["halfmove"]
        self.turn = snap["turn"]
        self.last_move = snap["last_move"]
        self.captured = snap["captured"]
        del self.moves[snap["moves_len"]:]
        self.seen = snap["seen"]
        self.draw_offer = ""
        self.undo_offer = ""
        if self.clock_initial > 0:
            saved_clk = snap.get("clock_remain")
            if isinstance(saved_clk, dict):
                for m in self.SEATS:
                    if m in saved_clk:
                        self.clock_remain[m] = min(self.clock_remain.get(m, saved_clk[m]), saved_clk[m])
            self.turn_started_at = time.time()
        self._refresh()

    def request_undo(self, uid: str) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if not self._undo_stack:
            raise GameError("Chưa có nước nào để đi lại.")

        opp = self.seat(other_mark(player.mark))
        if opp and opp.bot:
            plies = 2 if (self.turn == player.mark and len(self._undo_stack) >= 2) else 1
            if self.turn == player.mark and len(self._undo_stack) < 2 and self._undo_stack[-1]["turn"] != player.mark:
                raise GameError("Bạn chưa đi nước nào để đi lại.")
            self._apply_undo_plies(plies)
            self.system(f"{player.name} đi lại nước vừa rồi.")
            self.touched = time.time()
            return

        if self.undo_offer and self.undo_offer != player.mark:
            self.accept_undo(uid)
            return
        if self.undo_offer == player.mark:
            self.undo_offer = ""
            self.system(f"{player.name} rút lại yêu cầu đi lại.")
        else:
            self.undo_offer = player.mark
            self.system(f"{player.name} xin đi lại nước vừa rồi.")
        self.touched = time.time()

    def accept_undo(self, uid: str) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if not self.undo_offer or self.undo_offer == player.mark:
            raise GameError("Không có yêu cầu đi lại nào để đồng ý.")
        req_mark = self.undo_offer
        self.undo_offer = ""
        plies = 2 if (self.turn == req_mark and len(self._undo_stack) >= 2) else 1
        self._apply_undo_plies(plies)
        self.system(f"{player.name} đồng ý cho đi lại.")
        self.touched = time.time()

    def decline_undo(self, uid: str) -> None:
        player = self._seated(uid)
        if not self.undo_offer or self.undo_offer == player.mark:
            return
        self.undo_offer = ""
        self.system(f"{player.name} từ chối yêu cầu đi lại.")
        self.touched = time.time()

    # ---- serialize --------------------------------------------------------- #
    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        mine = player.mark if player else ""

        # Chỉ người tới lượt cần danh sách nước đi; gửi cho người khác vừa vô
        # ích vừa nặng payload.
        legal: dict[str, list[dict]] = {}
        if mine and mine == self.turn and self.status == "playing":
            legal = {str(frm): [{"to": m["to"], "promo": m["promo"]} for m in moves]
                     for frm, moves in self.legal.items()}

        return {
            "board": self.board,
            "turn": self.turn,
            "whiteMark": self.white_mark,
            "colorOf": {"X": self.color_of("X"), "O": self.color_of("O")},
            "legal": legal,
            "lastMove": list(self.last_move),
            "check": self.check,
            "checkMark": self.turn if self.check and self.status == "playing" else "",
            "kingIndex": {"X": king_index(self.board, self.color_of("X")),
                          "O": king_index(self.board, self.color_of("O"))},
            "moves": self.moves[-120:],
            "moveCount": len(self.moves),
            "captured": self.captured,
            "halfmove": self.halfmove,
            "drawOffer": self.draw_offer,
            "undoOffer": self.undo_offer,
            "canUndo": self.status == "playing" and len(self._undo_stack) > 0,
            "clock": {
                "enabled": self.clock_initial > 0,
                "preset": self.clock_preset,
                "initial": self.clock_initial,
                "increment": self.clock_increment,
                "remain": dict(self.clock_remain),
                "turnStartedAt": self.turn_started_at,
            },
            "serverNow": time.time(),
            "note": self.note,
        }
