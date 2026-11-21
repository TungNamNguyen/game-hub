"""Luật game "Sòng Bịp" — đặt úp quân rồi nói dối, bị bắt bài thì xoay ổ đạn.

Bàn 2-4 người. Mỗi VÒNG lộ một QUÂN CHỦ (Rồng / Phượng / Hổ) và chia lại 5 quân
cho mỗi người còn sống. Tới lượt, người chơi đặt ÚP 1-3 quân rồi khai "n con
<quân chủ>". Khai gì là quyền của họ — thật hay bịp không ai biết.

Người kế tiếp chọn một trong hai:
  - tin, rồi đặt tiếp lượt của mình;
  - hô BỊP, lật ĐÚNG những quân của lượt vừa rồi (không lật tay ai).

Xử lý khi hô BỊP:
  - có ít nhất một quân không phải quân chủ  -> người đặt đã bịp, HỌ bắn;
  - tất cả đều là quân chủ                    -> người hô sai, NGƯỜI HÔ bắn.
Quân Quỷ luôn được tính là quân chủ, bất kể quân chủ vòng đó là gì.

CHẾ ĐỘ MA VƯƠNG (các mode có hậu tố "d"). Đầu mỗi vòng, đúng MỘT quân chủ bị
hoá thành quân Ma Vương — nó CHIẾM CHỖ quân đó, bộ vẫn đúng 20 quân:

    quân chủ = Phượng  ->  6 Rồng · 5 Phượng · 6 Hổ · 2 Quỷ · 1 Ma Vương

Ma Vương KHÔNG phải quân thật, và phải đặt MỘT MÌNH (không ghép với quân nào).
Bù lại, bị hô bịp mà lật ra Ma Vương thì người đặt SẠCH, còn NGƯỜI HÔ cùng MỌI
người còn quân trên tay đều phải bắn. Đó là cú phản đòn mạnh nhất của game.
Bàn còn hai người thì Ma Vương không xuất hiện (xem ``DEVIL_MIN_ALIVE``).

Súng: mỗi người một khẩu 6 ổ, đúng 1 ổ có đạn. Xáo MỘT LẦN lúc vào ván và
KHÔNG BAO GIỜ xáo lại. Mỗi lần bắn lật ổ kế tiếp; ổ rỗng dùng rồi là mất, nên
càng bắn nhiều lần càng dễ chết: 1/6 -> 1/5 -> 1/4 -> 1/3 -> 1/2 -> chắc chết.

Một VÁN gồm nhiều VÒNG. Vòng kết thúc ngay sau khi người thua cuộc đối chất đã
bắn. Còn đúng một người sống thì người đó thắng cả ván.

CHE THÔNG TIN — phần sống còn của một game bịp. ``match_view`` chỉ gửi:
  - tay quân của CHÍNH người nhận (không bao giờ của người khác);
  - số lượng quân trong mỗi lượt đã đặt, KHÔNG gửi mặt quân;
  - mặt quân của đúng lượt bị hô bịp, và chỉ từ lúc hô trở đi.
Khán giả bị che y như người chơi, vì họ mách nước được qua chat.

DIỄN BIẾN CÓ ĐỘ TRỄ. Phần lật quân và xoay ổ đạn chia thành các pha có mốc thời
gian (``deadline``) để client kịp chạy animation, và hub gọi ``tick()`` để đẩy
pha. Kết quả phát súng chỉ được ĐƯA VÀO payload ở pha "shot" — pha "aim" trước
đó không chứa nó, nên mở DevTools cũng không biết trước mình sống hay chết.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from games import GameError, Player, SeatedRoom

# --------------------------------------------------------------------------- #
# quân và bộ quân
# --------------------------------------------------------------------------- #
DRAGON = "DRAGON"
PHOENIX = "PHOENIX"
TIGER = "TIGER"
DEMON = "DEMON"                 # quân Quỷ: luôn tính là quân chủ
DEVIL = "DEVIL"                 # quân Ma Vương: chỉ có ở chế độ Ma Vương

#: Quân có thể được rút làm quân chủ của vòng. Quỷ và Ma Vương KHÔNG nằm ở đây.
TABLE_RANKS = (DRAGON, PHOENIX, TIGER)

RANK_NAME = {DRAGON: "Rồng", PHOENIX: "Phượng", TIGER: "Hổ", DEMON: "Quỷ",
             DEVIL: "Ma Vương"}

#: Bộ 20 quân, đúng theo đặc tả: 6 + 6 + 6 + 2.
DECK_COUNT = {DRAGON: 6, PHOENIX: 6, TIGER: 6, DEMON: 2}
DECK_SIZE = sum(DECK_COUNT.values())

#: Số người còn sống tối thiểu để Ma Vương xuất hiện trong vòng.
#:
#: Dưới ngưỡng này (tay đôi) Ma Vương vô nghĩa: nó bị lật thì chỉ có người hô
#: bắn, y như khi lật một quân chủ thật, mà lại KHÔNG ghép được vào lượt 2-3
#: quân. Tức là nó biến thành một quân chủ bị què. Nên bàn còn hai người thì bộ
#: quân quay về bộ gốc 6/6/6/2.
DEVIL_MIN_ALIVE = 3

HAND_SIZE = 5
MIN_PLAY = 1
MAX_PLAY = 3

CHAMBERS = 6
LIVE_ROUNDS = 1                 # số ổ có đạn trong 6 ổ

# ---- mốc thời gian của từng pha (giây) ------------------------------------- #
TURN_SECONDS = 30.0             # đặc tả: mỗi lượt tối đa 30 giây
AWAY_TURN_SECONDS = 6.0         # rút ngắn thời gian chờ khi người giữ lượt bị mất kết nối
REVEAL_SECONDS = 3.0            # thời gian tối thiểu lật quân của lượt bị hô bịp
REVEAL_STEP_SECONDS = 0.6       # khoảng cách lật từng lá một (giây)
AIM_SECONDS = 3.4               # kề súng, xoay ổ đạn
BLANK_SECONDS = 2.6             # ổ rỗng: thở phào
DEATH_SECONDS = 4.4             # ổ có đạn: cần lâu hơn cho animation chết

TAUNT_TTL = 4.5
TAUNTS = (
    "Bịp chắc luôn!",
    "Run tay rồi kìa 😏",
    "Thật không đấy?",
    "Dám hô không!",
    "Quá non!",
    "Cược cả mạng nào 💀",
)

FEED_MAX = 60

#: Tên nhân vật cho máy. Đặt tên riêng thay vì "Máy 1/2/3" để bàn có không khí
#: sòng bài, và để người chơi nhớ được "thằng nào hay bịp".
BOT_NAMES = ("Tư Lì", "Cô Ba", "Lão Sáu", "Út Nhỏ")


def is_truth(rank: str, table_rank: str) -> bool:
    """Quân này có đúng như lời khai không. Quỷ luôn đúng.

    Ma Vương KHÔNG phải quân thật, dù nó sinh ra từ đúng quân chủ của vòng: nó
    là một quân riêng với hiệu ứng riêng (xem ``devil_losers``). Hàm này trả về
    False cho nó, nhưng ĐỪNG dùng một mình để phân xử đối chất — phải hỏi
    ``DEVIL in ranks`` trước, vì lật ra Ma Vương thì người bị hô lại là người
    thắng chứ không phải người thua.
    """
    return rank == table_rank or rank == DEMON


def resolve_claim(ranks, table_rank: str) -> bool:
    """True nếu lời khai THẬT (mọi quân đều hợp). Một quân sai là bịp.

    Chỉ dùng cho lượt KHÔNG chứa Ma Vương.
    """
    return all(is_truth(rank, table_rank) for rank in ranks)


def deck_count_for(devil_rank: str = "") -> dict[str, int]:
    """Thành phần bộ quân của một vòng. Tổng LUÔN là 20.

    Ma Vương không được cộng thêm vào bộ: nó CHIẾM CHỖ đúng một quân chủ. Quân
    chủ là Phượng thì bộ thành 6 Rồng / 5 Phượng / 6 Hổ / 2 Quỷ / 1 Ma Vương.
    """
    counts = dict(DECK_COUNT)
    if devil_rank:
        if counts.get(devil_rank, 0) <= 0:
            raise ValueError(f"không có quân {devil_rank} để hoá Ma Vương")
        counts[devil_rank] -= 1
        counts[DEVIL] = 1
    return counts


def deck_ranks(devil_rank: str = "") -> list[str]:
    """20 mặt quân của một vòng, chưa xáo."""
    ranks = [rank for rank, count in DECK_COUNT.items() for _ in range(count)]
    if devil_rank:
        # Đổi MỘT quân chủ thành Ma Vương, không chèn thêm quân nào.
        ranks[ranks.index(devil_rank)] = DEVIL
    return ranks


def fresh_deck(rng: random.Random, devil_rank: str = "") -> list["Card"]:
    deck = [Card(f"c{index:02d}", rank)
            for index, rank in enumerate(deck_ranks(devil_rank), start=1)]
    rng.shuffle(deck)
    return deck


def fresh_cylinder(rng: random.Random) -> list[bool]:
    """Ổ đạn đã xáo: True là ổ có đạn. Xáo đúng một lần cho cả ván."""
    cylinder = [True] * LIVE_ROUNDS + [False] * (CHAMBERS - LIVE_ROUNDS)
    rng.shuffle(cylinder)
    return cylinder


@dataclass(frozen=True)
class Card:
    id: str
    rank: str


@dataclass
class Play:
    """Một lượt đặt quân. ``cards`` là mặt thật, chỉ lộ khi bị hô bịp."""
    seat: str
    cards: list[Card]

    @property
    def count(self) -> int:
        return len(self.cards)


@dataclass
class SeatState:
    """Phần trạng thái game gắn với GHẾ, không gắn với người.

    Tách khỏi ``Player`` có chủ ý: người bị loại vẫn phải hiện trên bàn cho tới
    hết ván, và người mất kết nối rồi F5 phải nhận lại đúng tay quân cũ.
    """
    alive: bool = True
    hand: list[Card] = field(default_factory=list)
    cylinder: list[bool] = field(default_factory=list)
    shots: int = 0                      # số lần đã bắn -> cũng là ổ kế tiếp
    cause: str = ""                     # vì sao bị loại, để hiện trên bàn

    def chambers_left(self) -> int:
        return max(0, len(self.cylinder) - self.shots)

    def death_odds(self) -> float:
        """Xác suất chết ở phát kế tiếp. Công khai được vì ai cũng đếm được số
        lần từng người đã bắn."""
        left = self.chambers_left()
        if left <= 0:
            return 1.0
        live = sum(1 for loaded in self.cylinder[self.shots:] if loaded)
        return live / left


# --------------------------------------------------------------------------- #
# phòng
# --------------------------------------------------------------------------- #
class BluffRoom(SeatedRoom):
    CHANNEL = "bluff"
    START_STATUS = "playing"
    HAS_CLOCK = True                    # cần hub gọi tick() để đẩy pha
    DEFAULT_MODE = "p4"
    #: Chế độ Ma Vương là một BIẾN THỂ của từng kiểu bàn, không phải kiểu bàn
    #: riêng, nên mỗi số ghế có hai mục. Không có "p2d": bàn hai người thì Ma
    #: Vương không bao giờ xuất hiện (xem DEVIL_MIN_ALIVE) nên mục đó sẽ lừa
    #: người chọn.
    MODES = {
        "p4": {"label": "Bàn 4 người", "seats": 4},
        "p3": {"label": "Bàn 3 người", "seats": 3},
        "p2": {"label": "Tay đôi (2 người)", "seats": 2},
        "p4d": {"label": "Bàn 4 người · Ma Vương", "seats": 4, "devil": True},
        "p3d": {"label": "Bàn 3 người · Ma Vương", "seats": 3, "devil": True},
    }

    @classmethod
    def seats_for(cls, mode: str) -> tuple[str, ...]:
        count = cls.MODES.get(mode, {}).get("seats", 4)
        return tuple(f"P{i + 1}" for i in range(count))

    @property
    def devil_mode(self) -> bool:
        """Phòng này có bật Ma Vương không. Khác ``devil_rank``: cái đó là "vòng
        NÀY có Ma Vương trong bộ không"."""
        return bool(self.MODES.get(self.mode, {}).get("devil"))

    def __init__(self, code: str, mode: str = "") -> None:
        self.rng = random.Random()
        super().__init__(code, mode)
        self.reset_match()

    # ---- vòng đời ván ------------------------------------------------------ #
    def reset_match(self) -> None:
        """Dọn cho VÁN mới: ai cũng sống lại, súng được xáo lại từ đầu."""
        self.state: dict[str, SeatState] = {
            seat: SeatState(cylinder=fresh_cylinder(self.rng)) for seat in self.SEATS
        }
        self.round_no = 0
        self.phase = "turn"             # turn | reveal | aim | shot | over
        self.table_rank = TABLE_RANKS[0]
        #: Quân chủ đã bị hoá Ma Vương ở vòng này, "" nếu vòng này không có.
        self.devil_rank = ""
        #: Thành phần bộ quân của vòng này. Công khai được: ai cũng đếm được.
        self.deck_count: dict[str, int] = deck_count_for()
        self.turn = ""
        self.forced_liar = False
        self.deadline = 0.0
        self.pile: list[Play] = []
        self.last_play: Play | None = None
        self.challenge: dict | None = None
        self.shot: dict | None = None
        #: Hàng người còn phải bắn ở lượt đối chất này. Thường chỉ một người,
        #: nhưng lật ra Ma Vương thì cả bàn (trừ người đặt) vào hàng.
        self.shot_queue: list[str] = []
        #: Người đang bị kề súng ở pha "aim"/"shot".
        self.firing = ""
        self.feed: list[dict] = []

    def on_match_start(self) -> None:
        self.system(f"Vào ván. Bàn {len(self.SEATS)} người, mỗi người một khẩu 6 ổ.")
        if self.devil_mode:
            self.system(f"Chế độ {RANK_NAME[DEVIL]}: mỗi vòng có một quân "
                        f"{RANK_NAME[DEVIL]} trộn trong bộ.")
        self._start_round(self.rng.choice(self.alive_seats()))

    # ---- tra cứu ----------------------------------------------------------- #
    def alive_seats(self) -> list[str]:
        return [seat for seat in self.SEATS if self.state[seat].alive]

    def seats_with_cards(self) -> list[str]:
        return [seat for seat in self.SEATS
                if self.state[seat].alive and self.state[seat].hand]

    def _seat_index(self, seat: str) -> int:
        return self.SEATS.index(seat) if seat in self.SEATS else 0

    def _next_alive(self, seat: str) -> str:
        """Người sống kế tiếp theo vòng bàn, có thể là chính ``seat``."""
        start = self._seat_index(seat)
        for step in range(1, len(self.SEATS) + 1):
            candidate = self.SEATS[(start + step) % len(self.SEATS)]
            if self.state[candidate].alive:
                return candidate
        return seat

    def _next_actor(self, seat: str) -> str:
        """Người kế tiếp ĐƯỢC ĐI: còn sống và còn quân trên tay.

        Người hết quân bị bỏ lượt tới hết vòng (đặc tả §6). Có thể trả về chính
        ``seat`` nếu cả bàn chỉ còn họ có quân. Trả "" nếu không còn ai có quân.
        """
        start = self._seat_index(seat)
        for step in range(1, len(self.SEATS) + 1):
            candidate = self.SEATS[(start + step) % len(self.SEATS)]
            state = self.state[candidate]
            if state.alive and state.hand:
                return candidate
        return ""

    def _note(self, text: str, tone: str = "") -> None:
        self.feed.append({"text": text, "tone": tone, "ts": time.time()})
        del self.feed[:-FEED_MAX]

    def _name(self, seat: str) -> str:
        player = self.seat(seat)
        return player.name if player else self._seat_label(seat)

    # ---- bắt đầu vòng ------------------------------------------------------ #
    def _start_round(self, first_seat: str) -> None:
        """Chia lại bàn: quân chủ mới, xáo lại 20 quân, mỗi người 5 quân.

        Súng KHÔNG bị chạm tới ở đây — ổ đạn sống qua mọi vòng, đó là toàn bộ
        sức nặng của game.
        """
        alive = self.alive_seats()
        if len(alive) <= 1:
            self._end_game()
            return

        self.round_no += 1
        self.table_rank = self.rng.choice(TABLE_RANKS)
        # Ma Vương luôn sinh ra từ ĐÚNG quân chủ của vòng, và chiếm chỗ nó: bộ
        # vẫn 20 quân, chỉ bớt đi một quân chủ.
        self.devil_rank = (self.table_rank
                           if self.devil_mode and len(alive) >= DEVIL_MIN_ALIVE
                           else "")
        self.deck_count = deck_count_for(self.devil_rank)
        deck = fresh_deck(self.rng, self.devil_rank)
        for seat in self.SEATS:
            state = self.state[seat]
            state.hand = [deck.pop() for _ in range(HAND_SIZE)] if state.alive else []
        # Quân còn lại trong bộ KHÔNG được chia và không ai được biết (đặc tả
        # §5 bước 3): bàn 2-3 người thì luôn còn quân treo, và chính chỗ mờ đó
        # làm việc đếm quân khó hơn. Ở chế độ Ma Vương, chỗ mờ này còn nặng hơn:
        # bàn 3 người thì 5 quân bị treo, nên Ma Vương có thể không đến tay ai.

        self.pile = []
        self.last_play = None
        self.challenge = None
        self.shot = None
        self.shot_queue = []
        self.firing = ""
        if first_seat not in alive:
            first_seat = self._next_alive(first_seat)
        self._begin_turn(first_seat)
        self._note(f"Vòng {self.round_no} — quân chủ là {RANK_NAME[self.table_rank]}.",
                   "round")
        if self.devil_rank:
            self._note(f"Một con {RANK_NAME[self.devil_rank]} đã hoá "
                       f"{RANK_NAME[DEVIL]} và đang trốn đâu đó trong bộ.", "devil")
        self.touched = time.time()

    def _turn_seconds(self, seat: str) -> float:
        p = self.seat(seat)
        if p is not None and not p.bot and not p.connected:
            return AWAY_TURN_SECONDS
        return TURN_SECONDS

    def disconnect(self, uid: str) -> None:
        super().disconnect(uid)
        if self.in_progress() and self.phase == "turn" and self.turn:
            p = self.seat(self.turn)
            if p is not None and not p.bot and not p.connected:
                self.deadline = min(self.deadline, time.time() + AWAY_TURN_SECONDS)

    def _begin_turn(self, seat: str) -> None:
        self.phase = "turn"
        self.turn = seat
        self.shot = None
        self.challenge = None
        # Còn đúng một người có quân, và người đó KHÔNG phải người vừa đặt:
        # họ không còn ai để đặt tiếp cho nên buộc phải hô bịp (đặc tả §6).
        with_cards = self.seats_with_cards()
        self.forced_liar = (
            len(with_cards) == 1
            and with_cards[0] == seat
            and self.last_play is not None
            and self.last_play.seat != seat
        )
        self.deadline = time.time() + self._turn_seconds(seat)

    def _advance_turn(self) -> None:
        nxt = self._next_actor(self.turn)
        if not nxt:
            # Cả bàn hết quân mà chưa ai hô bịp. Chỉ xảy ra khi người duy nhất
            # còn quân lại chính là người vừa đặt (không được tự hô bịp chính
            # mình) nên họ phải đặt tới hết tay. Không ai phải bắn: xử bàn trắng
            # rồi chia lại, còn hơn để phòng treo vĩnh viễn.
            self._note("Cả bàn hết quân, không ai bị bắt bài. Bàn trắng, chia lại.",
                       "void")
            self.system("Bàn trắng — cả bàn hết quân mà không ai hô bịp.")
            self._start_round(self._next_alive(self.turn))
            return
        self._begin_turn(nxt)

    # ---- hành động của người chơi ------------------------------------------ #
    def handle(self, uid: str, action: str, msg: dict) -> None:
        if action == "play":
            raw = msg.get("cards") or []
            if not isinstance(raw, list):
                raise GameError("Dữ liệu quân không hợp lệ.")
            self.play(uid, [str(item) for item in raw])
        elif action == "liar":
            self.call_liar(uid)
        elif action == "taunt":
            self.taunt(uid, str(msg.get("text", "")))
        else:
            raise GameError("Hành động không hợp lệ.")

    def taunt(self, uid: str, text: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        if text not in TAUNTS:
            raise GameError("Câu cà khịa không hợp lệ.")
        if not hasattr(self, "taunts"):
            self.taunts = {}
        now = time.time()
        prev = self.taunts.get(player.mark)
        if prev and now - prev["ts"] < 1.5:
            return
        self._taunt_seq = getattr(self, "_taunt_seq", 0) + 1
        self.taunts[player.mark] = {"id": self._taunt_seq, "text": text, "ts": now}
        self.touched = now

    def _actor(self, uid: str) -> tuple[str, SeatState]:
        """Kiểm tra chung cho cả hai hành động: đúng người, đúng lúc."""
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn đang xem thôi, không chơi được.")
        if self.status != "playing":
            raise GameError("Ván chưa bắt đầu.")
        if self.phase != "turn":
            raise GameError("Đang xử lý lượt trước, chờ một chút.")
        state = self.state[player.mark]
        if not state.alive:
            raise GameError("Bạn đã bị loại khỏi ván này.")
        if self.turn != player.mark:
            raise GameError("Chưa tới lượt bạn.")
        return player.mark, state

    def play(self, uid: str, card_ids: list[str]) -> None:
        seat, state = self._actor(uid)
        if self.forced_liar:
            raise GameError("Bạn là người duy nhất còn quân — phải hô bịp.")
        if not MIN_PLAY <= len(card_ids) <= MAX_PLAY:
            raise GameError(f"Mỗi lượt đặt {MIN_PLAY}-{MAX_PLAY} quân.")
        if len(set(card_ids)) != len(card_ids):
            raise GameError("Không đặt trùng một quân hai lần.")

        by_id = {card.id: card for card in state.hand}
        chosen: list[Card] = []
        for card_id in card_ids:
            card = by_id.get(card_id)
            if card is None:
                raise GameError("Quân đó không có trong tay bạn.")
            chosen.append(card)

        # Ma Vương phải đặt MỘT MÌNH. Giữ nó chung với quân khác trên tay thì
        # được — hạn chế này chỉ áp lúc chọn quân để đặt.
        if len(chosen) > 1 and any(card.rank == DEVIL for card in chosen):
            raise GameError(f"{RANK_NAME[DEVIL]} phải đặt một mình, "
                            f"không ghép với quân nào.")

        picked = {card.id for card in chosen}
        state.hand = [card for card in state.hand if card.id not in picked]

        play = Play(seat=seat, cards=chosen)
        self.pile.append(play)
        self.last_play = play
        self._note(f"{self._name(seat)} đặt {play.count} con "
                   f"{RANK_NAME[self.table_rank]}.", "play")
        self.touched = time.time()
        self._advance_turn()

    def call_liar(self, uid: str) -> None:
        seat, _state = self._actor(uid)
        if self.last_play is None:
            raise GameError("Chưa có ai đặt quân để mà hô.")
        if self.last_play.seat == seat:
            raise GameError("Không hô bịp chính mình được.")

        accused = self.last_play.seat
        ranks = [card.rank for card in self.last_play.cards]
        devil = DEVIL in ranks

        if devil:
            # Ma Vương đảo ngược mọi thứ: người bị hô sạch, người hô CÙNG cả
            # bàn còn quân đều phải bắn. "Bịp hay thật" không còn ý nghĩa ở đây.
            truthful = False
            caught_lie = False
            losers = self.devil_losers(seat, accused)
        else:
            truthful = resolve_claim(ranks, self.table_rank)
            caught_lie = not truthful
            losers = [seat] if truthful else [accused]

        self.challenge = {
            "caller": seat,
            "accused": accused,
            "cards": [{"id": card.id, "rank": card.rank,
                       "truth": is_truth(card.rank, self.table_rank),
                       "devil": card.rank == DEVIL}
                      for card in self.last_play.cards],
            "truthful": truthful,
            "devil": devil,
            # ``loser`` giữ lại cho phần cũ chỉ cần biết "ai bắn đầu tiên";
            # ``losers`` là danh sách đầy đủ, theo thứ tự bắn.
            "loser": losers[0] if losers else "",
            "losers": list(losers),
            # Chỉ khi bị bắt BỊP thì người đặt mới mở vòng sau. Lật ra Ma Vương
            # thì họ không bịp gì cả, nên lượt đi theo thứ tự bàn.
            "caughtLie": caught_lie,
        }
        self.shot_queue = list(losers)
        self.firing = ""
        self.phase = "reveal"
        reveal_dur = max(REVEAL_SECONDS, 1.8 + REVEAL_STEP_SECONDS * len(self.last_play.cards))
        self.deadline = time.time() + reveal_dur
        self.turn = ""
        self.forced_liar = False

        self._note(f"{self._name(seat)} hô BỊP {self._name(accused)}!", "liar")
        if devil:
            self._note(f"Lật ra {RANK_NAME[DEVIL]}! {self._name(accused)} sạch — "
                       f"{', '.join(self._name(s) for s in losers)} phải bắn.",
                       "devil")
        elif truthful:
            self._note(f"Lật ra: đúng {len(ranks)} con {RANK_NAME[self.table_rank]}. "
                       f"{self._name(seat)} hô sai.", "truth")
        else:
            wrong = [RANK_NAME[r] for r in ranks if not is_truth(r, self.table_rank)]
            self._note(f"Lật ra có {', '.join(wrong)} — {self._name(accused)} bịp!",
                       "lie")
        self.touched = time.time()

    def devil_losers(self, caller: str, accused: str) -> list[str]:
        """Ai phải bắn khi lật ra Ma Vương.

        Người hô, cộng MỌI người còn sống mà còn quân trên tay — trừ chính người
        đã đặt Ma Vương. Người đã hết quân trong vòng này thoát, vì họ không còn
        can dự gì vào vòng nữa.

        Thứ tự bắt đầu từ người hô: họ là người bấm nút, nên họ lãnh đạn trước.
        """
        order = list(self.SEATS)
        start = order.index(caller) if caller in order else 0
        ring = [order[(start + step) % len(order)] for step in range(len(order))]
        shooters = []
        for seat in ring:
            if seat == accused:
                continue
            state = self.state[seat]
            if not state.alive:
                continue
            # Người hô luôn bắn, kể cả khi vừa hết quân.
            if seat == caller or state.hand:
                shooters.append(seat)
        return shooters

    # ---- hết giờ ----------------------------------------------------------- #
    def _timeout(self) -> None:
        """Hết 30 giây. Hình phạt là thông số thiết kế (đặc tả §20); ở đây chọn
        cách nhẹ nhất mà vẫn đẩy được ván đi: tự đặt MỘT quân ngẫu nhiên.

        Cố ý không chọn quân "an toàn" giúp người chơi: để máy tự khai thật hộ
        thì bỏ lượt lại thành có lợi, người ta sẽ cố tình treo lượt.
        """
        seat = self.turn
        if not seat or not self.state[seat].alive:
            self._advance_turn()
            return
        if self.forced_liar:
            self._note(f"{self._name(seat)} hết giờ — tự hô bịp.", "timeout")
            player = self.seat(seat)
            if player is not None:
                self.call_liar(player.uid)
            else:
                self._advance_turn()
            return

        state = self.state[seat]
        if not state.hand:
            self._advance_turn()
            return
        card = self.rng.choice(state.hand)
        self._note(f"{self._name(seat)} hết giờ — tự đặt 1 quân.", "timeout")
        state.hand = [item for item in state.hand if item.id != card.id]
        play = Play(seat=seat, cards=[card])
        self.pile.append(play)
        self.last_play = play
        self._advance_turn()

    # ---- ổ đạn ------------------------------------------------------------- #
    def _begin_aim(self) -> None:
        """Đưa người kế tiếp trong hàng vào tầm súng, hoặc chốt vòng nếu hết.

        Luật gọi là "bắn cùng lúc", nhưng mỗi người một khẩu súng riêng nên thứ
        tự không đổi kết quả. Bắn LẦN LƯỢT để mỗi phát có đủ nhịp animation —
        ba khẩu nổ cùng một khung hình thì không ai kịp thấy gì.
        """
        while self.shot_queue:
            seat = self.shot_queue.pop(0)
            if not self.state[seat].alive:
                continue            # vừa chết ở phát trước, hoặc đã rời ván
            self.firing = seat
            self.shot = None
            self.phase = "aim"
            self.deadline = time.time() + AIM_SECONDS
            return
        self.firing = ""
        self.shot = None
        self._after_round()

    def _fire(self) -> None:
        """Lật ổ kế tiếp của người đang bị kề súng. Ổ rỗng thì mất luôn ổ đó."""
        target = self.firing or (self.challenge or {}).get("loser", "")
        state = self.state.get(target)
        if not target or state is None or not state.alive:
            # Người đó đã rời ván giữa lúc chờ (bỏ ván / mất ghế): không bắn ai.
            self.shot = None
            self.firing = ""
            self._after_shot()
            return

        self.firing = target
        chamber = state.shots
        loaded = state.cylinder[chamber] if chamber < len(state.cylinder) else True
        state.shots += 1
        self.shot = {
            "seat": target,
            "chamber": chamber,
            "result": "death" if loaded else "blank",
            "left": state.chambers_left(),
            "odds": round(state.death_odds(), 4),
        }
        self.phase = "shot"
        self.deadline = time.time() + (DEATH_SECONDS if loaded else BLANK_SECONDS)

        if loaded:
            self._kill(target, "trúng đạn")
            self._note(f"ĐOÀNG! {self._name(target)} trúng đạn và bị loại.", "death")
            self.system(f"{self._name(target)} trúng đạn, bị loại.")
        else:
            left = state.chambers_left()
            self._note(f"Cạch — ổ rỗng. {self._name(target)} sống, còn {left} ổ.",
                       "blank")
        waiting = [s for s in self.shot_queue if self.state[s].alive]
        if waiting:
            self._note("Còn phải bắn: "
                       + ", ".join(self._name(s) for s in waiting), "devil")
        self.touched = time.time()

    def _kill(self, seat: str, cause: str) -> None:
        state = self.state[seat]
        state.alive = False
        state.hand = []
        state.cause = cause

    def _after_shot(self) -> None:
        """Xong một phát súng: kết thúc ván, bắn tiếp, hoặc mở vòng mới."""
        if len(self.alive_seats()) <= 1:
            # Hàng đợi mất hết ý nghĩa khi ván đã có người thắng.
            self.shot_queue = []
            self.firing = ""
            self._end_game()
            return
        if self.shot_queue:
            self._begin_aim()
            return
        self.firing = ""
        self._after_round()

    def _after_round(self) -> None:
        """Hết loạt bắn của vòng: chốt ai mở vòng sau rồi chia lại bàn."""
        # Đặc tả §5 bước 4 và §30: bị bắt bài thì CHÍNH người bịp mở vòng sau
        # (nếu còn sống); hô sai thì tới người kế tiếp sau người đã đặt.
        #
        # Dùng cờ "caughtLie" chứ không phải "not truthful": lật ra Ma Vương thì
        # truthful cũng là False, nhưng người đặt không bịp gì — thưởng cho họ
        # quyền mở vòng nữa thì cú Ma Vương mạnh quá đáng.
        info = self.challenge or {}
        accused = info.get("accused", "")
        if info.get("caughtLie") and accused and self.state[accused].alive:
            first = accused
        elif accused:
            first = self._next_alive(accused)
        else:
            first = self._next_alive(self.turn or self.SEATS[0])
        self._start_round(first)

    def _end_game(self) -> None:
        alive = self.alive_seats()
        self.finish(alive[0] if len(alive) == 1 else "draw")

    # ---- ghi đè phần khung 2 ghế ------------------------------------------- #
    def finish(self, winner: str) -> None:
        """Bàn nhiều ghế: người thắng là người sống sót, không có "bên kia"."""
        self.status = "finished"
        self.winner = winner
        self.rematch.clear()
        self.phase = "over"
        self.turn = ""
        self.forced_liar = False
        self.deadline = 0.0
        self.shot_queue = []
        self.firing = ""
        if winner in self.scores:
            self.scores[winner] += 1
            self._note(f"{self._name(winner)} là người cuối cùng còn sống. Thắng!",
                       "win")
            self.system(f"{self._name(winner)} thắng ván này.")
        else:
            self.scores["draw"] += 1
            self._note("Không còn ai sống. Bàn trắng.", "void")
        self.touched = time.time()

    def resign(self, uid: str) -> None:
        """Bỏ ván = tự loại mình, không phải "nhường cho người kia thắng"."""
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        if not self.state[player.mark].alive:
            raise GameError("Bạn đã bị loại rồi.")
        self.system(f"{player.name} bỏ ván.")
        self._quit_seat(player.mark, "bỏ ván")

    def stand(self, uid: str) -> None:
        """Rời ghế. Đang chơi thì coi như bỏ ván nhưng VẪN GIỮ GHẾ.

        Khác bàn 2 ghế (ở đó rời ghế là hủy ván): bàn 4 người mà một người đi thì
        ba người còn lại vẫn chơi được, nên ván phải tiếp tục. Giữ ghế để bàn
        hiện đủ "ai đã bị loại", và để người đó F5 quay lại vẫn thấy ván.
        """
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        if self.in_progress():
            if self.state[player.mark].alive:
                self.system(f"{player.name} rời bàn giữa ván.")
                self._quit_seat(player.mark, "rời bàn")
            else:
                # Đã bị loại từ trước thì chỉ nhả ghế. KHÔNG được rơi xuống
                # super().stand(): bản đó hủy ván khi ván đang chạy, tức là một
                # người đã chết lại xoá ván của những người còn sống.
                mark, player.mark = player.mark, ""
                self.rematch.discard(mark)
                self.system(f"{player.name} rời ghế {self._seat_label(mark)}.")
            self.touched = time.time()
            return
        super().stand(uid)

    def _quit_seat(self, seat: str, cause: str) -> None:
        """Một người tự rút khỏi ván đang chạy."""
        self._kill(seat, cause)
        self._note(f"{self._name(seat)} {cause}, coi như bị loại.", "quit")
        # Loạt bắn đang treo bị bỏ luôn: bàn vừa hụt người thì lời khai cũ mất
        # nghĩa, và bắt những người còn lại bắn nốt cho một cú đối chất đã vô
        # hiệu là oan.
        self.shot_queue = []
        self.firing = ""
        if len(self.alive_seats()) <= 1:
            self._end_game()
            return
        # Mọi lời khai đang treo mất ý nghĩa khi bàn vừa hụt người giữa dòng,
        # kể cả khi người đi chính là người đang bị hô bịp. Chia lại cho sạch.
        self._start_round(self._next_alive(seat))

    # ---- máy chơi đơn ------------------------------------------------------ #
    def add_bot(self, level: str = "normal", mark: str = "") -> Player | None:
        """Lấp MỌI ghế trống bằng máy, trừ một ghế chừa cho người tạo phòng.

        ``RoomManager.solo()`` gọi hàm này đúng một lần trên phòng vừa tạo (còn
        trống hết), nên bàn 4 người sẽ có 3 máy — đủ để chơi ngay một mình.
        """
        if self.bot_players():
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        # Chừa ghế ĐẦU cho người mở phòng — nhưng CHỈ khi chưa ai ngồi. Thứ tự
        # lượt chạy P1 -> P2 -> ... nên người mở phòng được mở vòng đầu, không
        # phải ngồi xem máy đánh trước.
        #
        # Nếu đã có người ngồi thì họ đã có ghế rồi, lúc đó lấp KÍN phần còn lại
        # mới đúng ý. Bỏ điều kiện này thì gọi add_bot sau khi có người sẽ để
        # trống một ghế và bàn không bao giờ vào ván được.
        if not any(p.mark and not p.bot for p in self.players.values()):
            if len(free) < 2:
                raise GameError("Không còn ghế cho máy.")
            free = free[1:]
        if not free:
            raise GameError("Không còn ghế cho máy.")
        seated = None
        for slot, seat in enumerate(free):
            seated = self._seat_bot(seat, level, BOT_NAMES[slot % len(BOT_NAMES)],
                                    slot=slot)
        return seated

    def bot_pending(self, mark: str) -> bool:
        """Máy chỉ hành động ở pha "turn". Các pha lật quân / xoay ổ đạn do đồng
        hồ của phòng đẩy, không ai được chen vào."""
        return self.phase == "turn" and self.turn == mark

    def progress_token(self) -> tuple:
        """Dấu vết đủ mịn để phát hiện bàn đã đổi trong lúc máy đang nghĩ."""
        return (self.status, self.phase, self.turn, self.round_no, len(self.pile),
                self.firing, len(self.shot_queue),
                sum(self.state[seat].shots for seat in self.SEATS))

    # ---- đồng hồ ----------------------------------------------------------- #
    def tick(self) -> bool:
        """Đẩy pha khi tới mốc thời gian. Hub gọi định kỳ."""
        if self.status != "playing" or not self.deadline:
            return False
        if time.time() < self.deadline:
            return False

        if self.phase == "turn":
            self._timeout()
        elif self.phase == "reveal":
            self._begin_aim()
        elif self.phase == "aim":
            self._fire()
        elif self.phase == "shot":
            self._after_shot()
        else:
            return False
        self.touched = time.time()
        return True

    # ---- serialize --------------------------------------------------------- #
    def _seat_label(self, mark: str) -> str:
        return f"Ghế {mark[1:]}" if mark.startswith("P") else mark

    def _seat_info(self, mark: str) -> dict | None:
        info = super()._seat_info(mark)
        if info is None:
            return None
        state = self.state[mark]
        # Số ổ đã dùng là thông tin CÔNG KHAI: mọi người đều thấy từng phát súng
        # nên ai cũng đếm được. Hiện thẳng ra còn hay hơn, vì biết đối thủ chỉ
        # còn 2 ổ là lúc mọi quyết định trở nên nặng.
        info.update({
            "alive": state.alive,
            "cards": len(state.hand),
            "shots": state.shots,
            "chambers": len(state.cylinder),
            "left": state.chambers_left(),
            "odds": round(state.death_odds(), 4),
            "cause": state.cause,
        })
        return info

    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        mine = player.mark if player else ""
        now = time.time()
        active_taunts = {
            seat: t for seat, t in getattr(self, "taunts", {}).items()
            if now - t["ts"] <= TAUNT_TTL
        }

        return {
            "phase": self.phase,
            "round": self.round_no,
            "tableRank": self.table_rank,
            "tableRankName": RANK_NAME[self.table_rank],
            "rankNames": RANK_NAME,
            "turn": self.turn,
            "forcedLiar": self.forced_liar,
            # Chế độ Ma Vương. ``devilMode`` là cấu hình phòng, ``devilRank`` là
            # "vòng NÀY có Ma Vương, và nó sinh ra từ quân nào" — cả hai đều là
            # thông tin công khai, giấu đi chỉ làm người chơi hoang mang.
            "devilMode": self.devil_mode,
            "devilRank": self.devil_rank,
            "devilName": RANK_NAME[DEVIL],
            # Gửi cả mốc hết hạn và giờ SERVER: đồng hồ máy khách hay lệch, nên
            # client lấy hiệu hai số này rồi tự đếm lùi.
            "deadline": self.deadline,
            "now": time.time(),
            "maxPlay": MAX_PLAY,
            "handSize": HAND_SIZE,
            # Thành phần bộ quân của ĐÚNG vòng này (đã trừ quân hoá Ma Vương),
            # để người chơi đếm quân không bị lệch một con.
            "deckCount": self.deck_count,
            # Chỉ SỐ LƯỢNG mỗi lượt. Mặt quân của các lượt chưa bị hô bịp không
            # bao giờ đi xuống client, kể cả của khán giả.
            "pile": [{"seat": play.seat, "count": play.count} for play in self.pile],
            "lastPlay": ({"seat": self.last_play.seat, "count": self.last_play.count}
                         if self.last_play else None),
            "hand": [{"id": card.id, "rank": card.rank}
                     for card in (self.state[mine].hand if mine else [])],
            "challenge": self.challenge,
            # Kết quả phát súng chỉ có mặt từ pha "shot" trở đi (xem _fire).
            "shot": self.shot,
            # Ai đang bị kề súng, và còn ai đứng chờ sau họ. Cú Ma Vương đẩy cả
            # bàn vào hàng nên client cần biết để hiện "còn N người phải bắn".
            "firing": self.firing,
            "pending": list(self.shot_queue),
            "feed": self.feed[-24:],
            "alive": self.alive_seats(),
            "taunts": active_taunts,
            "tauntChoices": list(TAUNTS),
        }
