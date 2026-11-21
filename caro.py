"""Luật cờ caro / XO. Thắng bằng N quân liên tiếp theo hàng, cột hoặc chéo."""

from __future__ import annotations

import time

from games import GameError, SeatedRoom, int_field, other_mark

# 4 hướng là đủ phủ 8 chiều, vì mỗi hướng ta dò cả hai phía.
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


def winning_line(board: list[str], size: int, win_len: int, index: int) -> list[int] | None:
    """Đường thắng đi qua ô ``index``, hoặc None.

    Chỉ cần dò từ ô vừa đánh: đường thắng mới xuất hiện thì bắt buộc phải chứa
    ô đó, nên không phải quét cả bàn.
    """
    mark = board[index]
    if not mark:
        return None
    row, col = divmod(index, size)
    for dr, dc in DIRECTIONS:
        cells = [index]
        for step in (-1, 1):
            r, c = row + dr * step, col + dc * step
            while 0 <= r < size and 0 <= c < size and board[r * size + c] == mark:
                cells.append(r * size + c)
                r += dr * step
                c += dc * step
        if len(cells) >= win_len:
            return sorted(cells)
    return None


class CaroRoom(SeatedRoom):
    CHANNEL = "caro"
    START_STATUS = "playing"
    DEFAULT_MODE = "caro19"
    MODES = {
        "xo": {"label": "XO cổ điển 3x3", "size": 3, "win": 3},
        "caro9": {"label": "Caro nhỏ 9x9", "size": 9, "win": 5},
        "caro15": {"label": "Caro 15x15", "size": 15, "win": 5},
        "caro19": {"label": "Caro chuẩn 19x19", "size": 19, "win": 5},
        "caro25": {"label": "Caro rộng 25x25 (625 ô)", "size": 25, "win": 5},
        "caro35": {"label": "Caro siêu rộng 35x35 (1.225 ô)", "size": 35, "win": 5},
        "caro50": {"label": "Caro mênh mông 50x50 (2.500 ô)", "size": 50, "win": 5},
    }

    def __init__(self, code: str, mode: str = "") -> None:
        super().__init__(code, mode)
        self.reset_match()

    @property
    def size(self) -> int:
        return self.MODES[self.mode]["size"]

    @property
    def win_len(self) -> int:
        return self.MODES[self.mode]["win"]

    # ---- vòng đời ván ------------------------------------------------------ #
    def reset_match(self) -> None:
        self.board = [""] * (self.size * self.size)
        self.turn = self.first_turn
        self.win_line: list[int] = []
        self.last_move = -1
        self.move_count = 0

    def on_match_start(self) -> None:
        self.system(f"Ván mới, {self.turn} đi trước.")

    def progress_token(self) -> tuple:
        return super().progress_token() + (self.move_count,)

    # ---- hành động --------------------------------------------------------- #
    def handle(self, uid: str, action: str, msg: dict) -> None:
        if action != "move":
            raise GameError("Hành động không hợp lệ.")
        self.move(uid, int_field(msg, "index", -1))

    def move(self, uid: str, index: int) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn chỉ đang xem, không đánh được.")
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if player.mark != self.turn:
            raise GameError("Chưa tới lượt bạn.")
        if not 0 <= index < len(self.board):
            raise GameError("Ô không hợp lệ.")
        if self.board[index]:
            raise GameError("Ô này đã có quân.")

        self.board[index] = player.mark
        self.last_move = index
        self.move_count += 1
        self.touched = time.time()

        line = winning_line(self.board, self.size, self.win_len, index)
        if line:
            self.win_line = line
            self.system(f"{player.name} ({player.mark}) thắng!")
            self.finish(player.mark)
        elif self.move_count >= len(self.board):
            self.system("Hòa, hết ô.")
            self.finish("draw")
        else:
            self.turn = other_mark(player.mark)

    # ---- serialize --------------------------------------------------------- #
    def match_view(self, uid: str) -> dict:
        return {
            "size": self.size,
            "winLen": self.win_len,
            "board": self.board,
            "turn": self.turn,
            "winLine": self.win_line,
            "lastMove": self.last_move,
            "moveCount": self.move_count,
        }
