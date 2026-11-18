"""Luật Bắn tàu (Battleship).

Luật áp dụng ở đây:
  - Mỗi người một bàn 10x10 và một hạm đội 5 tàu (5, 4, 3, 3, 2 ô).
  - Pha xếp tàu: hai người xếp đồng thời, không ai phải chờ ai. Xếp xong cả hai
    thì vào pha bắn.
  - Bắn trúng thì được bắn tiếp, bắn trượt thì đổi lượt.
  - Hạ hết tàu đối phương là thắng.

ĐIỂM SỐNG CÒN: ``match_view`` không bao giờ được gửi vị trí tàu của đối thủ
xuống client. Nếu gửi thì mở DevTools ra là thấy hết tàu, game vô nghĩa. Người
xem cũng bị che như vậy, vì họ có thể mách nước qua chat.
"""

from __future__ import annotations

import random
import time

from games import GameError, SeatedRoom, other_mark

BOARD = 10
SHIP_TYPES = (
    ("carrier", "Tàu sân bay", 5),
    ("battleship", "Thiết giáp hạm", 4),
    ("cruiser", "Tàu tuần dương", 3),
    ("submarine", "Tàu ngầm", 3),
    ("destroyer", "Tàu khu trục", 2),
)
TOTAL_SHIP_CELLS = sum(size for _, _, size in SHIP_TYPES)


def in_board(row: int, col: int) -> bool:
    return 0 <= row < BOARD and 0 <= col < BOARD


def ship_cells(row: int, col: int, size: int, horizontal: bool) -> list[int]:
    """Các ô một con tàu chiếm. Ném GameError nếu tràn ra ngoài bàn."""
    cells = []
    for step in range(size):
        r = row if horizontal else row + step
        c = col + step if horizontal else col
        if not in_board(r, c):
            raise GameError("Tàu nằm tràn ra ngoài bàn.")
        cells.append(r * BOARD + c)
    return cells


def neighbourhood(cells: list[int]) -> set[int]:
    """Các ô thuộc tàu cộng viền quanh nó.

    Tàu không được dính nhau kể cả ở góc: chạm nhau thì không đoán được biên
    của từng tàu, mà luật "hạ tàu" lại dựa vào biên đó.
    """
    blocked: set[int] = set()
    for cell in cells:
        row, col = divmod(cell, BOARD)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if in_board(row + dr, col + dc):
                    blocked.add((row + dr) * BOARD + (col + dc))
    return blocked


class Fleet:
    """Hạm đội của một người: tàu đã xếp và các ô đã bị bắn."""

    def __init__(self) -> None:
        self.ships: list[dict] = []      # {key, name, size, cells[], hits set}
        self.blocked: set[int] = set()   # ô đã bị tàu khác chiếm hoặc kề tàu
        self.shots: dict[int, str] = {}  # ô -> "hit" | "miss"
        self.ready = False

    # ---- xếp tàu ----------------------------------------------------------- #
    def remaining_types(self) -> list[tuple[str, str, int]]:
        placed = {s["key"] for s in self.ships}
        return [t for t in SHIP_TYPES if t[0] not in placed]

    def place(self, key: str, row: int, col: int, horizontal: bool) -> None:
        if self.ready:
            raise GameError("Bạn đã xác nhận xếp xong rồi.")
        spec = next((t for t in SHIP_TYPES if t[0] == key), None)
        if spec is None:
            raise GameError("Loại tàu không hợp lệ.")
        if any(s["key"] == key for s in self.ships):
            raise GameError("Tàu này đã được xếp.")
        cells = ship_cells(row, col, spec[2], horizontal)
        if self.blocked & set(cells):
            raise GameError("Tàu không được chồng hoặc dính vào tàu khác.")
        self.ships.append({"key": key, "name": spec[1], "size": spec[2],
                           "cells": cells, "hits": set(), "horizontal": horizontal})
        self.blocked |= neighbourhood(cells)

    def remove(self, key: str) -> None:
        if self.ready:
            raise GameError("Bạn đã xác nhận xếp xong rồi.")
        self.ships = [s for s in self.ships if s["key"] != key]
        self.blocked = set()
        for ship in self.ships:
            self.blocked |= neighbourhood(ship["cells"])

    def clear(self) -> None:
        if self.ready:
            raise GameError("Bạn đã xác nhận xếp xong rồi.")
        self.ships.clear()
        self.blocked.clear()

    def auto_place(self) -> None:
        """Xếp ngẫu nhiên toàn bộ hạm đội. Thử lại cả ván nếu bị kẹt."""
        if self.ready:
            raise GameError("Bạn đã xác nhận xếp xong rồi.")
        for _ in range(400):
            self.ships.clear()
            self.blocked.clear()
            try:
                for key, _name, size in SHIP_TYPES:
                    for _try in range(300):
                        horizontal = random.random() < 0.5
                        row = random.randrange(BOARD - (0 if horizontal else size - 1))
                        col = random.randrange(BOARD - (size - 1 if horizontal else 0))
                        try:
                            self.place(key, row, col, horizontal)
                            break
                        except GameError:
                            continue
                    else:
                        raise GameError("bí chỗ")
                return
            except GameError:
                continue
        raise GameError("Không xếp được, thử lại lần nữa.")

    def confirm(self) -> None:
        if len(self.ships) != len(SHIP_TYPES):
            raise GameError(f"Còn {len(SHIP_TYPES) - len(self.ships)} tàu chưa xếp.")
        self.ready = True

    def unconfirm(self) -> None:
        self.ready = False

    # ---- bắn --------------------------------------------------------------- #
    def receive(self, index: int) -> dict:
        """Nhận một phát bắn. Trả về kết quả để thông báo cho hai bên."""
        if index in self.shots:
            raise GameError("Ô này đã bắn rồi.")
        for ship in self.ships:
            if index in ship["cells"]:
                ship["hits"].add(index)
                self.shots[index] = "hit"
                sunk = len(ship["hits"]) >= ship["size"]
                return {"result": "hit", "sunk": sunk,
                        "ship": ship["name"] if sunk else "",
                        "cells": ship["cells"] if sunk else []}
        self.shots[index] = "miss"
        return {"result": "miss", "sunk": False, "ship": "", "cells": []}

    def all_sunk(self) -> bool:
        return bool(self.ships) and all(len(s["hits"]) >= s["size"] for s in self.ships)

    def hit_count(self) -> int:
        return sum(len(s["hits"]) for s in self.ships)

    # ---- serialize --------------------------------------------------------- #
    def own_view(self) -> dict:
        """Bàn của chính mình: thấy hết tàu."""
        return {
            "ships": [{"key": s["key"], "name": s["name"], "size": s["size"],
                       "cells": s["cells"], "horizontal": s["horizontal"],
                       "hits": sorted(s["hits"]),
                       "sunk": len(s["hits"]) >= s["size"]} for s in self.ships],
            "shots": {str(k): v for k, v in self.shots.items()},
            "ready": self.ready,
            "remaining": [{"key": k, "name": n, "size": z}
                          for k, n, z in self.remaining_types()],
            "sunkCount": sum(1 for s in self.ships if len(s["hits"]) >= s["size"]),
        }

    def enemy_view(self, reveal: bool) -> dict:
        """Bàn đối phương: chỉ thấy các phát đã bắn.

        ``reveal`` chỉ bật khi ván đã kết thúc, lúc đó lộ tàu là vô hại và còn
        giúp xem lại ván.
        """
        view = {
            "shots": {str(k): v for k, v in self.shots.items()},
            "ready": self.ready,
            "shipCount": len(self.ships),
            "sunkShips": [{"name": s["name"], "size": s["size"], "cells": s["cells"]}
                          for s in self.ships if len(s["hits"]) >= s["size"]],
            "sunkCount": sum(1 for s in self.ships if len(s["hits"]) >= s["size"]),
            "hitsTaken": self.hit_count(),
            "totalCells": TOTAL_SHIP_CELLS,
        }
        if reveal:
            view["ships"] = [{"name": s["name"], "size": s["size"], "cells": s["cells"],
                              "hits": sorted(s["hits"]),
                              "sunk": len(s["hits"]) >= s["size"]} for s in self.ships]
        return view


class ShipRoom(SeatedRoom):
    CHANNEL = "ship"
    START_STATUS = "placing"
    DEFAULT_MODE = "classic"
    MODES = {
        "classic": {"label": "Bắn tàu 10x10 · 5 tàu"},
    }

    def __init__(self, code: str, mode: str = "") -> None:
        super().__init__(code, mode)
        self.reset_match()

    # ---- vòng đời ván ------------------------------------------------------ #
    def reset_match(self) -> None:
        self.fleets = {"X": Fleet(), "O": Fleet()}
        self.turn = self.first_turn
        self.log: list[dict] = []
        self.last_shot = -1
        self.last_result = ""

    def on_match_start(self) -> None:
        self.system("Xếp tàu đi. Hai bên xếp cùng lúc, xong thì bấm Sẵn sàng.")

    def _note(self, text: str) -> None:
        self.log.append({"text": text, "ts": time.time()})
        del self.log[:-40]

    # ---- máy chơi đơn ------------------------------------------------------ #
    def bot_pending(self, mark: str) -> bool:
        """Pha xếp tàu: hai bên xếp CÙNG LÚC, nên máy phải hành động dù không
        phải "lượt" của nó. Pha bắn thì theo lượt như bình thường."""
        if self.status == "placing":
            return not self.fleets[mark].ready
        return self.turn == mark

    def progress_token(self) -> tuple:
        return super().progress_token() + (
            len(self.log),
            self.fleets["X"].ready, self.fleets["O"].ready,
            len(self.fleets["X"].shots), len(self.fleets["O"].shots),
        )

    # ---- hành động --------------------------------------------------------- #
    def handle(self, uid: str, action: str, msg: dict) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn chỉ đang xem, không chơi được.")
        fleet = self.fleets[player.mark]

        if action in ("place", "remove", "clear", "auto", "ready", "unready"):
            if self.status != "placing":
                raise GameError("Không còn ở pha xếp tàu.")

        if action == "place":
            fleet.place(str(msg.get("ship", "")), int(msg.get("row", -1)),
                        int(msg.get("col", -1)), bool(msg.get("horizontal", True)))
        elif action == "remove":
            fleet.remove(str(msg.get("ship", "")))
        elif action == "clear":
            fleet.clear()
        elif action == "auto":
            fleet.auto_place()
        elif action == "ready":
            fleet.confirm()
            self.system(f"{player.name} đã sẵn sàng.")
            self._start_firing_if_ready()
        elif action == "unready":
            fleet.unconfirm()
        elif action == "fire":
            self.fire(uid, int(msg.get("index", -1)))
        else:
            raise GameError("Hành động không hợp lệ.")
        self.touched = time.time()

    def _start_firing_if_ready(self) -> None:
        if all(self.fleets[m].ready for m in ("X", "O")):
            self.status = "playing"
            self.turn = self.first_turn
            seat = self.seat(self.turn)
            self.system(f"Bắt đầu bắn. {seat.name if seat else self.turn} bắn trước.")

    def fire(self, uid: str, index: int) -> None:
        player = self.players[uid]
        if self.status != "playing":
            raise GameError("Chưa tới pha bắn.")
        if player.mark != self.turn:
            raise GameError("Chưa tới lượt bạn.")
        if not 0 <= index < BOARD * BOARD:
            raise GameError("Ô không hợp lệ.")

        target_mark = other_mark(player.mark)
        outcome = self.fleets[target_mark].receive(index)
        self.last_shot = index
        self.last_result = outcome["result"]
        row, col = divmod(index, BOARD)
        coord = f"{chr(ord('A') + col)}{row + 1}"

        if outcome["sunk"]:
            self._note(f"{player.name} hạ {outcome['ship']} tại {coord}!")
        elif outcome["result"] == "hit":
            self._note(f"{player.name} bắn trúng tại {coord}.")
        else:
            self._note(f"{player.name} bắn trượt tại {coord}.")

        if self.fleets[target_mark].all_sunk():
            self.system(f"{player.name} thắng, hạ sạch hạm đội đối phương!")
            self.finish(player.mark)
            return
        # Trúng thì bắn tiếp, trượt thì đổi lượt.
        if outcome["result"] == "miss":
            self.turn = target_mark

    # ---- serialize --------------------------------------------------------- #
    def _seat_label(self, mark: str) -> str:
        return "Người 1" if mark == "X" else "Người 2"

    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        mine = player.mark if player else ""
        reveal = self.status == "finished"

        if mine:
            enemy = other_mark(mine)
            own = self.fleets[mine].own_view()
            foe = self.fleets[enemy].enemy_view(reveal)
        else:
            # Khán giả: che cả hai bàn cho tới khi ván xong, tránh mách nước.
            own = self.fleets["X"].enemy_view(reveal)
            foe = self.fleets["O"].enemy_view(reveal)

        return {
            "boardSize": BOARD,
            "shipTypes": [{"key": k, "name": n, "size": z} for k, n, z in SHIP_TYPES],
            "totalShipCells": TOTAL_SHIP_CELLS,
            "turn": self.turn,
            "own": own,
            "enemy": foe,
            "readyState": {m: self.fleets[m].ready for m in ("X", "O")},
            "log": self.log[-20:],
            "lastShot": self.last_shot,
            "lastResult": self.last_result,
        }
