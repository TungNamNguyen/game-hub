"""Máy chơi cờ caro / XO.

Hai chế độ tuỳ cỡ bàn, vì hai bài toán khác nhau hẳn:

  * Bàn tí hon (XO 3x3): vét cạn bằng minimax. Chỉ 9 ô nên máy chơi HOÀN HẢO —
    mức Khó không bao giờ thua, giỏi nhất cũng chỉ hoà được.
  * Bàn lớn (tới 50x50 = 2.500 ô): không thể vét. Máy chấm điểm từng ô ứng
    viên theo "cửa sổ thắng", và ở mức Khó nhìn thêm một nước trả lời của đối
    thủ.

Cách chấm điểm dùng cửa sổ chứ không đếm quân liền nhau, vì đếm liền nhau bỏ
sót các thế rời như ``X X _ X X`` — thế đó thắng ngay nước sau mà cách đếm liền
nhau lại cho điểm thấp. Cửa sổ là mọi đoạn ``win_len`` ô liên tiếp đi qua ô
đang xét: đoạn nào không có quân đối thủ thì còn khả năng thành đường thắng, và
càng nhiều quân mình trong đoạn thì càng giá trị.
"""

from __future__ import annotations

from bots import Bot, BotError
from caro import DIRECTIONS, winning_line
from games import other_mark

# Điểm theo số quân mình đã có trong một cửa sổ sạch (không có quân đối thủ).
# Nhảy bậc rất mạnh để "còn thiếu 1 quân" luôn thắng "còn thiếu 2 quân" dù
# thế sau có nhiều cửa sổ hơn.
WINDOW_SCORE = (0, 1, 12, 150, 2_000, 30_000)
WIN_SCORE = 10 ** 7

# Bán kính quanh các quân đã có để lấy ô ứng viên. 2 là đủ: nước đáng đi luôn
# nằm sát cụm quân, còn lấy rộng hơn thì bàn 50x50 phình ra vài nghìn ứng viên.
NEIGHBOUR_RADIUS = 2

# Số ứng viên đưa vào phần nhìn trước ở mức Khó. Giữ nhỏ vì mỗi ứng viên lại
# phải chấm điểm toàn bộ ứng viên của đối thủ.
LOOKAHEAD_WIDTH = {"easy": 0, "normal": 0, "hard": 10}


def _windows(index: int, size: int, win_len: int):
    """Sinh các cửa sổ ``win_len`` ô liên tiếp đi qua ``index``, theo 4 hướng."""
    row, col = divmod(index, size)
    for dr, dc in DIRECTIONS:
        # offset = ô đang xét nằm ở vị trí thứ mấy trong cửa sổ.
        for offset in range(win_len):
            start_r, start_c = row - dr * offset, col - dc * offset
            end_r, end_c = start_r + dr * (win_len - 1), start_c + dc * (win_len - 1)
            if not (0 <= start_r < size and 0 <= start_c < size):
                continue
            if not (0 <= end_r < size and 0 <= end_c < size):
                continue
            yield [(start_r + dr * k) * size + (start_c + dc * k) for k in range(win_len)]


def cell_score(board: list[str], size: int, win_len: int,
               index: int, mark: str) -> int:
    """Giá trị của việc ``mark`` đặt quân vào ``index``."""
    foe = other_mark(mark)
    total = 0
    for window in _windows(index, size, win_len):
        mine = 0
        for cell in window:
            piece = board[cell]
            if piece == foe:
                break                       # cửa sổ đã chết
            if piece == mark:
                mine += 1
        else:
            # +1 vì tính cả quân sắp đặt vào index (index đang trống).
            filled = mine + 1
            if filled >= win_len:
                return WIN_SCORE
            total += WINDOW_SCORE[min(filled, len(WINDOW_SCORE) - 1)]
    return total


def candidates(board: list[str], size: int) -> list[int]:
    """Ô trống gần quân đã có. Bàn trống thì trả về ô giữa."""
    occupied = [i for i, piece in enumerate(board) if piece]
    if not occupied:
        centre = (size // 2) * size + size // 2
        return [centre]

    picked: set[int] = set()
    for index in occupied:
        row, col = divmod(index, size)
        for dr in range(-NEIGHBOUR_RADIUS, NEIGHBOUR_RADIUS + 1):
            for dc in range(-NEIGHBOUR_RADIUS, NEIGHBOUR_RADIUS + 1):
                r, c = row + dr, col + dc
                if 0 <= r < size and 0 <= c < size and not board[r * size + c]:
                    picked.add(r * size + c)
    return sorted(picked)


def _immediate(board: list[str], size: int, win_len: int,
               cells: list[int], mark: str) -> int | None:
    """Ô đặt vào là thắng ngay, hoặc None."""
    for index in cells:
        board[index] = mark
        line = winning_line(board, size, win_len, index)
        board[index] = ""
        if line:
            return index
    return None


def _win_spots(board: list[str], size: int, win_len: int,
               cells: list[int], mark: str) -> list[int]:
    """MỌI ô mà ``mark`` đặt vào là thắng ngay."""
    out = []
    for index in cells:
        board[index] = mark
        if winning_line(board, size, win_len, index):
            out.append(index)
        board[index] = ""
    return out


def four_threats(board: list[str], size: int, win_len: int,
                 cells: list[int], mark: str) -> list[int]:
    """Ô mà ``mark`` đặt vào sẽ tạo ra thế "bốn quân" — tức nước sau họ có nước
    thắng, nên đối phương buộc phải trả lời.

    Đây là bậc thang bị thiếu thì máy chơi rất tệ: nếu chỉ biết chặn khi đối thủ
    ĐÃ có bốn quân thì đã muộn. Bốn quân hở hai đầu có tới hai ô thắng, chặn một
    đầu vẫn thua. Phải chặn từ lúc họ mới có ba quân.
    """
    out = []
    for index in cells:
        board[index] = mark
        # Chỉ cần xét các ô quanh ô vừa đặt: thế bốn quân mới sinh ra bắt buộc
        # phải đi qua nó.
        nearby = _around(board, size, index)
        if _immediate(board, size, win_len, nearby, mark) is not None:
            out.append(index)
        board[index] = ""
    return out


def _around(board: list[str], size: int, index: int) -> list[int]:
    """Ô trống trong bán kính NEIGHBOUR_RADIUS quanh ``index``."""
    row, col = divmod(index, size)
    out = []
    for dr in range(-NEIGHBOUR_RADIUS, NEIGHBOUR_RADIUS + 1):
        for dc in range(-NEIGHBOUR_RADIUS, NEIGHBOUR_RADIUS + 1):
            r, c = row + dr, col + dc
            if 0 <= r < size and 0 <= c < size and not board[r * size + c]:
                out.append(r * size + c)
    return out


# --------------------------------------------------------------------------- #
# XO 3x3: vét cạn
# --------------------------------------------------------------------------- #
def _solve_small(board: list[str], size: int, win_len: int, mark: str) -> int:
    """Minimax vét cạn, trả về ô tốt nhất. Dùng cho bàn rất nhỏ (XO)."""
    def search(turn: str, depth: int, alpha: int, beta: int, last: int) -> int:
        if last >= 0 and winning_line(board, size, win_len, last):
            # Người vừa đi (đối phương của `turn`) đã thắng.
            return -100 + depth
        empties = [i for i, piece in enumerate(board) if not piece]
        if not empties:
            return 0
        best = -1000
        for index in empties:
            board[index] = turn
            value = -search(other_mark(turn), depth + 1, -beta, -alpha, index)
            board[index] = ""
            if value > best:
                best = value
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best

    best_index, best_value = -1, -10_000
    for index in [i for i, piece in enumerate(board) if not piece]:
        board[index] = mark
        value = -search(other_mark(mark), 1, -1000, 1000, index)
        board[index] = ""
        if value > best_value:
            best_index, best_value = index, value
    return best_index


# --------------------------------------------------------------------------- #
# bot
# --------------------------------------------------------------------------- #
class CaroBot(Bot):
    CHANNEL = "caro"

    # Bàn nhỏ hơn mức này thì vét cạn được, khỏi cần chấm điểm gần đúng.
    EXHAUSTIVE_CELLS = 16

    # Mức Dễ: xác suất đi lỏng tay thay vì đi nước tốt nhất.
    SLOPPY = {"easy": 0.45, "normal": 0.0, "hard": 0.0}

    # Mức Dễ còn phải BỎ CHẶN đôi lúc, nếu không thì không thắng được nó.
    # Một máy chỉ cần "thắng khi thắng được, chặn khi phải chặn" đã đủ để hoà
    # mọi ván XO 3x3 — đo thực tế: 0/12 ván thua. Người mới chơi mà không bao
    # giờ thắng nổi mức Dễ thì mức Dễ đó vô nghĩa.
    MISS_BLOCK = {"easy": 0.4, "normal": 0.0, "hard": 0.0}

    # Nhận biết thế "bốn quân" (bậc 3-4 của bậc thang đe doạ). Mức Dễ không có,
    # để nó vẫn bị đánh bại bằng thế ba quân mở.
    THREAT_AWARE = {"easy": False, "normal": True, "hard": True}
    THREAT_WIDTH = 24

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        board = list(room.board)
        size, win_len = room.size, room.win_len
        cells = candidates(board, size)
        if not cells:
            raise BotError("Bàn đã đầy, không còn ô nào để đi.")

        if len(board) <= self.EXHAUSTIVE_CELLS and self.level != "easy":
            index = _solve_small(board, size, win_len, mark)
            if index >= 0:
                return [("move", {"index": index})]

        index = self._pick(board, size, win_len, cells, mark)
        return [("move", {"index": index})]

    def _pick(self, board, size, win_len, cells, mark):
        foe = other_mark(mark)

        # Bậc thang mối đe doạ, xét theo đúng thứ tự mức độ khẩn cấp. Đây là
        # cách chơi caro tiêu chuẩn; thiếu một bậc là máy hớ hẳn một loại thế.

        # 1. Thắng được ngay thì thắng. KHÔNG mức nào bỏ qua bước này — máy bỏ
        # lỡ nước thắng bày sẵn thì trông như bị lỗi, không phải như đang dễ.
        win_now = _immediate(board, size, win_len, cells, mark)
        if win_now is not None:
            return win_now

        # 2. Đối thủ sắp thắng thì chặn. Mức Dễ đôi lúc "không thấy".
        miss = self.MISS_BLOCK.get(self.level, 0.0)
        blocking = self.rng.random() >= miss
        spots = _win_spots(board, size, win_len, cells, foe)
        if spots and blocking:
            # Nhiều ô thắng thì coi như đã thua; vẫn chặn ô tốt nhất cho mình để
            # còn cơ hội nếu đối thủ đi sai.
            return max(spots, key=lambda i: cell_score(board, size, win_len, i, mark))

        scored = []
        for index in cells:
            mine = cell_score(board, size, win_len, index, mark)
            theirs = cell_score(board, size, win_len, index, foe)
            # Hệ số 0.9 cho phần phòng: hơi thiên về tấn công, vì trong caro
            # người chủ động tạo thế đôi thường thắng.
            scored.append((mine + theirs * 0.9, index))
        scored.sort(reverse=True)

        sloppy = self.SLOPPY.get(self.level, 0.0)
        if sloppy and self.rng.random() < sloppy:
            pool = scored[:max(2, len(scored) // 3)]
            return self.rng.choice(pool)[1]

        if self.THREAT_AWARE.get(self.level) and len(board) > self.EXHAUSTIVE_CELLS:
            # Chỉ soi các ô đáng soi: quét đe doạ là O(ứng viên²) nên bàn 50x50
            # mà quét hết thì chậm hẳn, còn nước tạo đe doạ thật thì gần như
            # luôn nằm trong nhóm điểm cao.
            head = [index for _value, index in scored[:self.THREAT_WIDTH]]

            # 3. Ta tạo được bốn quân -> đi luôn. Đó là nước bắt buộc đối thủ
            #    phải trả lời, nên ta giữ thế chủ động.
            mine_four = four_threats(board, size, win_len, head, mark)
            if mine_four:
                return max(mine_four,
                           key=lambda i: cell_score(board, size, win_len, i, mark))

            # 4. Đối thủ tạo được bốn quân -> chiếm đúng ô họ cần nhất.
            #    Xếp theo giá trị của ô ĐỐI VỚI HỌ, không theo giá trị với ta:
            #    thế ba quân mở _XXX_ có nhiều ô "tạo được bốn", nhưng chỉ hai
            #    ô sát hai đầu mới thật sự phá được thế. Ô họ cần nhất chính là
            #    ô có điểm cao nhất khi tính cho họ.
            if blocking:
                foe_four = four_threats(board, size, win_len, head, foe)
                if foe_four:
                    return max(foe_four, key=lambda i: (
                        cell_score(board, size, win_len, i, foe),
                        cell_score(board, size, win_len, i, mark)))

        width = LOOKAHEAD_WIDTH.get(self.level, 0)
        if width <= 1 or len(scored) <= 1:
            return scored[0][1]
        return self._lookahead(board, size, win_len, scored[:width], mark, foe)

    def _lookahead(self, board, size, win_len, shortlist, mark, foe):
        """Nhìn trước một nước: trừ đi phần đối thủ hưởng lợi sau nước của ta.

        Bắt được lỗi hay gặp của máy chỉ chấm điểm tĩnh: đi một nước trông đẹp
        nhưng tặng đối thủ thế bốn quân mở.
        """
        best_index, best_value = shortlist[0][1], None
        for gain, index in shortlist:
            board[index] = mark

            # Nước này thành đường thắng thì chọn luôn (đã lọc ở bước 1, nhưng
            # giữ lại cho chắc nếu bước 1 bị bỏ qua).
            if winning_line(board, size, win_len, index):
                board[index] = ""
                return index

            foe_cells = candidates(board, size)
            foe_best = 0
            if _immediate(board, size, win_len, foe_cells, foe) is not None:
                foe_best = WIN_SCORE
            else:
                for foe_index in foe_cells:
                    value = cell_score(board, size, win_len, foe_index, foe)
                    if value > foe_best:
                        foe_best = value
            board[index] = ""

            value = gain - foe_best * 1.1
            if best_value is None or value > best_value:
                best_index, best_value = index, value
        return best_index
