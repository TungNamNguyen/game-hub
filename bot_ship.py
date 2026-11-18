"""Máy chơi Bắn tàu.

KHÔNG GIỮ BỘ NHỚ RIÊNG. Mọi thứ máy "biết" đều suy ra lại từ trạng thái phòng
mỗi lượt: ``fleet.shots`` (ô nào đã bắn, trúng hay trượt) và danh sách tàu đã
chìm. Làm vậy vì hub tạo engine mới cho từng lượt (xem Hub._bot_loop), và vì
server có thể restart giữa ván — máy nào dựa vào biến nội bộ sẽ quên sạch và
bắn lại các ô cũ.

Chiến thuật ba tầng, giống cách người chơi giỏi làm:

  1. TRUY (target): còn vết trúng chưa thuộc tàu nào đã chìm thì đuổi theo nó.
     Hai vết trúng thẳng hàng thì nối dài đường đó ra hai đầu — tàu nằm dọc
     theo đường đó.
  2. DÒ (hunt) theo lưới nhảy: tàu ngắn nhất dài 2 ô, nên chỉ cần bắn các ô có
     ``(hàng + cột) % 2 == 0`` là không con tàu nào lọt lưới. Cách này giảm
     một nửa số phát dò.
  3. LOẠI Ô CHẾT: luật của phòng cấm tàu dính nhau kể cả ở góc (xem
     battleship.neighbourhood), nên mọi ô kề tàu đã chìm chắc chắn là nước.
     Bắn vào đó là phí lượt. Mức Khó dùng suy luận này, mức thấp thì không.
"""

from __future__ import annotations

from battleship import BOARD, SHIP_TYPES, neighbourhood
from bots import Bot, BotError
from games import other_mark


def _neighbours(index: int) -> list[int]:
    """4 ô kề theo hàng/cột (không tính chéo — tàu không đi chéo)."""
    row, col = divmod(index, BOARD)
    out = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = row + dr, col + dc
        if 0 <= r < BOARD and 0 <= c < BOARD:
            out.append(r * BOARD + c)
    return out


def _line_ends(hits: list[int]) -> list[int]:
    """Với các vết trúng thẳng hàng, trả về ô nối dài ở hai đầu."""
    rows = {h // BOARD for h in hits}
    cols = {h % BOARD for h in hits}
    out = []
    if len(rows) == 1:                       # nằm ngang
        row = rows.pop()
        lo, hi = min(cols), max(cols)
        if lo - 1 >= 0:
            out.append(row * BOARD + lo - 1)
        if hi + 1 < BOARD:
            out.append(row * BOARD + hi + 1)
    elif len(cols) == 1:                     # nằm dọc
        col = cols.pop()
        lo, hi = min(rows), max(rows)
        if lo - 1 >= 0:
            out.append((lo - 1) * BOARD + col)
        if hi + 1 < BOARD:
            out.append((hi + 1) * BOARD + col)
    return out


def _groups(hits: set[int]) -> list[list[int]]:
    """Gom các vết trúng liền nhau thành từng cụm (mỗi cụm là một con tàu)."""
    remaining = set(hits)
    out = []
    while remaining:
        seed = remaining.pop()
        cluster = [seed]
        queue = [seed]
        while queue:
            current = queue.pop()
            for nb in _neighbours(current):
                if nb in remaining:
                    remaining.discard(nb)
                    cluster.append(nb)
                    queue.append(nb)
        out.append(cluster)
    return out


class ShipBot(Bot):
    CHANNEL = "ship"

    # Mức Dễ bắn bừa hoàn toàn; mức Thường dùng lưới nhảy + truy theo vết;
    # mức Khó thêm suy luận loại ô kề tàu đã chìm.
    USE_PARITY = {"easy": False, "normal": True, "hard": True}
    USE_DEDUCTION = {"easy": False, "normal": False, "hard": True}
    # Mức Dễ đôi khi bỏ lỡ việc truy theo vết trúng, cho người chơi cơ hội.
    LAZY_CHASE = {"easy": 0.35, "normal": 0.0, "hard": 0.0}

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        if room.status == "placing":
            return self._place(room, mark)
        if room.status == "playing":
            return [("fire", {"index": self._target(room, mark)})]
        raise BotError("Chưa tới lúc máy hành động.")

    # ---- pha xếp tàu ------------------------------------------------------- #
    def _place(self, room, mark: str) -> list[tuple[str, dict]]:
        """Nhờ luôn auto_place của phòng: nó đã cài đúng luật không dính nhau,
        và xếp ngẫu nhiên là chiến thuật hợp lý — không có thế xếp nào "mạnh"
        khi đối thủ không biết gì về bàn của mình."""
        fleet = room.fleets[mark]
        steps: list[tuple[str, dict]] = []
        if len(fleet.ships) != len(SHIP_TYPES):
            steps.append(("clear", {}))
            steps.append(("auto", {}))
        steps.append(("ready", {}))
        return steps

    # ---- pha bắn ----------------------------------------------------------- #
    def _target(self, room, mark: str) -> int:
        """Chọn ô để bắn trên bàn đối thủ."""
        foe_fleet = room.fleets[other_mark(mark)]
        shots = foe_fleet.shots                      # ô -> "hit" | "miss"

        # Ô kề tàu đã chìm chắc chắn là nước: tàu không được dính nhau.
        sunk_cells: set[int] = set()
        for ship in foe_fleet.ships:
            if len(ship["hits"]) >= ship["size"]:
                sunk_cells |= set(ship["cells"])
        dead: set[int] = set()
        if self.USE_DEDUCTION.get(self.level) and sunk_cells:
            dead = neighbourhood(sorted(sunk_cells)) - sunk_cells

        open_cells = [i for i in range(BOARD * BOARD) if i not in shots]
        if not open_cells:
            raise BotError("Không còn ô nào để bắn.")

        usable = [i for i in open_cells if i not in dead] or open_cells

        # --- tầng 1: truy theo vết trúng chưa chìm -------------------------- #
        live_hits = {i for i, kind in shots.items() if kind == "hit"} - sunk_cells
        lazy = self.LAZY_CHASE.get(self.level, 0.0)
        if live_hits and not (lazy and self.rng.random() < lazy):
            chase = self._chase(live_hits, shots, usable)
            if chase is not None:
                return chase

        # --- tầng 2: dò theo lưới nhảy -------------------------------------- #
        if self.USE_PARITY.get(self.level):
            parity = [i for i in usable if ((i // BOARD) + (i % BOARD)) % 2 == 0]
            if parity:
                return self.rng.choice(parity)
        return self.rng.choice(usable)

    def _chase(self, live_hits: set[int], shots: dict, usable: list[int]) -> int | None:
        allowed = set(usable)
        clusters = _groups(live_hits)
        # Ưu tiên cụm dài nhất: đã biết hướng tàu nên tỉ lệ trúng tiếp cao nhất.
        clusters.sort(key=len, reverse=True)

        for cluster in clusters:
            if len(cluster) >= 2:
                ends = [i for i in _line_ends(cluster) if i in allowed]
                if ends:
                    return self.rng.choice(ends)
            else:
                spots = [i for i in _neighbours(cluster[0]) if i in allowed]
                if spots:
                    return self.rng.choice(spots)

        # Các đầu đường đều đã bắn rồi (tàu nằm sát mép hoặc sát tàu khác) —
        # nới điều kiện: cho phép cả ô nằm trong vùng "chắc là nước".
        for cluster in clusters:
            spots = [i for i in _neighbours(cluster[0]) if i not in shots]
            if len(cluster) >= 2:
                spots = [i for i in _line_ends(cluster) if i not in shots]
            if spots:
                return self.rng.choice(spots)
        return None
