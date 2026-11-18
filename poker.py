"""Luật "Xì Tố" — No-Limit Texas Hold'em 2-6 người, chip ảo, không có máy.

CHIP. Lần đầu ngồi vào một bàn được cấp ``CHIP_START`` chip ảo. Hết chip thì
ngồi xem, bấm "Mua lại" để được cấp lại ``CHIP_START`` cho ván sau. Rời ghế rồi
ngồi lại CÙNG phòng thì giữ nguyên số chip cũ (``self.bank``) — không có cách
"đứng dậy để reset chip".

LUẬT (No-Limit Hold'em chuẩn, theo quy ước của các site poker online):
  - Mỗi ván: nút chia (D) dịch một ghế theo chiều kim đồng hồ, hai ghế sau nút
    đặt mù nhỏ / mù lớn. Tay đôi: nút là mù nhỏ, đi trước preflop, đi sau từ
    flop trở đi.
  - 4 vòng cược: preflop, flop (3 lá), turn (1 lá), river (1 lá).
  - Cược tối thiểu = mù lớn. Tố tối thiểu = mức tố gần nhất trong vòng đó
    (mù lớn nếu chưa ai tố). Ví dụ mù 500/1.000, ai đó tố lên 3.000 (thêm
    2.000) thì tố lại tối thiểu phải lên 5.000.
  - All-in THIẾU (không đủ một lần tố đầy đủ) KHÔNG mở lại quyền tố cho người
    đã hành động — họ chỉ được theo hoặc bỏ (``SeatState.can_raise``).
  - Cược thừa không ai theo được trả lại trước khi chia pot.
  - Side pot: người all-in chỉ tranh phần pot tương ứng với số đã góp.
  - Hòa thì chia đều, chip lẻ cho người gần bên trái nút nhất.
  - Mọi người còn lại đều all-in thì lật bài ngửa và chạy nốt bàn chung.
  - CHIA 2 LẦN (run it twice): lúc tất tay mà bàn chung chưa đủ 5 lá, mọi
    người còn trong ván được hỏi có muốn chia 2 lần không. TẤT CẢ đồng ý thì
    chạy phần bàn còn thiếu hai lần bằng các lá còn lại trong bộ; mỗi pot tách
    đôi, nửa đầu xử theo bàn 1, nửa sau theo bàn 2.
  - Hết ván, ai đã được chia bài (kể cả bỏ bài hay thua) đều bấm "Khoe bài"
    được.

GHẾ & HÀNG CHỜ.
  - Vào phòng khi còn ghế trống: ngồi ngay. Nếu ván đang chạy thì giữ ghế đó
    nhưng CHỜ VÁN SAU mới được chia bài.
  - Bàn kín: bấm "Xếp hàng" trên một ghế. Khi người ngồi ghế đó rời đi (sau khi
    ván hiện tại kết thúc) thì người đầu hàng tự động vào ghế.
  - Đứng dậy / mất kết nối giữa ván: bài bị bỏ (trừ khi đã all-in), ghế được
    giữ tới hết ván rồi mới nhả — chip đã góp vào pot không bao giờ bị mất.

GIẢI ĐẤU (chế độ "t6", xem MODES). Cùng một bộ luật chơi, khác ở vòng đời bàn:
  - Một người tạo phòng và là CHỦ PHÒNG. Mọi người vào sẽ tự ngồi ghế trống
    (đăng ký). Đủ kín ghế thì giải tự khởi tranh; chưa đủ thì chủ phòng bấm
    "Bắt đầu" (cần tối thiểu ``TOURNEY_MIN_PLAYERS`` người).
  - Khởi tranh: tất cả nhận ``CHIP_START`` chip BẰNG NHAU. Không có Mua lại,
    không có Tạm nghỉ. HẾT CHIP LÀ BỊ LOẠI, ghi hạng theo thứ tự rụng (người
    rụng đầu nhận hạng cuối). Còn lại một người là vô địch.
  - Giải đã chạy thì KHÔNG mở ghế nữa: ai vào sau chỉ xem được, ai đã bị loại
    vào lại cũng chỉ xem được (``out_uids``).
  - Tự bấm "Rời giải" giữa giải = bị loại luôn (nếu đang all-in thì chốt loại
    khi ván kết thúc, chip đã góp vẫn tranh pot bình thường).
  - Mất kết nối KHÔNG bị loại ngay: có ``TOURNEY_DISCONNECT_GRACE`` giây để
    quay lại (F5, rớt mạng), quá hạn mới bị loại. Trong lúc đó ghế vẫn bị mù
    ăn và tự Bỏ bài như sòng thật.
  - Mù TĂNG THEO MỨC (``TOURNEY_BLINDS``, mỗi ``TOURNEY_LEVEL_HANDS`` ván một
    mức) — mù cố định thì sáu người với 100.000 chip sẽ đánh tới sáng.

ĐỒNG HỒ. Mỗi lượt ``ACTION_SECONDS``; hết giờ tự Qua (nếu được) hoặc Bỏ bài.
Hết giờ ``TIMEOUTS_TO_SITOUT`` lần liên tiếp thì bị chuyển sang tạm nghỉ (bàn
tiền lẻ; giải đấu không có tạm nghỉ nên cứ bị mù ăn dần).

Module thuần Python, không I/O. Bảng xếp hạng và avatar do Hub bơm vào qua hai
callback ``on_hand_end`` và ``avatar_for``.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from games import GameError, Player, SeatedRoom, clean_name, is_bot_uid
from poker_hand import best_hand, card_label, describe, describe_cards, fresh_deck

# --------------------------------------------------------------------------- #
# hằng số bàn
# --------------------------------------------------------------------------- #
CHIP_START = 100_000
SMALL_BLIND = 500
BIG_BLIND = 1_000

ACTION_SECONDS = 25.0           # mỗi lượt cược
AWAY_SECONDS = 6.0              # người mất kết nối: không bắt cả bàn chờ lâu
START_GRACE_SECONDS = 4.0       # bàn vừa đủ người: chờ người khác kịp ngồi
RUNOUT_SECONDS = 1.8            # mỗi lá lật khi cả bàn all-in
RIT_VOTE_SECONDS = 10.0         # bỏ phiếu "chia 2 lần"
SHOWDOWN_SECONDS = 7.0          # xem kết quả lật bài (và kịp bấm khoe bài)
FOLD_WIN_SECONDS = 5.0          # thắng không cần lật bài
TIMEOUTS_TO_SITOUT = 2

PREFLOP, FLOP, TURN, RIVER = "preflop", "flop", "turn", "river"
STREETS = (PREFLOP, FLOP, TURN, RIVER)
BOARD_SIZE = {PREFLOP: 0, FLOP: 3, TURN: 4, RIVER: 5}
STREET_NAME = {PREFLOP: "Preflop", FLOP: "Flop", TURN: "Turn", RIVER: "River"}

FEED_MAX = 80

# ---- giải đấu loại trực tiếp ---------------------------------------------- #
#: Tối thiểu bao nhiêu người thì chủ phòng bấm Bắt đầu được.
TOURNEY_MIN_PLAYERS = 2
#: Bao nhiêu ván thì mù lên một mức.
TOURNEY_LEVEL_HANDS = 8
#: Thang mù. Mức cuối giữ nguyên nếu giải dài hơn thang.
TOURNEY_BLINDS = (
    (500, 1_000), (1_000, 2_000), (1_500, 3_000), (2_500, 5_000),
    (4_000, 8_000), (6_000, 12_000), (10_000, 20_000), (15_000, 30_000),
    (25_000, 50_000), (40_000, 80_000),
)
#: Mất kết nối giữa giải: bấy nhiêu giây để quay lại, quá hạn thì bị loại.
TOURNEY_DISCONNECT_GRACE = 45.0

#: Câu cà khịa dựng sẵn — bấm là gửi, hiện thành bong bóng trên ghế.
TAUNTS = (
    "All-in đi sợ gì 😏", "Bài rác mà bluff hoài 🤡", "Fold cho đỡ nhục 😂",
    "Tay này chắc 7-2 🍃", "Gà quá gà 🐔", "Nhanh lên, bàn chờ ngủ gật 😴",
    "Hết chip rồi à 👀", "Call đi, số đẹp lắm 🍀", "Dằn mặt tí 🔥",
    "Mơ gì sảnh rồng thế 🐉", "GG, xin vía 🙏", "Bài đẹp không nói nhiều 😎",
)


def vn(amount: int) -> str:
    """1000000 -> "1.000.000" (dấu phân nghìn kiểu Việt)."""
    return f"{int(amount):,}".replace(",", ".")


@dataclass(frozen=True)
class Card:
    value: int
    suit: str

    def as_tuple(self) -> tuple[int, str]:
        return (self.value, self.suit)

    def to_json(self) -> dict:
        return {"v": self.value, "s": self.suit, "label": card_label(self.as_tuple())}


@dataclass
class SeatState:
    """Một ghế đang có người. Chip sống qua nhiều ván; phần còn lại dọn mỗi ván."""
    chips: int = CHIP_START
    sitting_out: bool = False
    leaving: bool = False           # rời ghế khi ván hiện tại kết thúc
    timeouts: int = 0               # số lần hết giờ LIÊN TIẾP
    # ---- giải đấu ----
    eliminated: bool = False        # đã bị loại khỏi giải, ngồi xem tới hết
    place: int = 0                  # hạng chung cuộc (1 = vô địch)
    quitting: bool = False          # tự rời giải, chốt loại khi hết ván
    # ---- trong ván ----
    hole: list[Card] = field(default_factory=list)
    dealt: bool = False             # được chia bài ván này
    folded: bool = False
    all_in: bool = False
    bet: int = 0                    # đã đặt ở vòng cược hiện tại
    acted: bool = False             # đã hành động kể từ lần tố đầy đủ gần nhất
    can_raise: bool = True          # còn quyền tố (all-in thiếu không mở lại)
    action: str = ""                # sb | bb | check | call | bet | raise | allin | fold
    action_amount: int = 0
    shown: bool = False             # thắng không cần lật nhưng muốn khoe bài

    @property
    def live(self) -> bool:
        return self.dealt and not self.folded

    def clear_hand(self) -> None:
        self.hole = []
        self.dealt = self.folded = self.all_in = self.acted = self.shown = False
        self.can_raise = True
        self.bet = self.action_amount = 0
        self.action = ""


class PokerRoom(SeatedRoom):
    CHANNEL = "poker"
    MODES = {
        "p6": {"label": "Bàn 6 người", "seats": 6},
        "p4": {"label": "Bàn 4 người", "seats": 4},
        "p2": {"label": "Tay đôi", "seats": 2},
        # Giải đấu loại trực tiếp: chip bằng nhau, hết chip là ra, mù tăng dần.
        "t6": {"label": "Giải đấu 6 người (loại trực tiếp)", "seats": 6,
               "tournament": True},
        "t4": {"label": "Giải đấu 4 người (loại trực tiếp)", "seats": 4,
               "tournament": True},
    }
    DEFAULT_MODE = "p6"
    HAS_CLOCK = True

    @classmethod
    def seats_for(cls, mode: str) -> tuple[str, ...]:
        return tuple(f"S{i + 1}" for i in range(cls.MODES[mode]["seats"]))

    def __init__(self, code: str, mode: str = "") -> None:
        super().__init__(code, mode)
        self.rng = random.Random()
        # Ghế trống mang 0 chip; chip chỉ được cấp khi có người ngồi vào.
        self.state: dict[str, SeatState] = {s: SeatState(chips=0) for s in self.SEATS}
        self.settled = False                    # pot của ván này đã chia xong
        self.queue: dict[str, list[str]] = {s: [] for s in self.SEATS}   # uid chờ ghế
        self.bank: dict[str, int] = {}          # uid -> chip khi rời ghế
        self.last_seat: dict[str, str] = {}     # uid -> ghế ngồi gần nhất
        self.deck: list[Card] = []
        self.board: list[Card] = []
        self.street = PREFLOP
        self.phase = "idle"                     # idle | starting | betting | runout | showdown
        self.deadline = 0.0
        self.start_at = 0.0
        self.actor = ""
        self.button = ""
        self.sb_seat = ""
        self.bb_seat = ""
        self.current_bet = 0
        # Mù của bàn. Bàn tiền lẻ giữ nguyên hằng số; giải đấu tăng theo mức.
        self.sb = SMALL_BLIND
        self.bb = BIG_BLIND
        self.min_raise = self.bb
        self.contrib: dict[str, int] = {}       # đã góp cả ván, theo ghế
        self.hand_uids: dict[str, str] = {}     # ghế -> uid lúc chia (cho leaderboard)
        self.hand_no = 0
        self.result: dict | None = None
        self.feed: list[dict] = []
        self._cleaning = False
        # Chia 2 lần (run it twice) — xem _begin_all_in.
        self.rit_votes: dict[str, bool | None] = {}
        self.rit = False                # đã chốt chia 2 lần
        self.run_no = 1                 # đang chạy bàn thứ mấy
        self.base_board: list[Card] = []
        self.base_street = PREFLOP
        self.board1: list[Card] = []    # bàn của lần chia thứ nhất
        # ---- giải đấu loại trực tiếp ----
        self.tournament = bool(self.MODES[self.mode].get("tournament"))
        self.tstage = "lobby" if self.tournament else ""   # lobby | running | done
        self.host_uid = ""                      # chủ phòng, người bấm Bắt đầu
        self.level = 0                          # mức mù hiện tại (index)
        self.placements: list[dict] = []        # bảng hạng, hạng nhỏ = cao
        self.out_uids: set[str] = set()         # đã bị loại: vào lại chỉ xem
        self.out_deadline: dict[str, float] = {}  # ghế -> hạn quay lại
        self.hand_start_chips: dict[str, int] = {}  # chip đầu ván (xếp hạng)
        # Hub gắn vào (xem hub._wire_poker_room). None thì bỏ qua.
        self.on_hand_end = None
        self.avatar_for = None

    # ======================================================================
    # tra cứu
    # ======================================================================
    def _seat_label(self, mark: str) -> str:
        return f"Ghế {self.SEATS.index(mark) + 1}" if mark in self.SEATS else mark

    def _name(self, seat: str) -> str:
        player = self.seat(seat)
        return player.name if player else self._seat_label(seat)

    def _after(self, seat: str, pred) -> str:
        """Ghế đầu tiên SAU ``seat`` theo chiều kim đồng hồ thỏa ``pred``.
        Duyệt đủ một vòng, nên chính ``seat`` được xét cuối cùng."""
        n = len(self.SEATS)
        start = self.SEATS.index(seat) if seat in self.SEATS else -1
        for step in range(1, n + 1):
            cand = self.SEATS[(start + step) % n]
            if pred(cand):
                return cand
        return ""

    def _live(self) -> list[str]:
        return [s for s in self.SEATS if self.state[s].live]

    def _able(self) -> list[str]:
        """Còn trong ván VÀ còn chip để cược."""
        return [s for s in self._live() if not self.state[s].all_in]

    def _ready(self, seat: str) -> bool:
        """Được chia bài ở ván kế tiếp."""
        player = self.seat(seat)
        st = self.state[seat]
        return (player is not None and player.connected and st.chips > 0
                and not st.sitting_out and not st.leaving and not st.eliminated)

    def free_marks(self) -> list[str]:
        """Ghế còn nhận người. Giải đã khởi tranh thì KHÔNG còn ghế nào — kể cả
        ghế chưa ai ngồi — nên ``RoomManager.quick()`` và sảnh chờ không ném
        người lạ vào giữa giải."""
        if self.tournament and self.tstage != "lobby":
            return []
        return super().free_marks()

    def _alive_seats(self) -> list[str]:
        """Giải đấu: ghế còn trong giải (có người, chưa bị loại).

        Khác ``_ready``: người mất kết nối vẫn còn trong giải — họ còn thời
        gian quay lại, và dù không quay lại thì mù vẫn ăn tới khi hết chip.
        """
        return [s for s in self.SEATS
                if self.seat(s) is not None and not self.state[s].eliminated]

    def pot_total(self) -> int:
        """Chip đang nằm giữa bàn. Sau khi chia pot thì bằng 0 — ``contrib``
        vẫn được giữ để tính thắng/thua ròng cho bảng xếp hạng."""
        return 0 if self.settled else sum(self.contrib.values())

    def _note(self, text: str, tone: str = "") -> None:
        self.feed.append({"text": text, "tone": tone, "ts": time.time()})
        del self.feed[:-FEED_MAX]

    # ======================================================================
    # ghế, hàng chờ, chip
    # ======================================================================
    def _seat_player(self, player: Player, seat: str) -> None:
        player.mark = seat
        # Giải đấu: mọi người VÀO BẰNG NHAU, không có chuyện mang chip cũ sang.
        chips = CHIP_START if self.tournament else self.bank.pop(player.uid, CHIP_START)
        self.state[seat] = SeatState(chips=max(0, chips))
        self.last_seat[player.uid] = seat
        for waiting in self.queue.values():
            if player.uid in waiting:
                waiting.remove(player.uid)
        tail = ""
        if self.tournament:
            tail = " — chờ giải khởi tranh"
        elif chips <= 0:
            tail = " — hết chip, bấm Rebuy để chơi"
        elif self.phase in ("betting", "runout") and not self._cleaning:
            tail = " — chờ ván sau"
        self.system(f"{player.name} vào {self._seat_label(seat)} với {vn(chips)} chip{tail}.")
        self._try_start()

    def _release_seat(self, seat: str) -> None:
        """Nhả ghế: cất chip vào ``bank`` rồi cho người đầu hàng chờ vào."""
        player = self.seat(seat)
        if player is not None:
            self.bank[player.uid] = self.state[seat].chips
            self.last_seat[player.uid] = seat
            player.mark = ""
            if not player.connected:
                self.players.pop(player.uid, None)
        self.state[seat] = SeatState(chips=0)
        self._promote(seat)

    def _promote(self, seat: str) -> None:
        if self.tournament:
            return          # giải đấu không có hàng chờ, ghế trống là trống
        waiting = self.queue[seat]
        while waiting and self.seat(seat) is None:
            uid = waiting.pop(0)
            player = self.players.get(uid)
            if player is not None and player.connected and not player.mark:
                self.system(f"Tới lượt {player.name} trong hàng chờ.")
                self._seat_player(player, seat)

    def join(self, uid: str, name: str, color: str = "") -> Player:
        """Vào phòng. uid cũ được nối lại đúng ghế nên F5 không mất ván."""
        self.touched = time.time()
        player = self.players.get(uid)
        if player is not None:
            if name:
                player.name = clean_name(name)
            if color:
                player.color = color
            if not player.connected:
                player.connected = True
                self.system(f"{player.name} đã kết nối lại.")
                # Giải đấu: về kịp hạn thì huỷ án loại.
                if player.mark and self.out_deadline.pop(player.mark, None):
                    self.system(f"{player.name} quay lại kịp — vẫn còn trong giải.")
                # Bàn đang chờ vì thiếu người: người này về là đủ, chia lại ngay.
                self._try_start()
            return player

        player = Player(uid=uid, name=clean_name(name), color=color or "#6366f1")
        self.players[uid] = player
        if self.tournament:
            self._tourney_join(player)
            return player
        free = self.free_marks()
        if free:
            prefer = self.last_seat.get(uid)
            self._seat_player(player, prefer if prefer in free else free[0])
        else:
            self.system(f"{player.name} vào xem. Bàn kín — bấm “Xếp hàng” trên một ghế.")
        return player

    # ---- giải đấu: vào phòng, chủ phòng -----------------------------------
    def _tourney_join(self, player: Player) -> None:
        """Người MỚI vào một phòng giải đấu.

        Chỉ lúc đang nhận đăng ký mới được ngồi. Giải chạy rồi thì vào sau =
        khán giả, và người đã bị loại quay lại cũng chỉ là khán giả.
        """
        if self.tstage != "lobby":
            self.system(f"{player.name} vào xem — giải đang diễn ra, không mở ghế.")
            return
        if player.uid in self.out_uids:
            self.system(f"{player.name} đã rời giải trước đó, chỉ xem được.")
            return
        free = self.free_marks()
        if not free:
            self.system(f"{player.name} vào xem — danh sách đăng ký đã đủ.")
            return
        if not self.host_uid:
            self.host_uid = player.uid
            self.system(f"{player.name} là chủ phòng — bấm “Bắt đầu giải” khi đủ người.")
        prefer = self.last_seat.get(player.uid)
        self._seat_player(player, prefer if prefer in free else free[0])

    def _ensure_host(self) -> None:
        """Chọn lại chủ phòng nếu người cũ đã rời. Giải đang chạy thì giữ nguyên
        (lúc đó chủ phòng không còn quyền gì nữa)."""
        if not self.tournament or self.tstage == "running":
            return
        player = self.players.get(self.host_uid)
        if player is not None and player.mark and player.connected:
            return
        for seat in self.SEATS:
            other = self.seat(seat)
            if other is not None and not other.bot and other.connected:
                self.host_uid = other.uid
                self.system(f"{other.name} là chủ phòng.")
                return
        self.host_uid = ""

    def _tourney_gate(self, uid: str) -> None:
        """Chặn mọi đường ngồi vào bàn khi giải đã khởi tranh."""
        if self.tstage != "lobby":
            raise GameError("Giải đã khởi tranh — bạn chỉ có thể xem.")
        if uid in self.out_uids:
            raise GameError("Bạn đã rời giải này, chỉ xem được thôi.")

    def sit(self, uid: str) -> None:
        player = self.players[uid]
        if player.mark:
            st = self.state[player.mark]
            if st.leaving:
                st.leaving = False
                self.system(f"{player.name} đổi ý, ở lại bàn.")
                return
            raise GameError("Bạn đang ngồi rồi.")
        if self.tournament:
            self._tourney_gate(uid)
        free = self.free_marks()
        if not free:
            raise GameError("Bàn kín ghế. Bấm “Xếp hàng” trên một ghế để chờ.")
        prefer = self.last_seat.get(uid)
        self._seat_player(player, prefer if prefer in free else free[0])
        self._ensure_host()
        self.touched = time.time()

    def request_seat(self, uid: str, seat: str) -> None:
        """Bấm vào một ghế: trống thì ngồi, có người thì xếp hàng chờ ghế đó."""
        player = self.players.get(uid)
        if player is None:
            raise GameError("Bạn chưa vào phòng.")
        if seat not in self.SEATS:
            raise GameError("Ghế không hợp lệ.")
        if player.mark:
            raise GameError("Bạn đang ngồi rồi.")
        if self.tournament:
            self._tourney_gate(uid)
            if self.seat(seat) is not None:
                raise GameError("Ghế này đã có người đăng ký.")
            self._seat_player(player, seat)
            self._ensure_host()
            return
        if self.seat(seat) is None:
            self._seat_player(player, seat)
            return
        if uid in self.queue[seat]:
            raise GameError("Bạn đã ở trong hàng chờ ghế này.")
        self.queue[seat].append(uid)
        self.system(f"{player.name} xếp hàng chờ {self._seat_label(seat)} "
                    f"(thứ {len(self.queue[seat])}).")
        self.touched = time.time()

    def leave_queue(self, uid: str, seat: str) -> None:
        if seat not in self.queue or uid not in self.queue[seat]:
            raise GameError("Bạn không ở trong hàng chờ ghế đó.")
        self.queue[seat].remove(uid)
        self.touched = time.time()

    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        seat = player.mark
        st = self.state[seat]
        if self.tournament:
            self._tourney_stand(player)
            self.touched = time.time()
            return
        if self.status == "playing" and st.live:
            st.leaving = True
            self.system(f"{player.name} sẽ rời ghế khi ván kết thúc.")
            if self.phase == "betting" and not st.all_in:
                self._fold_seat(seat, "rời bàn")
        else:
            self.system(f"{player.name} rời {self._seat_label(seat)}.")
            self._release_seat(seat)
            self._try_start()
        self.touched = time.time()

    def _tourney_stand(self, player: Player) -> None:
        """Bấm "Rời giải". Lúc đăng ký thì chỉ là rút tên; giải đã chạy thì
        coi như BỊ LOẠI, không có đường quay lại bàn."""
        seat = player.mark
        st = self.state[seat]
        if self.tstage == "lobby":
            self.system(f"{player.name} rút khỏi danh sách đăng ký.")
            self._release_seat(seat)
            self._ensure_host()
            self._try_start()
            return
        if st.eliminated:
            return                      # đã bị loại rồi, đang ngồi xem
        st.quitting = True
        # Đang trong ván: bỏ bài để bàn chạy tiếp. Nếu đã all-in thì không bỏ
        # được — chip đã góp vẫn tranh pot, chốt loại khi ván kết thúc.
        if st.live and self.phase == "betting" and not st.all_in:
            self._fold_seat(seat, "rời giải")
        if st.live:
            self.system(f"{player.name} rời giải — chốt bị loại khi ván này xong.")
        else:
            self._eliminate(seat, "tự rời giải")

    def disconnect(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None:
            return
        player.connected = False
        self.touched = time.time()
        for waiting in self.queue.values():
            if uid in waiting:
                waiting.remove(uid)
        if self.tournament and self.tstage == "running":
            self._tourney_disconnect(player)
            return
        if not player.mark:
            self.players.pop(uid, None)
            return
        seat = player.mark
        if self.status == "playing" and self.state[seat].live:
            # Giữ ghế tới hết ván (chip đã góp vẫn nằm trong pot). Đang tới lượt
            # thì rút ngắn đồng hồ, không bắt cả bàn chờ người đã đi.
            self.system(f"{player.name} mất kết nối — giữ ghế tới hết ván.")
            if self.actor == seat and self.phase == "betting":
                self.deadline = min(self.deadline, time.time() + AWAY_SECONDS)
        else:
            self.system(f"{player.name} rời bàn.")
            self._release_seat(seat)
            self._try_start()

    def _tourney_disconnect(self, player: Player) -> None:
        """Mất kết nối giữa giải. Không loại ngay: F5 hay rớt wifi là chuyện
        thường, cho ``TOURNEY_DISCONNECT_GRACE`` giây để quay lại. Trong lúc đó
        ghế vẫn bị mù ăn và tự bỏ bài, đúng như bàn thật."""
        seat = player.mark
        if not seat:
            self.players.pop(player.uid, None)
            return
        if self.state[seat].eliminated:
            return                      # khán giả đã bị loại: giữ ghế cho dễ nhìn
        self.out_deadline[seat] = time.time() + TOURNEY_DISCONNECT_GRACE
        self.system(f"{player.name} mất kết nối — còn {int(TOURNEY_DISCONNECT_GRACE)} "
                    "giây để quay lại, quá hạn là bị loại.")
        if self.actor == seat and self.phase == "betting":
            self.deadline = min(self.deadline, time.time() + AWAY_SECONDS)

    def rebuy(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn chưa ngồi ở bàn này.")
        if self.tournament:
            raise GameError("Giải đấu loại trực tiếp: hết chip là bị loại, không mua lại.")
        st = self.state[player.mark]
        if st.chips > 0:
            raise GameError("Bạn vẫn còn chip, chưa cần Rebuy.")
        if self.phase in ("betting", "ritvote", "runout") and st.live:
            raise GameError("Chờ ván này kết thúc rồi Rebuy.")
        st.chips = CHIP_START
        st.sitting_out = False
        st.timeouts = 0
        self.system(f"{player.name} rebuy {vn(CHIP_START)} chip.")
        self.touched = time.time()
        self._try_start()

    def toggle_sitout(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn chưa ngồi ở bàn này.")
        if self.tournament:
            raise GameError("Giải đấu không có tạm nghỉ — đã vào là đánh tới cùng.")
        st = self.state[player.mark]
        st.sitting_out = not st.sitting_out
        st.timeouts = 0
        self.system(f"{player.name} " + ("Sit out (không chia bài)." if st.sitting_out
                                         else "quay lại bàn (I'm back)."))
        self._try_start()

    def show_cards(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn đang xem.")
        st = self.state[player.mark]
        if self.phase != "showdown" or not st.dealt or not st.hole:
            raise GameError("Chỉ Show cards được khi ván vừa kết thúc.")
        if self._is_revealed(player.mark):
            raise GameError("Bài của bạn đang ngửa rồi.")
        st.shown = True
        cards = " ".join(c.to_json()["label"] for c in st.hole)
        self._note(f"{player.name} shows {cards}", "show")

    def taunt(self, uid: str, taunt_id: int) -> None:
        player = self.players.get(uid)
        if player is None:
            return
        if not 0 <= taunt_id < len(TAUNTS):
            raise GameError("Câu cà khịa không hợp lệ.")
        now = time.time()
        if now - player.last_chat < 1.0:
            raise GameError("Cà khịa chậm thôi.")
        player.last_chat = now
        self.chat.append({"kind": "taunt", "name": player.name, "color": player.color,
                          "mark": player.mark, "text": TAUNTS[taunt_id], "ts": now})
        del self.chat[:-80]
        self.touched = now

    # Xì Tố không có "xin thua cả ván" hay "đánh lại": mỗi ván tự chia.
    def resign(self, uid: str) -> None:
        self.fold(uid)

    def vote_rematch(self, uid: str) -> None:
        raise GameError("Xì Tố tự chia ván mới, không cần xin đánh lại.")

    def reset_match(self) -> None:          # hook bắt buộc của SeatedRoom
        pass

    # ---- máy chơi đơn (AI Bot) -------------------------------------------- #
    def add_bot(self, level: str = "normal", mark: str = "") -> Player | None:
        """Lấp mọi ghế trống bằng AI Bot, chừa ghế đầu tiên cho người mở phòng."""
        if self.bot_players():
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        if not any(p.mark and not p.bot for p in self.players.values()):
            if len(free) < 2:
                raise GameError("Không còn ghế cho máy.")
            free = free[1:]
        if not free:
            raise GameError("Không còn ghế cho máy.")
        from bot_poker import BOT_PROFILES
        seated = None
        for slot, seat in enumerate(free):
            self.state[seat] = SeatState(chips=CHIP_START)
            prof_name, _ = BOT_PROFILES[slot % len(BOT_PROFILES)]
            seated = self._seat_bot(seat, level, f"{prof_name} 🤖", slot=slot)
        return seated

    def bot_to_act(self) -> Player | None:
        if not self.in_progress():
            return None
        if self.phase == "betting" and self.actor:
            p = self.seat(self.actor)
            if p is not None and p.bot:
                return p
        if self.phase == "ritvote":
            for bot in self.bot_players():
                if bot.mark and bot.mark in self.rit_votes and self.rit_votes[bot.mark] is None:
                    return bot
        return None

    def progress_token(self) -> tuple:
        return (
            self.status,
            self.hand_no,
            self.phase,
            self.street,
            self.actor,
            self.current_bet,
            tuple((s, self.state[s].bet, self.state[s].acted) for s in self.SEATS),
            tuple(sorted(self.rit_votes.items())),
        )

    # ======================================================================
    # vòng đời một ván
    # ======================================================================
    def _try_start(self) -> None:
        if self.status == "playing":
            return
        if self.tournament:
            if self.tstage == "lobby":
                # Đủ KÍN GHẾ thì tự khởi tranh, chưa đủ thì chờ chủ phòng bấm.
                ready = [s for s in self.SEATS if self._ready(s)]
                if len(ready) >= len(self.SEATS):
                    self._begin_tournament(ready, auto=True)
                return
            if self.tstage != "running":
                return                  # giải đã xong: không tự chia nữa
        ready = [s for s in self.SEATS if self._ready(s)]
        if len(ready) >= 2:
            if self.phase != "starting":
                self.phase = "starting"
                self.start_at = time.time() + START_GRACE_SECONDS
        elif self.phase == "starting":
            self.phase = "idle"
            self.start_at = 0.0

    # ======================================================================
    # giải đấu loại trực tiếp
    # ======================================================================
    def start_tournament(self, uid: str) -> None:
        """Chủ phòng bấm "Bắt đầu giải" (hoặc "Giải mới" khi đã có vô địch)."""
        if not self.tournament:
            raise GameError("Bàn này không phải giải đấu.")
        if not self.host_uid or uid != self.host_uid:
            raise GameError("Chỉ chủ phòng mới bắt đầu được giải.")
        if self.tstage == "done":
            self._reset_tournament()
            return
        if self.tstage != "lobby":
            raise GameError("Giải đang diễn ra.")
        ready = [s for s in self.SEATS if self._ready(s)]
        if len(ready) < TOURNEY_MIN_PLAYERS:
            raise GameError(f"Cần ít nhất {TOURNEY_MIN_PLAYERS} người để khởi tranh.")
        self._begin_tournament(ready, auto=False)

    def _begin_tournament(self, ready: list[str], auto: bool) -> None:
        """Khoá danh sách và chia ván đầu. Từ đây ghế không bao giờ mở lại."""
        self.tstage = "running"
        self.placements = []
        self.out_uids = set()
        self.out_deadline = {}
        self.hand_no = 0
        self.level = 0
        self.sb, self.bb = TOURNEY_BLINDS[0]
        self.min_raise = self.bb
        for seat in self.SEATS:
            if seat in ready:
                self.state[seat] = SeatState(chips=CHIP_START)
            elif self.seat(seat) is None:
                self.state[seat] = SeatState(chips=0)
        names = ", ".join(self._name(s) for s in ready)
        self.system(("Đủ người — giải tự khởi tranh! " if auto
                     else "Chủ phòng bấm bắt đầu — giải khởi tranh! ")
                    + f"{len(ready)} người: {names}. Mỗi người {vn(CHIP_START)} chip, "
                      "hết chip là bị loại, người cuối cùng còn chip là vô địch.")
        self._note(f"Tournament started · {len(ready)} players", "deal")
        self.phase = "starting"
        self.start_at = time.time() + START_GRACE_SECONDS
        self.touched = time.time()

    def _apply_level(self) -> None:
        """Chốt mức mù cho ván sắp chia. Gọi sau khi đã tăng ``hand_no``."""
        index = min(max(0, self.hand_no - 1) // TOURNEY_LEVEL_HANDS,
                    len(TOURNEY_BLINDS) - 1)
        sb, bb = TOURNEY_BLINDS[index]
        if (sb, bb) != (self.sb, self.bb):
            self.sb, self.bb = sb, bb
            self.system(f"Mức {index + 1}: mù lên {vn(sb)}/{vn(bb)}.")
            self._note(f"Blinds up — level {index + 1}: {vn(sb)}/{vn(bb)}", "street")
        self.level = index

    def _eliminate(self, seat: str, reason: str) -> None:
        """Loại một ghế và ghi hạng. Người rụng đầu nhận hạng cuối."""
        st = self.state[seat]
        if st.eliminated:
            return
        place = max(1, len(self._alive_seats()))        # tính cả ghế này
        player = self.seat(seat)
        name = player.name if player else self._seat_label(seat)
        st.eliminated = True
        st.quitting = False
        st.place = place
        st.chips = 0            # chip bỏ lại (nếu tự rời) coi như rời sàn
        st.clear_hand()
        self.out_deadline.pop(seat, None)
        if player is not None:
            self.out_uids.add(player.uid)
        self.placements.append({"place": place, "seat": seat, "name": name,
                                "uid": player.uid if player else "", "reason": reason})
        self.system(f"{name} bị loại — hạng {place} ({reason}).")
        self._note(f"{name} eliminated · #{place} ({reason})", "fold")

    def _tourney_sweep(self) -> None:
        """Giữa hai ván: chốt loại người tự rời, mất kết nối quá hạn, hết chip.

        Xếp người cùng rụng một ván theo chip ĐẦU VÁN: ai vào ván với ít chip
        hơn thì rụng trước, nhận hạng thấp hơn — y như luật giải thật.
        """
        now = time.time()
        for seat in self.SEATS:
            st = self.state[seat]
            if st.quitting and not st.eliminated and self.seat(seat) is not None:
                self._eliminate(seat, "tự rời giải")
        for seat, limit in list(self.out_deadline.items()):
            player = self.seat(seat)
            if player is None or player.connected or self.state[seat].eliminated:
                self.out_deadline.pop(seat, None)
            elif now >= limit:
                self.out_deadline.pop(seat, None)
                self._eliminate(seat, "mất kết nối")
        busted = [s for s in self._alive_seats() if self.state[s].chips <= 0]
        busted.sort(key=lambda s: self.hand_start_chips.get(s, 0))
        for seat in busted:
            self._eliminate(seat, "hết chip")

    def _finish_tournament(self) -> None:
        """Còn một người: chốt vô địch, bàn đứng lại."""
        self.tstage = "done"
        self.status = "finished"
        self.phase = "idle"
        self.actor = ""
        self.deadline = 0.0
        self.start_at = 0.0
        self.board = []
        self.board1 = []
        self.result = None
        self.contrib = {}
        self.settled = False
        self.rit = False
        self.rit_votes = {}
        for st in self.state.values():
            st.clear_hand()
        alive = self._alive_seats()
        if alive:
            seat = alive[0]
            player = self.seat(seat)
            name = player.name if player else self._seat_label(seat)
            self.state[seat].place = 1
            self.winner = seat
            # scores ở đây là SỐ VÁN thắng (xem _close_hand), không phải cúp —
            # chức vô địch nằm ở self.winner và self.placements.
            self.placements.append({"place": 1, "seat": seat, "name": name,
                                    "uid": player.uid if player else "",
                                    "reason": "vô địch"})
            self.system(f"🏆 {name} VÔ ĐỊCH giải đấu!")
            self._note(f"🏆 {name} wins the tournament!", "win")
        else:
            self.winner = ""
            self.system("Giải kết thúc — không còn ai ở bàn.")
        self.placements.sort(key=lambda row: row["place"])
        self._ensure_host()
        self.touched = time.time()

    def _reset_tournament(self) -> None:
        """Chủ phòng mở giải mới ngay trong phòng cũ: mọi người về mốc chip
        ban đầu, án loại của giải trước được xoá."""
        self.tstage = "lobby"
        self.status = "waiting"
        self.winner = ""
        self.phase = "idle"
        self.deadline = 0.0
        self.start_at = 0.0
        self.actor = ""
        self.hand_no = 0
        self.level = 0
        self.sb, self.bb = TOURNEY_BLINDS[0]
        self.min_raise = self.bb
        self.current_bet = 0
        self.button = self.sb_seat = self.bb_seat = ""
        self.placements = []
        self.out_uids = set()
        self.out_deadline = {}
        self.hand_start_chips = {}
        self.board = []
        self.board1 = []
        self.result = None
        self.contrib = {}
        self.settled = False
        self.rit = False
        self.rit_votes = {}
        self.feed = []
        for seat in self.SEATS:
            player = self.seat(seat)
            if player is None:
                self.state[seat] = SeatState(chips=0)
            elif not player.connected:
                player.mark = ""
                self.players.pop(player.uid, None)
                self.state[seat] = SeatState(chips=0)
            else:
                self.state[seat] = SeatState(chips=CHIP_START)
        self.system(f"Giải mới — mọi người về {vn(CHIP_START)} chip. "
                    "Chủ phòng bấm “Bắt đầu giải” khi đủ người.")
        self._ensure_host()
        self._try_start()

    def _cleanup_seats(self) -> None:
        """Giữa hai ván: nhả ghế người rời / mất kết nối, nhường ghế người hết
        chip cho hàng chờ, rồi lấp ghế trống từ hàng chờ."""
        self._cleaning = True
        try:
            for seat in self.SEATS:
                player = self.seat(seat)
                if player is None:
                    continue
                st = self.state[seat]
                if st.leaving or not player.connected:
                    self.system(f"{player.name} rời {self._seat_label(seat)}.")
                    self._release_seat(seat)
                elif player.bot and st.chips <= 0:
                    st.chips = CHIP_START
                    st.timeouts = 0
                    self.system(f"{player.name} tự rebuy {vn(CHIP_START)} chip.")
                elif st.chips <= 0 and self.queue[seat]:
                    self.system(f"{player.name} hết chip, nhường ghế cho người đang chờ.")
                    self._release_seat(seat)
            for seat in self.SEATS:
                if self.seat(seat) is None:
                    self._promote(seat)
        finally:
            self._cleaning = False

    def _deal_hand(self) -> None:
        if self.tournament:
            self._tourney_sweep()
            if len(self._alive_seats()) <= 1:
                self._finish_tournament()
                return
        else:
            self._cleanup_seats()
        ready = [s for s in self.SEATS if self._ready(s)]
        self.actor = ""
        self.rit_votes = {}
        self.rit = False
        self.run_no = 1
        self.base_board = []
        self.board1 = []
        if len(ready) < 2:
            self.status = "waiting"
            self.phase = "idle"
            self.deadline = 0.0
            self.contrib = {}
            self.settled = False
            self.board = []
            self.result = None
            for st in self.state.values():
                st.clear_hand()
            if self.tournament:
                # Giải đấu không dừng vì thiếu người: người còn trong giải đang
                # mất kết nối, chờ họ về (hoặc hết hạn quay lại, xem tick()).
                self._note("Chờ người chơi quay lại…", "wait")
            else:
                self._note("Waiting for players with chips…", "wait")
            return

        self.status = "playing"
        self.hand_no += 1
        if self.tournament:
            self._apply_level()
        self.hand_start_chips = {s: self.state[s].chips for s in ready}
        for seat in self.SEATS:
            self.state[seat].clear_hand()
            self.state[seat].dealt = seat in ready
        self.board = []
        self.result = None
        self.winner = ""
        self.settled = False
        self.contrib = {s: 0 for s in ready}
        self.hand_uids = {s: self.seat(s).uid for s in ready}

        in_ready = lambda s: s in ready      # noqa: E731
        self.button = self._after(self.button or self.SEATS[-1], in_ready)
        if len(ready) == 2:
            self.sb_seat = self.button
            self.bb_seat = self._after(self.button, in_ready)
        else:
            self.sb_seat = self._after(self.button, in_ready)
            self.bb_seat = self._after(self.sb_seat, in_ready)

        self.deck = [Card(v, s) for v, s in fresh_deck()]
        self.rng.shuffle(self.deck)
        for _ in range(2):
            for seat in ready:
                self.state[seat].hole.append(self.deck.pop())

        self._note(f"Hand #{self.hand_no} · Dealer: {self._name(self.button)}", "deal")
        self._post(self.sb_seat, self.sb, "sb")
        self._post(self.bb_seat, self.bb, "bb")
        self.street = PREFLOP
        self.current_bet = self.bb
        self.min_raise = self.bb
        self.phase = "betting"
        first = self._after(self.bb_seat, self._needs_action)
        if first:
            self._begin_turn(first)
        else:
            self._end_street()
        self.touched = time.time()

    def _post(self, seat: str, amount: int, kind: str) -> None:
        paid = self._pay(seat, amount)
        st = self.state[seat]
        st.action, st.action_amount = kind, paid
        label = "small blind" if kind == "sb" else "big blind"
        self._note(f"{self._name(seat)} posts {label} {vn(paid)}", "blind")

    def _pay(self, seat: str, amount: int) -> int:
        st = self.state[seat]
        paid = max(0, min(amount, st.chips))
        st.chips -= paid
        st.bet += paid
        self.contrib[seat] = self.contrib.get(seat, 0) + paid
        if st.chips == 0:
            st.all_in = True
        return paid

    def _needs_action(self, seat: str) -> bool:
        st = self.state[seat]
        if not st.live or st.all_in:
            return False
        if st.bet < self.current_bet:
            return True
        if len(self._able()) <= 1:
            return False            # không còn ai để cược cùng
        return not st.acted

    def _begin_turn(self, seat: str) -> None:
        self.actor = seat
        player = self.seat(seat)
        away = player is None or not player.connected
        self.deadline = time.time() + (AWAY_SECONDS if away else ACTION_SECONDS)

    def _after_action(self, seat: str) -> None:
        live = self._live()
        if len(live) == 1:
            self._award_uncontested(live[0])
            return
        nxt = self._after(seat, self._needs_action)
        if nxt:
            self._begin_turn(nxt)
        else:
            self._end_street()

    def _end_street(self) -> None:
        self.actor = ""
        for st in self.state.values():
            st.bet = 0
        live = self._live()
        if len(live) == 1:
            self._award_uncontested(live[0])
            return
        if self.street == RIVER:
            self._showdown()
            return
        if len(self._able()) <= 1:
            self._begin_all_in(live)
            return
        self._next_street()
        for seat in live:
            st = self.state[seat]
            st.acted = False
            st.can_raise = True
            if not st.all_in:
                st.action, st.action_amount = "", 0
        self.current_bet = 0
        self.min_raise = self.bb
        self.phase = "betting"
        first = self._after(self.button, self._needs_action)
        if first:
            self._begin_turn(first)
        else:
            self._end_street()

    def _next_street(self) -> None:
        self.street = STREETS[STREETS.index(self.street) + 1]
        self.deck.pop()                                   # đốt một lá như sòng thật
        new = []
        while len(self.board) < BOARD_SIZE[self.street]:
            card = self.deck.pop()
            self.board.append(card)
            new.append(card)
        prefix = f"Run {self.run_no} · " if self.rit else ""
        self._note(f"{prefix}{STREET_NAME[self.street]}: "
                   + " ".join(c.to_json()["label"] for c in new), "street")

    # ======================================================================
    # tất tay: bỏ phiếu chia 2 lần, rồi chạy nốt bàn
    # ======================================================================
    def _begin_all_in(self, live: list[str]) -> None:
        """Hết cược mà bàn chung chưa đủ 5 lá: lật bài ngửa, hỏi mọi người còn
        trong ván có muốn CHIA 2 LẦN không. Chỉ khi TẤT CẢ đồng ý mới chia 2
        lần; một người từ chối hoặc hết giờ thì chia 1 lần như thường."""
        self.base_board = list(self.board)
        self.base_street = self.street
        self.board1 = []
        self.rit = False
        self.run_no = 1
        self.rit_votes = {seat: None for seat in live}
        self.phase = "ritvote"
        self.deadline = time.time() + RIT_VOTE_SECONDS
        self._note("All-in! Cards up — Run it twice?", "allin")

    def vote_rit(self, uid: str, yes: bool) -> None:
        player = self.players.get(uid)
        seat = player.mark if player else ""
        if self.phase != "ritvote":
            raise GameError("Không có cuộc bỏ phiếu Run it twice nào.")
        if seat not in self.rit_votes:
            raise GameError("Chỉ người còn trong ván mới được bỏ phiếu.")
        if self.rit_votes[seat] is not None:
            raise GameError("Bạn đã bỏ phiếu rồi.")
        self.rit_votes[seat] = bool(yes)
        self._note(f"{self._name(seat)} {'agrees to' if yes else 'declines to'} run it twice", "")
        if not yes:
            self._start_runout(False)
        elif all(v is True for v in self.rit_votes.values()):
            self._start_runout(True)
        self.touched = time.time()

    def _start_runout(self, twice: bool) -> None:
        self.rit = twice
        self.run_no = 1
        self.phase = "runout"
        self.deadline = time.time() + RUNOUT_SECONDS
        self._note("Everyone agreed — RUNNING IT TWICE, half the pot each run." if twice
                   else "Running it once.", "allin" if twice else "")

    def _runout_step(self) -> None:
        if self.street != RIVER:
            self._next_street()
        elif self.rit and self.run_no == 1:
            # Xong bàn thứ nhất: giữ lại, chạy bàn thứ hai từ đúng chỗ tất tay
            # bằng các lá CÒN LẠI trong bộ (không xào lại).
            self.board1 = list(self.board)
            self.board = list(self.base_board)
            self.street = self.base_street
            self.run_no = 2
            self._next_street()
        else:
            self._showdown()
            return
        self.deadline = time.time() + RUNOUT_SECONDS

    # ======================================================================
    # hành động của người chơi
    # ======================================================================
    def _actor_seat(self, uid: str) -> tuple[str, SeatState]:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn đang xem, không hành động được.")
        if self.phase != "betting":
            raise GameError("Chưa tới lúc hành động.")
        if self.actor != player.mark:
            raise GameError("Chưa tới lượt bạn.")
        st = self.state[player.mark]
        st.timeouts = 0
        return player.mark, st

    def _done(self, seat: str, action: str, amount: int = 0) -> None:
        st = self.state[seat]
        st.acted = True
        st.can_raise = False
        st.action, st.action_amount = action, amount
        self.touched = time.time()
        self._after_action(seat)

    def fold(self, uid: str) -> None:
        seat, _ = self._actor_seat(uid)
        self._fold_seat(seat, "")

    def _fold_seat(self, seat: str, why: str) -> None:
        st = self.state[seat]
        st.folded = True
        st.action, st.action_amount = "fold", 0
        self._note(f"{self._name(seat)} folds{(' (' + why + ')') if why else ''}", "fold")
        if self.actor == seat:
            self._done(seat, "fold")
        else:
            live = self._live()
            if len(live) == 1 and self.phase == "betting":
                self._award_uncontested(live[0])

    def check(self, uid: str) -> None:
        seat, st = self._actor_seat(uid)
        if st.bet < self.current_bet:
            raise GameError(f"Không Check được — phải Call {vn(self.current_bet - st.bet)} hoặc Fold.")
        self._note(f"{self._name(seat)} checks", "check")
        self._done(seat, "check")

    def call(self, uid: str) -> None:
        seat, st = self._actor_seat(uid)
        need = self.current_bet - st.bet
        if need <= 0:
            raise GameError("Không có gì để Call — bấm Check.")
        paid = self._pay(seat, need)
        if st.all_in:
            self._note(f"{self._name(seat)} calls {vn(paid)} and is all-in", "allin")
            self._done(seat, "allin", st.bet)
        else:
            self._note(f"{self._name(seat)} calls {vn(paid)}", "call")
            self._done(seat, "call", st.bet)

    def raise_to(self, uid: str, amount) -> None:
        """Cược (khi chưa ai cược) hoặc tố LÊN TỚI ``amount`` — tổng số đặt
        trong vòng này, đúng như ô nhập "Raise to" của các site poker."""
        seat, st = self._actor_seat(uid)
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise GameError("Số chip không hợp lệ.") from None
        opts = self._action_options(seat)
        if not opts["canRaise"]:
            raise GameError("Không Raise được lúc này — chỉ Call hoặc Fold.")
        max_to = opts["maxTo"]
        amount = min(amount, max_to)
        if amount < opts["minTo"]:
            raise GameError(f"Min raise là {vn(opts['minTo'])}.")
        if amount <= self.current_bet:
            raise GameError("Mức Raise phải cao hơn mức Bet hiện tại.")

        was_bet = self.current_bet == 0
        increment = amount - self.current_bet
        full = increment >= self.min_raise
        self._pay(seat, amount - st.bet)
        self.current_bet = amount
        if full:
            self.min_raise = increment
            for other in self._able():
                if other != seat:
                    self.state[other].acted = False
                    self.state[other].can_raise = True
        else:
            # All-in thiếu: người khác phải trả lời (theo/bỏ) nhưng KHÔNG được
            # tố lại nếu họ đã hành động — can_raise giữ nguyên.
            for other in self._able():
                if other != seat:
                    self.state[other].acted = False

        if st.all_in:
            self._note(f"{self._name(seat)} goes ALL-IN {vn(amount)}!", "allin")
            self._done(seat, "allin", amount)
        elif was_bet:
            self._note(f"{self._name(seat)} bets {vn(amount)}", "raise")
            self._done(seat, "bet", amount)
        else:
            self._note(f"{self._name(seat)} raises to {vn(amount)}", "raise")
            self._done(seat, "raise", amount)

    def all_in(self, uid: str) -> None:
        seat, st = self._actor_seat(uid)
        opts = self._action_options(seat)
        if opts["canRaise"]:
            self.raise_to(uid, opts["maxTo"])
        elif opts["toCall"] > 0:
            self.call(uid)
        else:
            raise GameError("Không còn ai để All-in cùng — bấm Check.")

    def handle(self, uid: str, action: str, msg: dict) -> None:
        if action == "fold":
            self.fold(uid)
        elif action == "check":
            self.check(uid)
        elif action == "call":
            self.call(uid)
        elif action in ("raise", "bet"):
            self.raise_to(uid, msg.get("amount", 0))
        elif action == "allin":
            self.all_in(uid)
        elif action == "start":
            self.start_tournament(uid)
        elif action == "rebuy":
            self.rebuy(uid)
        elif action == "sitout":
            self.toggle_sitout(uid)
        elif action == "show":
            self.show_cards(uid)
        elif action == "rit":
            self.vote_rit(uid, bool(msg.get("yes")))
        elif action == "requestSeat":
            self.request_seat(uid, str(msg.get("seat", "")))
        elif action == "leaveQueue":
            self.leave_queue(uid, str(msg.get("seat", "")))
        elif action == "taunt":
            try:
                taunt_id = int(msg.get("id", -1))
            except (TypeError, ValueError):
                taunt_id = -1
            self.taunt(uid, taunt_id)
        else:
            raise GameError("Hành động không hợp lệ.")

    def _action_options(self, seat: str) -> dict:
        st = self.state[seat]
        to_call = max(0, self.current_bet - st.bet)
        max_to = st.bet + st.chips
        others_able = [s for s in self._able() if s != seat]
        can_raise = st.can_raise and max_to > self.current_bet and bool(others_able)
        min_to = self.bb if self.current_bet == 0 else self.current_bet + self.min_raise
        min_to = min(min_to, max_to)
        return {
            "toCall": to_call,
            "callAmount": min(to_call, st.chips),
            "canCheck": to_call == 0,
            "callIsAllIn": to_call > 0 and to_call >= st.chips,
            "canRaise": can_raise,
            "minTo": min_to,
            "maxTo": max_to,
            "currentBet": self.current_bet,
            "myBet": st.bet,
            "pot": self.pot_total(),
            "isBet": self.current_bet == 0,
        }

    # ======================================================================
    # kết thúc ván
    # ======================================================================
    def _return_uncalled(self) -> dict[str, int]:
        """Phần cược cao hơn tất cả người khác (không ai theo) được trả lại."""
        if len(self.contrib) < 1:
            return {}
        ordered = sorted(self.contrib.items(), key=lambda kv: -kv[1])
        top_seat, top = ordered[0]
        second = ordered[1][1] if len(ordered) > 1 else 0
        if top <= second:
            return {}
        diff = top - second
        self.contrib[top_seat] -= diff
        self.state[top_seat].chips += diff
        self._note(f"Uncalled bet {vn(diff)} returned to {self._name(top_seat)}", "")
        return {top_seat: diff}

    def _build_pots(self, live: list[str]) -> list[dict]:
        levels = sorted({v for v in self.contrib.values() if v > 0})
        pots: list[dict] = []
        prev = 0
        for level in levels:
            amount = sum(min(v, level) - prev for v in self.contrib.values() if v > prev)
            eligible = [s for s in live if self.contrib.get(s, 0) >= level]
            prev = level
            if amount <= 0:
                continue
            if pots and set(pots[-1]["eligible"]) == set(eligible):
                pots[-1]["amount"] += amount
            else:
                pots.append({"amount": amount, "eligible": eligible})
        return pots

    def _left_of_button(self, seat: str) -> int:
        n = len(self.SEATS)
        btn = self.SEATS.index(self.button) if self.button in self.SEATS else 0
        return (self.SEATS.index(seat) - btn - 1) % n

    def _award_uncontested(self, winner: str) -> None:
        self.actor = ""
        for st in self.state.values():
            st.bet = 0
        refund = self._return_uncalled()
        pot = self.pot_total()
        self.state[winner].chips += pot
        payouts = {winner: pot}
        self.result = {
            "showdown": False, "winners": [winner], "payouts": payouts, "refund": refund,
            "pots": [{"name": "Pot", "amount": pot, "winners": [winner], "label": ""}],
            "hands": {},
        }
        self._note(f"{self._name(winner)} wins {vn(pot)} — everyone else folded", "win")
        self._close_hand(payouts, FOLD_WIN_SECONDS)

    def _showdown(self) -> None:
        self.actor = ""
        for st in self.state.values():
            st.bet = 0
        refund = self._return_uncalled()
        live = self._live()
        # Chia 2 lần: mỗi pot (chính lẫn phụ) tách làm hai nửa, nửa đầu xử theo
        # bàn 1, nửa sau theo bàn 2. Thắng cả hai bàn thì ăn cả pot, mỗi người
        # thắng một bàn thì chia đôi — tự nhiên rơi ra từ cách tính này, kể cả
        # với 3+ người và nhiều pot phụ.
        boards = [self.board1, self.board] if self.rit else [self.board]
        runs = [{s: best_hand([c.as_tuple() for c in self.state[s].hole + board])
                 for s in live} for board in boards]
        payouts: dict[str, int] = {}
        pot_results = []
        for index, pot in enumerate(self._build_pots(live)):
            name = "Main pot" if index == 0 else f"Side pot {index}"
            halves = ([pot["amount"] - pot["amount"] // 2, pot["amount"] // 2]
                      if self.rit else [pot["amount"]])
            for run_index, amount in enumerate(halves):
                scores = runs[run_index]
                eligible = [s for s in pot["eligible"] if s in scores] or live
                best = max(scores[s].key() for s in eligible)
                winners = sorted((s for s in eligible if scores[s].key() == best),
                                 key=self._left_of_button)
                share, odd = divmod(amount, len(winners))
                for i, seat in enumerate(winners):
                    payouts[seat] = payouts.get(seat, 0) + share + (1 if i < odd else 0)
                pot_results.append({
                    "name": name + (f" · Run {run_index + 1}" if self.rit else ""),
                    "run": run_index + 1,
                    "amount": amount, "winners": winners,
                    "label": describe(scores[winners[0]]),
                })
        for seat, amount in payouts.items():
            self.state[seat].chips += amount

        hands = {}
        for seat in live:
            hands[seat] = {"label": describe(runs[0][seat]),
                           "best": [Card(*c).to_json() for c in runs[0][seat].cards]}
            if self.rit:
                hands[seat]["label2"] = describe(runs[1][seat])
                hands[seat]["best2"] = [Card(*c).to_json() for c in runs[1][seat].cards]
        winners_all = []
        for pot in pot_results:
            for seat in pot["winners"]:
                if seat not in winners_all:
                    winners_all.append(seat)
        self.result = {"showdown": True, "rit": self.rit, "winners": winners_all,
                       "payouts": payouts, "refund": refund, "pots": pot_results,
                       "hands": hands}
        for seat in live:
            tail = hands[seat]["label"]
            if self.rit:
                tail = f"Run 1: {tail} · Run 2: {hands[seat]['label2']}"
            self._note(f"{self._name(seat)}: "
                       + " ".join(c.to_json()["label"] for c in self.state[seat].hole)
                       + f" — {tail}", "showdown")
        for pot in pot_results:
            names = ", ".join(self._name(s) for s in pot["winners"])
            self._note(f"{names} wins {pot['name']} {vn(pot['amount'])} "
                       f"with {pot['label']}", "win")
        self._close_hand(payouts, SHOWDOWN_SECONDS)

    def _close_hand(self, payouts: dict[str, int], pause: float) -> None:
        self.settled = True
        self.phase = "showdown"
        self.deadline = time.time() + pause
        self.touched = time.time()
        if payouts:
            self.winner = max(payouts, key=lambda s: payouts[s])
            for seat, amount in payouts.items():
                if amount:
                    self.scores[seat] = self.scores.get(seat, 0) + 1
        net: dict[str, int] = {}
        for seat, uid in self.hand_uids.items():
            if is_bot_uid(uid):
                continue
            delta = payouts.get(seat, 0) - self.contrib.get(seat, 0)
            if uid and delta:
                net[uid] = net.get(uid, 0) + delta
        if net and callable(self.on_hand_end):
            try:
                self.on_hand_end(net)
            except Exception:       # ghi bảng xếp hạng lỗi không được phá ván
                pass

    def _timeout(self) -> None:
        seat = self.actor
        if not seat or not self.state[seat].live:
            self._end_street()
            return
        st = self.state[seat]
        st.timeouts += 1
        player = self.seat(seat)
        if st.bet >= self.current_bet:
            self._note(f"{self._name(seat)} timed out — auto check", "timeout")
            self._done(seat, "check")
        else:
            self._fold_seat(seat, "timed out")
        # Giải đấu KHÔNG chuyển sang tạm nghỉ: treo máy thì cứ để mù ăn tới khi
        # hết chip và bị loại, nếu không giải sẽ đứng mãi.
        if self.tournament:
            return
        if st.timeouts >= TIMEOUTS_TO_SITOUT or (player is not None and not player.connected):
            if not st.sitting_out:
                st.sitting_out = True
                self.system(f"{self._name(seat)} treo máy — chuyển sang Sit out.")

    # ======================================================================
    # đồng hồ — Hub gọi mỗi 0.35 giây
    # ======================================================================
    def tick(self) -> bool:
        now = time.time()
        # Giải đấu đang chờ người mất kết nối quay lại: hết hạn thì chốt loại
        # ngay, không đợi ván sau (vì không có ván nào đang chạy để đợi).
        if (self.tournament and self.tstage == "running" and self.phase == "idle"
                and any(now >= limit for limit in self.out_deadline.values())):
            self._deal_hand()
            return True
        if self.phase == "starting":
            if now < self.start_at:
                return False
            self.start_at = 0.0
            self._deal_hand()
            return True
        if self.status != "playing" or now < self.deadline:
            return False
        if self.phase == "betting":
            self._timeout()
            return True
        if self.phase == "ritvote":
            missing = [s for s, v in self.rit_votes.items() if v is None]
            if missing:
                self._note("Hết giờ bỏ phiếu ("
                           + ", ".join(self._name(s) for s in missing) + " chưa chọn).", "")
            self._start_runout(False)
            return True
        if self.phase == "runout":
            self._runout_step()
            return True
        if self.phase == "showdown":
            self._deal_hand()
            return True
        return False

    def progress_token(self) -> tuple:
        return (self.status, self.phase, self.street, self.hand_no, self.actor)

    # ======================================================================
    # trạng thái gửi cho client
    # ======================================================================
    def _seat_info(self, mark: str) -> dict | None:
        info = super()._seat_info(mark)
        if info is None:
            return None
        player = self.seat(mark)
        st = self.state[mark]
        info.update({
            "avatar": self.avatar_for(player.uid) if callable(self.avatar_for) else None,
            "chips": st.chips,
            "bet": st.bet,
            "invested": self.contrib.get(mark, 0),
            "dealt": st.dealt,
            "live": st.live,
            "folded": st.folded,
            "allIn": st.all_in,
            "action": st.action,
            "actionAmount": st.action_amount,
            "sittingOut": st.sitting_out,
            "leaving": st.leaving,
            "eliminated": st.eliminated,
            "place": st.place,
            "host": bool(self.host_uid) and player.uid == self.host_uid,
            "outAt": self.out_deadline.get(mark, 0.0),
            "cards": len(st.hole) if st.live else 0,
            "queue": [{"name": self.players[u].name, "color": self.players[u].color}
                      for u in self.queue[mark] if u in self.players],
        })
        return info

    def _shown_cards(self) -> dict[str, list[dict]]:
        """Bài lật ngửa: CHỈ lúc showdown thật, lúc cả bàn all-in chạy bài, hoặc
        người thắng tự khoe. Không bao giờ trong lúc còn cược."""
        shown = {}
        for seat in self.SEATS:
            if self._is_revealed(seat):
                shown[seat] = [c.to_json() for c in self.state[seat].hole]
        return shown

    def _is_revealed(self, seat: str) -> bool:
        """Bài của ghế này có đang lật ngửa cho cả bàn không.

        - Tất tay (bỏ phiếu / chạy bài) hoặc showdown thật: bài của người còn
          trong ván tự lật.
        - Hết ván: AI ĐƯỢC CHIA BÀI cũng có thể tự khoe — kể cả người đã bỏ bài
          hay thua — bằng nút "Khoe bài" (``shown``).
        Trong lúc còn cược thì không bao giờ lộ bài ai.
        """
        st = self.state[seat]
        if not st.dealt or not st.hole:
            return False
        if st.live and self.phase in ("ritvote", "runout"):
            return True
        if self.phase != "showdown":
            return False
        if st.shown:
            return True
        return st.live and bool(self.result and self.result.get("showdown"))

    def _tourney_view(self, uid: str) -> dict:
        """Phần trạng thái riêng của chế độ giải đấu."""
        player = self.players.get(uid)
        seat = player.mark if player else ""
        ready = [s for s in self.SEATS if self._ready(s)]
        host = self.players.get(self.host_uid)
        next_level = 0
        if self.tstage == "running" and self.hand_no:
            next_level = TOURNEY_LEVEL_HANDS - (self.hand_no - 1) % TOURNEY_LEVEL_HANDS
        return {
            "stage": self.tstage,                   # lobby | running | done
            "seatsTotal": len(self.SEATS),
            "registered": sum(1 for s in self.SEATS if self.seat(s) is not None),
            "ready": len(ready),
            "minPlayers": TOURNEY_MIN_PLAYERS,
            "alive": len(self._alive_seats()),
            "isHost": bool(uid) and uid == self.host_uid,
            "hostName": host.name if host else "",
            "canStart": (bool(uid) and uid == self.host_uid
                         and (self.tstage == "done"
                              or (self.tstage == "lobby"
                                  and len(ready) >= TOURNEY_MIN_PLAYERS))),
            "level": self.level + 1,
            "levelCount": len(TOURNEY_BLINDS),
            "levelHands": TOURNEY_LEVEL_HANDS,
            "nextLevelIn": next_level,
            "graceSeconds": TOURNEY_DISCONNECT_GRACE,
            "placements": list(self.placements),
            "champion": self.winner if self.tstage == "done" else "",
            # Khán giả "bị khoá": vào sau giờ chốt danh sách hoặc đã bị loại,
            # không có đường nào ngồi vào bàn nữa.
            "locked": bool(not seat and (self.tstage != "lobby"
                                         or uid in self.out_uids)),
        }

    def summary(self) -> dict:
        data = super().summary()
        data["tournament"] = self.tournament
        if self.tournament:
            data["stage"] = self.tstage
            data["alive"] = len(self._alive_seats())
            if self.tstage != "lobby":
                data["openSeats"] = 0       # giải đã chốt danh sách: chỉ vào xem
        return data

    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        seat = player.mark if player else ""
        st = self.state.get(seat) if seat else None

        me = {"seat": seat,
              "queuedFor": [s for s in self.SEATS if uid in self.queue[s]],
              "eliminated": bool(st is not None and st.eliminated),
              "place": st.place if st is not None else 0}
        if st is not None:
            hole = [c.as_tuple() for c in st.hole] if st.dealt else []
            me.update({
                "chips": st.chips, "dealt": st.dealt, "live": st.live,
                "folded": st.folded, "allIn": st.all_in,
                "sittingOut": st.sitting_out, "leaving": st.leaving,
                "hole": [c.to_json() for c in st.hole] if st.dealt else [],
                "handLabel": describe_cards(hole, [c.as_tuple() for c in self.board])
                if hole else "",
                "canShow": (self.phase == "showdown" and st.dealt and bool(st.hole)
                            and not self._is_revealed(seat)),
                "ritVote": self.rit_votes.get(seat) if self.phase == "ritvote" else None,
                "canVoteRit": (self.phase == "ritvote" and seat in self.rit_votes
                               and self.rit_votes[seat] is None),
            })

        act = None
        if seat and self.phase == "betting" and self.actor == seat:
            act = self._action_options(seat)

        live = self._live()
        side_pots = []
        if any(self.state[s].all_in for s in live):
            side_pots = [{"amount": p["amount"], "seats": p["eligible"]}
                         for p in self._build_pots(live)]

        return {
            "phase": self.phase,
            "street": self.street,
            "streetName": STREET_NAME.get(self.street, self.street),
            "deadline": self.start_at if self.phase == "starting" else self.deadline,
            "now": time.time(),
            "actionSeconds": ACTION_SECONDS,
            "actor": self.actor,
            "currentBet": self.current_bet,
            "button": self.button if self.status == "playing" else "",
            "sbSeat": self.sb_seat if self.status == "playing" else "",
            "bbSeat": self.bb_seat if self.status == "playing" else "",
            "board": [c.to_json() for c in self.board],
            # Chia 2 lần: bàn thứ nhất đã chạy xong (bàn đang chạy là "board").
            "board1": [c.to_json() for c in self.board1] if self.rit and self.board1 else [],
            "rit": {
                "voting": self.phase == "ritvote",
                "twice": self.rit,
                "run": self.run_no,
                "votes": dict(self.rit_votes),
            },
            "pot": self.pot_total(),
            "sidePots": side_pots if len(side_pots) > 1 else [],
            "handNo": self.hand_no,
            "blinds": {"sb": self.sb, "bb": self.bb},
            "chipStart": CHIP_START,
            "tournament": self._tourney_view(uid) if self.tournament else None,
            "me": me,
            "act": act,
            "shown": self._shown_cards(),
            "result": self.result if self.phase == "showdown" else None,
            "feed": self.feed[-40:],
            "taunts": list(TAUNTS),
        }
