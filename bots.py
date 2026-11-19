"""Máy chơi đơn cho các game trong hub.

Mỗi game có một lớp bot riêng (bot_caro.py, bot_chess.py, ...) nhưng tất cả
nhìn ra ngoài qua đúng một giao diện:

    engine = make_bot(channel, level)
    for action, payload in engine.actions(room, mark):
        room.handle(BOT_UID, action, payload)

``actions()`` là hàm THUẦN TÍNH TOÁN — nó chỉ đọc room rồi trả về danh sách
hành động, không tự đổi trạng thái. Lý do: hub gọi nó trong ``asyncio.to_thread``
để nước đi nặng (cờ vua nghĩ 3 giây) không làm treo chat và game của người
khác. Nếu nó vừa tính vừa sửa room thì sẽ đua với các gói tin WebSocket đang
được xử lý ở event loop. Xem ``Hub._bot_loop`` để thấy phần kiểm tra
``progress_token`` chống đua.

Ba mức khó dùng chung ý tưởng:
    easy    — nhìn nông, cố tình chơi hớ đôi lúc, để người mới thắng được
    normal  — chơi đúng, không tự bắn vào chân mình
    hard    — nghĩ sâu nhất trong khung thời gian cho phép
"""

from __future__ import annotations

import os
import random
import time

from games import BOT_UID, GameError

try:
    _BUDGET_SCALE = max(0.1, min(2.0, float(os.environ.get("BOT_BUDGET_SCALE", "1.0"))))
except ValueError:
    _BUDGET_SCALE = 1.0

LEVELS = ("easy", "normal", "hard")
DEFAULT_LEVEL = "normal"

LEVEL_LABEL = {
    "easy": "Dễ",
    "normal": "Thường",
    "hard": "Khó",
}

LEVEL_DESC = {
    "easy": "Đi nông, thỉnh thoảng đi hớ — dành cho người mới",
    "normal": "Chơi chắc tay, không tự bắn vào chân mình",
    "hard": "Nghĩ sâu nhất, đừng mong thắng dễ",
}


class BotError(Exception):
    """Máy không tính được nước đi. Hub ghi log rồi bỏ qua lượt này."""


# --------------------------------------------------------------------------- #
# khung chung
# --------------------------------------------------------------------------- #
class Bot:
    """Lớp cha của mọi máy. Lớp con chỉ cần cài ``actions``."""

    CHANNEL = ""

    #: Thời gian "giả vờ suy nghĩ" theo mức khó, để nước đi không hiện tức thì.
    #: Máy trả lời trong 5ms làm người chơi có cảm giác đang đánh với script,
    #: và ở Bắn tàu thì không kịp nhìn thấy phát bắn của mình vào đâu.
    THINK_DELAY = {"easy": 0.45, "normal": 0.7, "hard": 0.9}

    #: Ngân sách thời gian cho phần tìm kiếm, theo mức khó (giây).
    TIME_BUDGET = {"easy": 0.2, "normal": 0.9, "hard": 2.5}

    def __init__(self, level: str = DEFAULT_LEVEL) -> None:
        self.level = level if level in LEVELS else DEFAULT_LEVEL
        # Seed theo thời gian để hai ván liên tiếp không giống nhau y hệt.
        self.rng = random.Random()

    @property
    def think_delay(self) -> float:
        return self.THINK_DELAY.get(self.level, 0.7)

    @property
    def budget(self) -> float:
        return self.TIME_BUDGET.get(self.level, 0.9) * _BUDGET_SCALE

    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        """Trả về [(tên hành động, payload)] để hub đưa vào ``room.handle``."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# tìm kiếm alpha-beta dùng chung cho cờ vua và cờ tướng
# --------------------------------------------------------------------------- #
INF = 10 ** 9
MATE = 10 ** 6


class Timeout(Exception):
    """Hết ngân sách thời gian giữa lúc tìm kiếm."""


class Position:
    """Giao diện tối thiểu mà ``search_best`` cần.

    Cố ý tách khỏi luật game: cờ vua và cờ tướng khác nhau hoàn toàn về cách
    biểu diễn nước đi, nhưng phần alpha-beta + đào sâu dần + quiescence thì y
    hệt nhau. Viết một lần ở đây để hai bot không lệch nhau về chất lượng.
    """

    def moves(self) -> list:
        """Mọi nước hợp lệ của bên tới lượt."""
        raise NotImplementedError

    def play(self, move) -> "Position":
        """Trả về Position MỚI sau nước đi. Không được sửa chính mình."""
        raise NotImplementedError

    def score(self) -> int:
        """Điểm thế cờ theo góc nhìn của bên ĐANG TỚI LƯỢT (negamax)."""
        raise NotImplementedError

    def is_capture(self, move) -> bool:
        """Nước này có ăn quân không — dùng cho quiescence."""
        return False

    def quiescence_moves(self) -> list:
        """Nước ăn quân dùng cho quiescence search. Lớp con có thể ghi đè
        để sinh nhanh nước ăn quân mà không cần sinh toàn bộ nước đi tĩnh."""
        return [m for m in self.moves() if self.is_capture(m)]

    def hash_key(self) -> int:
        """Khóa băm 64-bit (Zobrist) cho Transposition Table."""
        return id(self)

    def order(self, move) -> int:
        """Điểm sắp xếp; cao đi trước. Sắp tốt thì alpha-beta cắt sớm hơn nhiều."""
        return 0

    def in_check(self) -> bool:
        """Bên tới lượt có đang bị chiếu không (để phân biệt hết nước / chiếu hết)."""
        return False

    def loss_on_no_move(self) -> bool:
        """Hết nước đi thì bên tới lượt THUA (cờ tướng) hay HOÀ (cờ vua)?"""
        return True


QUIESCENCE_MAX = 4

# Cờ phân loại cho Transposition Table
TT_EXACT = 0
TT_LOWERBOUND = 1  # >= beta (cut-off)
TT_UPPERBOUND = 2  # <= alpha (all-node)


def _quiesce(pos: Position, alpha: int, beta: int, deadline: float, depth: int,
             stats: list[int] | None = None) -> int:
    """Chỉ đào tiếp các nước ăn quân.

    Không có phần này thì máy hay "ăn non": nó thấy mình ăn được con xe ở nước
    cuối tầm nhìn rồi dừng lại, không thấy nước sau đối phương ăn lại.
    """
    if stats is not None:
        stats[0] += 1
        if (stats[0] & 0xFF) == 0:
            time.sleep(0)  # nhả Python GIL định kỳ để event loop phục vụ WebSocket mượt mà
    if time.monotonic() > deadline:
        raise Timeout
    stand = pos.score()
    if depth >= QUIESCENCE_MAX:
        return stand
    if stand >= beta:
        return stand

    # Delta pruning: nếu ngay cả khi ăn được một quân to (950cp) mà vẫn không vượt nổi
    # alpha thì nhánh này vô vọng, không cần đào tiếp (trừ khi đang bị chiếu).
    if stand < alpha - 950 and not pos.in_check():
        return stand

    alpha = max(alpha, stand)

    captures = pos.quiescence_moves()
    captures.sort(key=pos.order, reverse=True)
    for move in captures:
        value = -_quiesce(pos.play(move), -beta, -alpha, deadline, depth + 1, stats)
        if value >= beta:
            return value
        alpha = max(alpha, value)
    return alpha


def _negamax(pos: Position, depth: int, alpha: int, beta: int, deadline: float,
             ply: int, tt: dict[int, tuple[int, int, int, object]],
             killers: dict[int, list], history: dict[object, int],
             stats: list[int] | None = None) -> int:
    if stats is not None:
        stats[0] += 1
        if (stats[0] & 0xFF) == 0:
            time.sleep(0)  # nhả Python GIL định kỳ để tránh giật gói tin phòng khác trên CPU đơn nhân
    if time.monotonic() > deadline:
        raise Timeout

    h = pos.hash_key()
    tt_entry = tt.get(h)
    tt_move = None
    if tt_entry is not None:
        e_depth, e_flag, e_score, e_move = tt_entry
        tt_move = e_move
        if e_depth >= depth:
            if e_flag == TT_EXACT:
                return e_score
            if e_flag == TT_LOWERBOUND and e_score >= beta:
                return e_score
            if e_flag == TT_UPPERBOUND and e_score <= alpha:
                return e_score

    moves = pos.moves()
    if not moves:
        if pos.in_check() or pos.loss_on_no_move():
            # Trừ depth để máy chọn đường chiếu hết NGẮN nhất, và khi bị hết
            # thì chọn đường cầm cự lâu nhất.
            return -MATE - depth
        return 0

    if depth <= 0:
        return _quiesce(pos, alpha, beta, deadline, 0, stats)

    # Move ordering kết hợp: TT Best Move > Captures (MVV-LVA) > Killer Moves > History > Positional Order
    def move_priority(m):
        if tt_move is not None and m == tt_move:
            return 2_000_000
        if pos.is_capture(m):
            return 1_000_000 + pos.order(m)
        k = killers.get(ply)
        if k:
            if m == k[0]:
                return 800_000
            if len(k) > 1 and m == k[1]:
                return 700_000
        m_key = (m[0], m[1]) if isinstance(m, tuple) and len(m) >= 2 else m
        return history.get(m_key, 0) + pos.order(m)

    moves.sort(key=move_priority, reverse=True)
    best_val = -INF
    best_move = moves[0]
    orig_alpha = alpha
    in_chk = pos.in_check()

    for idx, move in enumerate(moves):
        is_cap = pos.is_capture(move)
        child = pos.play(move)

        # Late Move Reduction (LMR): Ở các nước tĩnh phía sau, duyệt thử ở độ sâu giảm 1-2 tầng
        if depth >= 3 and idx >= 4 and not is_cap and not in_chk:
            reduced = max(1, depth - 2)
            val = -_negamax(child, reduced, -alpha - 1, -alpha, deadline,
                            ply + 1, tt, killers, history, stats)
            if val > alpha:
                # Re-search full depth
                val = -_negamax(child, depth - 1, -beta, -alpha, deadline,
                                ply + 1, tt, killers, history, stats)
        else:
            val = -_negamax(child, depth - 1, -beta, -alpha, deadline,
                            ply + 1, tt, killers, history, stats)

        if val > best_val:
            best_val = val
            best_move = move
        if val > alpha:
            alpha = val
        if alpha >= beta:
            # Beta cut-off: lưu killer moves và history cho nước tĩnh
            if not is_cap:
                k = killers.setdefault(ply, [None, None])
                if k[0] != move:
                    k[1] = k[0]
                    k[0] = move
                m_key = (move[0], move[1]) if isinstance(move, tuple) and len(move) >= 2 else move
                history[m_key] = history.get(m_key, 0) + depth * depth
            break

    # Lưu kết quả vào Transposition Table (giới hạn tối đa 65.536 mục để bảo vệ RAM 512MB)
    if len(tt) < 65536:
        flag = TT_EXACT if (orig_alpha < best_val < beta) else (TT_LOWERBOUND if best_val >= beta else TT_UPPERBOUND)
        tt[h] = (depth, flag, best_val, best_move)

    return best_val


def search_best(pos: Position, max_depth: int, budget: float,
                rng: random.Random | None = None,
                blunder: float = 0.0, jitter: int = 0):
    """Đào sâu dần trong ngân sách thời gian kết hợp Transposition Table,
    Killer Moves, History Heuristic và LMR. Trả về (nước đi, điểm, độ sâu).
    """
    rng = rng or random.Random()
    moves = pos.moves()
    if not moves:
        return None, 0, 0
    if len(moves) == 1:
        return moves[0], 0, 1

    deadline = time.monotonic() + budget
    ordered = sorted(moves, key=pos.order, reverse=True)
    best_move = ordered[0]
    best_score = -INF
    reached = 0
    scored: list[tuple[int, object]] = []

    tt: dict[int, tuple[int, int, int, object]] = {}
    killers: dict[int, list] = {}
    history: dict[object, int] = {}
    stats = [0]

    for depth in range(1, max_depth + 1):
        alpha, local_best, local_scores = -INF, None, []
        try:
            for move in ordered:
                value = -_negamax(pos.play(move), depth - 1, -INF, -alpha, deadline,
                                  1, tt, killers, history, stats)
                if jitter:
                    value += rng.randint(-jitter, jitter)
                local_scores.append((value, move))
                if value > alpha or local_best is None:
                    alpha, local_best = value, move
        except Timeout:
            break
        best_move, best_score, reached = local_best, alpha, depth
        scored = local_scores
        # Sắp lại theo điểm vừa có, để vòng sâu hơn cắt nhánh sớm hơn
        ordered = [m for _v, m in sorted(local_scores, key=lambda p: -p[0])]
        if best_score > MATE // 2:
            break

    if blunder and scored and rng.random() < blunder:
        scored.sort(key=lambda p: -p[0])
        pool = scored[:max(2, len(scored) // 3)]
        best_move = rng.choice(pool)[1]

    return best_move, best_score, reached


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def _registry() -> dict[str, type[Bot]]:
    """Import muộn để bots.py không phải import vòng với các module luật."""
    from bot_bluff import BluffBot
    from bot_caro import CaroBot
    from bot_chess import ChessBot
    from bot_flags import FlagsBot
    from bot_geo import GeoBot
    from bot_ludo import LudoBot
    from bot_poker import PokerBot
    from bot_ship import ShipBot
    from bot_xiangqi import XiangqiBot
    from bot_zombie import ZombieBot

    return {
        CaroBot.CHANNEL: CaroBot,
        ChessBot.CHANNEL: ChessBot,
        XiangqiBot.CHANNEL: XiangqiBot,
        ShipBot.CHANNEL: ShipBot,
        BluffBot.CHANNEL: BluffBot,
        PokerBot.CHANNEL: PokerBot,
        FlagsBot.CHANNEL: FlagsBot,
        GeoBot.CHANNEL: GeoBot,
        LudoBot.CHANNEL: LudoBot,
        ZombieBot.CHANNEL: ZombieBot,
    }


_CACHE: dict[str, type[Bot]] | None = None


def bot_channels() -> list[str]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _registry()
    return sorted(_CACHE)


def supports(channel: str) -> bool:
    return channel in bot_channels()


def make_bot(channel: str, level: str = DEFAULT_LEVEL) -> Bot:
    global _CACHE
    if _CACHE is None:
        _CACHE = _registry()
    cls = _CACHE.get(channel)
    if cls is None:
        raise BotError(f"Game '{channel}' chưa có máy để chơi đơn.")
    return cls(level)


def levels_info() -> list[dict]:
    return [{"id": level, "label": LEVEL_LABEL[level], "desc": LEVEL_DESC[level]}
            for level in LEVELS]


__all__ = [
    "BOT_UID", "Bot", "BotError", "DEFAULT_LEVEL", "GameError", "LEVELS",
    "Position", "bot_channels", "levels_info", "make_bot", "search_best",
    "supports",
]
