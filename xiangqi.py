"""Luật cờ tướng (xiangqi).

Có đủ các luật đặc trưng mà bản "cờ tướng đơn giản" thường bỏ:
  - Tướng và Sĩ không ra khỏi cung 3x3.
  - Tượng đi hai ô chéo, bị chặn "mắt tượng", và không qua sông.
  - Mã bị chặn "chân mã".
  - Pháo muốn ăn phải nhảy qua đúng một quân bất kỳ.
  - Binh/Tốt chỉ đi ngang sau khi qua sông.
  - Luật "lộ mặt tướng": hai tướng không được đối diện trên cùng một cột mà
    giữa không có quân nào.
  - Hết nước đi là THUA (khác cờ vua: cờ tướng không có hòa vì bí nước).

Quy ước toạ độ: bàn 9 cột x 10 hàng, list 90 phần tử, ``index = row * 9 + col``.
Row 0 ở phía Đen (trên), row 9 ở phía Đỏ (dưới) — khớp thứ tự vẽ của CSS grid.
Cột đặt tên a..i từ trái sang, hàng đánh số 10..1 từ trên xuống, nên ô dưới
cùng bên trái là a1.

Quân ghi bằng 2 ký tự: màu ("r" Đỏ / "b" Đen) + loại:
    K Tướng, A Sĩ, E Tượng, H Mã, R Xe, C Pháo, P Binh/Tốt.
"""

from __future__ import annotations

import time

from games import GameError, SeatedRoom, int_field, other_mark

COLS, ROWS = 9, 10
CELLS = COLS * ROWS
FILES = "abcdefghi"
RED, BLACK = "r", "b"

ORTHOGONALS = ((-1, 0), (1, 0), (0, -1), (0, 1))
DIAGONALS = ((-1, -1), (-1, 1), (1, -1), (1, 1))

# (dr, dc) của nước mã, kèm (dr, dc) của "chân mã" — ô kề tướng phải trống.
HORSE_STEPS = (
    (-2, -1, -1, 0), (-2, 1, -1, 0), (2, -1, 1, 0), (2, 1, 1, 0),
    (-1, -2, 0, -1), (1, -2, 0, -1), (-1, 2, 0, 1), (1, 2, 0, 1),
)

# Tên quân để hiển thị và để ghi biên bản.
PIECE_NAME = {
    "K": "Tướng", "A": "Sĩ", "E": "Tượng", "H": "Mã",
    "R": "Xe", "C": "Pháo", "P": "Binh",
}
PIECE_ABBR = {"K": "Tg", "A": "S", "E": "T", "H": "M", "R": "X", "C": "P", "P": "B"}
PIECE_ORDER = {"R": 0, "C": 1, "H": 2, "E": 3, "A": 4, "P": 5, "K": 6}

# Không ăn quân liên tục bao nhiêu nửa nước thì xử hòa. Luật thi đấu thật phức
# tạp hơn nhiều (60 nước + các thế lặp cấm); đây là mức thực dụng cho hub.
IDLE_DRAW_PLIES = 120


def on_board(row: int, col: int) -> bool:
    return 0 <= row < ROWS and 0 <= col < COLS


def other_color(color: str) -> str:
    return BLACK if color == RED else RED


def square_name(index: int) -> str:
    row, col = divmod(index, COLS)
    return f"{FILES[col]}{ROWS - row}"


def in_palace(color: str, row: int, col: int) -> bool:
    if not 3 <= col <= 5:
        return False
    return 7 <= row <= 9 if color == RED else 0 <= row <= 2


def own_half(color: str, row: int) -> bool:
    """Phía sông của mình. Đỏ ở nửa dưới (row 5-9), Đen ở nửa trên (row 0-4)."""
    return row >= 5 if color == RED else row <= 4


def crossed_river(color: str, row: int) -> bool:
    return row <= 4 if color == RED else row >= 5


def start_board() -> list[str]:
    board = [""] * CELLS
    back = ("R", "H", "E", "A", "K", "A", "E", "H", "R")
    for col, kind in enumerate(back):
        board[col] = BLACK + kind
        board[9 * COLS + col] = RED + kind
    board[2 * COLS + 1] = BLACK + "C"
    board[2 * COLS + 7] = BLACK + "C"
    board[7 * COLS + 1] = RED + "C"
    board[7 * COLS + 7] = RED + "C"
    for col in (0, 2, 4, 6, 8):
        board[3 * COLS + col] = BLACK + "P"
        board[6 * COLS + col] = RED + "P"
    return board


def king_index(board: list[str], color: str) -> int:
    target = color + "K"
    for index, piece in enumerate(board):
        if piece == target:
            return index
    return -1


# --------------------------------------------------------------------------- #
# sinh nước đi
# --------------------------------------------------------------------------- #
def piece_targets(board: list[str], index: int) -> list[int]:
    """Nước đi thô của quân ở ``index``, chưa xét an toàn cho tướng của mình."""
    piece = board[index]
    if not piece:
        return []
    color, kind = piece[0], piece[1]
    row, col = divmod(index, COLS)
    out: list[int] = []

    def empty(r: int, c: int) -> bool:
        return on_board(r, c) and not board[r * COLS + c]

    def landable(r: int, c: int) -> bool:
        if not on_board(r, c):
            return False
        target = board[r * COLS + c]
        return not target or target[0] != color

    if kind == "K":
        for dr, dc in ORTHOGONALS:
            r, c = row + dr, col + dc
            if in_palace(color, r, c) and landable(r, c):
                out.append(r * COLS + c)
        return out

    if kind == "A":
        for dr, dc in DIAGONALS:
            r, c = row + dr, col + dc
            if in_palace(color, r, c) and landable(r, c):
                out.append(r * COLS + c)
        return out

    if kind == "E":
        for dr, dc in DIAGONALS:
            r, c = row + 2 * dr, col + 2 * dc
            if not on_board(r, c) or not own_half(color, r):
                continue
            if not empty(row + dr, col + dc):      # mắt tượng bị chặn
                continue
            if landable(r, c):
                out.append(r * COLS + c)
        return out

    if kind == "H":
        for dr, dc, lr, lc in HORSE_STEPS:
            r, c = row + dr, col + dc
            if not on_board(r, c) or not empty(row + lr, col + lc):
                continue
            if landable(r, c):
                out.append(r * COLS + c)
        return out

    if kind == "R":
        for dr, dc in ORTHOGONALS:
            r, c = row + dr, col + dc
            while on_board(r, c):
                target = r * COLS + c
                if board[target]:
                    if board[target][0] != color:
                        out.append(target)
                    break
                out.append(target)
                r += dr
                c += dc
        return out

    if kind == "C":
        for dr, dc in ORTHOGONALS:
            r, c = row + dr, col + dc
            jumped = False
            while on_board(r, c):
                target = r * COLS + c
                if not board[target]:
                    if not jumped:
                        out.append(target)          # đi như xe khi không ăn
                elif not jumped:
                    jumped = True                   # đây là ngòi
                else:
                    if board[target][0] != color:
                        out.append(target)          # quân đầu tiên sau ngòi
                    break
                r += dr
                c += dc
        return out

    if kind == "P":
        step = -1 if color == RED else 1
        if landable(row + step, col):
            out.append((row + step) * COLS + col)
        if crossed_river(color, row):
            for dc in (-1, 1):
                if landable(row, col + dc):
                    out.append(row * COLS + col + dc)
        return out

    return out


def generals_face(board: list[str]) -> bool:
    """Hai tướng đối diện trên cùng cột, giữa không có quân nào."""
    red, black = king_index(board, RED), king_index(board, BLACK)
    if red < 0 or black < 0:
        return False
    if red % COLS != black % COLS:
        return False
    col = red % COLS
    low, high = sorted((red // COLS, black // COLS))
    return all(not board[r * COLS + col] for r in range(low + 1, high))


def in_check(board: list[str], color: str) -> bool:
    """Tướng của ``color`` đang bị bắt, hoặc đang lộ mặt với tướng đối phương.

    Dò ngược từ ô tướng thay vì sinh nước đi của cả bên kia, vì hàm này được
    gọi một lần cho mỗi nước ứng viên khi lọc nước hợp lệ.
    """
    king = king_index(board, color)
    if king < 0:
        return True
    if generals_face(board):
        return True

    enemy = other_color(color)
    row, col = divmod(king, COLS)

    # Xe (quân đầu tiên trên đường) và Pháo (quân thứ hai, sau ngòi).
    for dr, dc in ORTHOGONALS:
        r, c = row + dr, col + dc
        screen = False
        while on_board(r, c):
            piece = board[r * COLS + c]
            if piece:
                if not screen:
                    if piece == enemy + "R":
                        return True
                    screen = True
                else:
                    if piece == enemy + "C":
                        return True
                    break
            r += dr
            c += dc

    # Mã: nằm ở 8 vị trí quanh tướng, chân mã tính từ phía con mã.
    for dr, dc, _lr, _lc in HORSE_STEPS:
        hr, hc = row + dr, col + dc
        if not on_board(hr, hc) or board[hr * COLS + hc] != enemy + "H":
            continue
        if abs(dr) == 2:
            leg_r, leg_c = hr + (-dr) // 2, hc
        else:
            leg_r, leg_c = hr, hc + (-dc) // 2
        if not board[leg_r * COLS + leg_c]:
            return True

    # Binh/Tốt kề tướng. Nước ngang chỉ có sau khi quân đó qua sông, mà hàng
    # của nó lúc ăn ngang chính là hàng của tướng.
    if enemy == BLACK:
        spots = [(row - 1, col)]
        if crossed_river(BLACK, row):
            spots += [(row, col - 1), (row, col + 1)]
    else:
        spots = [(row + 1, col)]
        if crossed_river(RED, row):
            spots += [(row, col - 1), (row, col + 1)]
    for r, c in spots:
        if on_board(r, c) and board[r * COLS + c] == enemy + "P":
            return True

    # Sĩ và Tượng địch không bao giờ tới được cung của ta, Tướng địch đã tính ở
    # phần lộ mặt — nên không cần dò thêm.
    return False


def apply_move(board: list[str], frm: int, to: int) -> tuple[list[str], str]:
    board = list(board)
    captured = board[to]
    board[to] = board[frm]
    board[frm] = ""
    return board, captured


def legal_moves(board: list[str], color: str) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for frm, piece in enumerate(board):
        if not piece or piece[0] != color:
            continue
        targets = []
        for to in piece_targets(board, frm):
            after, _ = apply_move(board, frm, to)
            if not in_check(after, color):
                targets.append(to)
        if targets:
            out[frm] = targets
    return out


def move_note(board: list[str], frm: int, to: int, after: list[str]) -> str:
    """Biên bản dạng "Mb1-c3" / "Xa1xa7", thêm "+" khi chiếu, "#" khi hết nước."""
    piece = board[frm]
    captured = board[to]
    text = (f"{PIECE_ABBR[piece[1]]}{square_name(frm)}"
            f"{'x' if captured else '-'}{square_name(to)}")
    enemy = other_color(piece[0])
    if in_check(after, enemy):
        text += "#" if not legal_moves(after, enemy) else "+"
    return text


def position_key(board: list[str], color: str) -> str:
    return "".join(p or "." for p in board) + "|" + color


# --------------------------------------------------------------------------- #
# phòng
# --------------------------------------------------------------------------- #
class XiangqiRoom(SeatedRoom):
    """Ván cờ tướng trong khung phòng hai ghế của hub.

    Cờ tướng luôn Đỏ đi trước, nên giống ``ChessRoom``: đổi MÀU giữa hai ghế
    sau mỗi ván (``red_mark``) thay vì đổi người đi trước. ``first_turn`` của
    lớp cha không dùng ở đây.
    """

    CHANNEL = "xiangqi"
    START_STATUS = "playing"
    HAS_CLOCK = True
    DEFAULT_MODE = "standard"
    MODES = {
        "standard": {"label": "Cờ tướng chuẩn 9x10"},
    }
    CLOCK_PRESETS = {
        "none": (0, 0),
        "180+2": (180, 2),
        "600+0": (600, 0),
        "900+5": (900, 5),
    }

    def __init__(self, code: str, mode: str = "") -> None:
        self.match_no = 0
        self.red_mark = "X"
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
        return RED if mark == self.red_mark else BLACK

    def _seat_label(self, mark: str) -> str:
        return "Đỏ" if mark == self.red_mark else "Đen"

    # ---- vòng đời ván ------------------------------------------------------ #
    def reset_match(self) -> None:
        self.red_mark = "X" if self.match_no % 2 == 0 else "O"
        self.board = start_board()
        self.turn = self.red_mark
        self.idle = 0                      # số nửa nước liên tiếp không ăn quân
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
        red = self.seat(self.red_mark)
        self.system(f"Ván mới. {red.name if red else 'Đỏ'} cầm quân Đỏ, đi trước.")

    def _refresh(self) -> None:
        color = self.color_of(self.turn)
        self.legal = legal_moves(self.board, color)
        self.check = in_check(self.board, color)

    def progress_token(self) -> tuple:
        return super().progress_token() + (len(self.moves),)

    def _remember(self) -> int:
        key = position_key(self.board, self.color_of(self.turn))
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
            self.move(uid, int_field(msg, "from", -1), int_field(msg, "to", -1))
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

    def move(self, uid: str, frm: int, to: int) -> None:
        player = self._seated(uid)
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if player.mark != self.turn:
            raise GameError("Chưa tới lượt bạn.")
        targets = self.legal.get(frm)
        if not targets:
            raise GameError("Quân này không có nước đi nào.")
        if to not in targets:
            raise GameError("Nước đi không hợp lệ.")

        now = self._spend_clock(player.mark)
        if self.clock_initial > 0 and self.clock_remain.get(player.mark, 0.0) <= 0:
            winner = other_mark(player.mark)
            self.note = f"{player.name} hết thời gian suy nghĩ."
            self.system(f"{player.name} hết giờ! {self._seat_label(winner)} thắng.")
            self.finish(winner)
            return

        self._undo_stack.append({
            "board": list(self.board),
            "turn": self.turn,
            "idle": self.idle,
            "last_move": self.last_move,
            "captured": {"X": list(self.captured["X"]), "O": list(self.captured["O"])},
            "moves_len": len(self.moves),
            "seen": dict(self.seen),
            "clock_remain": dict(self.clock_remain),
        })

        after, captured = apply_move(self.board, frm, to)
        note = move_note(self.board, frm, to, after)

        if captured:
            self.captured[player.mark].append(captured)
            self.captured[player.mark].sort(key=lambda p: PIECE_ORDER.get(p[1], 9))
            self.idle = 0
        else:
            self.idle += 1

        self.board = after
        self.last_move = (frm, to)
        self.moves.append({"note": note, "mark": player.mark, "from": frm, "to": to,
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
        if not self.legal:
            # Cờ tướng không có hòa vì bí nước: hết nước đi là thua.
            self.note = ("Chiếu hết." if self.check
                         else "Hết nước đi (bí) — cờ tướng xử thua bên không còn nước.")
            self.system(f"{mover.name} thắng: {self.note}")
            self.finish(mover.mark)
            return
        if self.idle >= IDLE_DRAW_PLIES:
            self.note = f"{IDLE_DRAW_PLIES // 2} nước liền không bên nào ăn quân."
            self.system("Hòa vì quá lâu không ăn quân.")
            self.finish("draw")
            return
        if repeats >= 3:
            self.note = "Thế cờ lặp lại 3 lần."
            self.system("Hòa vì lặp thế 3 lần.")
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
        self.turn = snap["turn"]
        self.idle = snap["idle"]
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

        legal: dict[str, list[int]] = {}
        if mine and mine == self.turn and self.status == "playing":
            legal = {str(frm): targets for frm, targets in self.legal.items()}

        return {
            "cols": COLS,
            "rows": ROWS,
            "board": self.board,
            "turn": self.turn,
            "redMark": self.red_mark,
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
            "pieceNames": PIECE_NAME,
            "idle": self.idle,
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
