"""Nền tảng phòng có ghế, dùng chung cho mọi game nhiều người trong hub.

Caro, cờ vua, Bắn tàu, Sòng Bịp khác nhau ở luật, nhưng giống nhau y hệt ở phần
khung: ghế, khán giả, vào lại đúng ghế sau khi F5, xin đánh lại, tỉ số, chat
trong phòng. Toàn bộ phần đó nằm ở ``SeatedRoom`` để các game không phải viết
lại — mỗi chỗ viết lại là một chỗ có thể lệch nhau.

Số ghế do lớp con quyết định qua ``SEATS``: mặc định hai ghế ("X", "O") cho game
đối kháng, còn Sòng Bịp dùng tới bốn ghế. Mọi vòng lặp trong file này đi theo
``self.SEATS`` chứ không theo hằng ``MARKS``, nên bàn N ghế không cần bản sao
riêng của phần khung.

Module này là Python thuần: không I/O, không import framework, nên luật chơi
test được độc lập.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

MARKS = ("X", "O")

# Bỏ ký tự dễ đọc lẫn (0/O, 1/I/L) để đọc mã phòng qua điện thoại không sai.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 4

NAME_MAX = 24
CHAT_MAX = 300
CHAT_HISTORY = 80
CHAT_COOLDOWN = 0.4     # giây, chặn spam chat trong phòng

# uid dành riêng cho máy. Chuỗi này khớp [A-Za-z0-9_-] nên về hình thức một
# client vẫn khai được, vì vậy server TỪ CHỐI mọi uid bắt đầu bằng tiền tố này
# ngay ở endpoint WebSocket (xem server.py). Nếu không chặn thì ai đó có thể nối
# vào bằng uid của máy và chiếm ghế của nó, hoặc đi nước thay nó.
#
# Phải là TIỀN TỐ chứ không phải một hằng đơn lẻ: bàn Sòng Bịp có tới ba máy
# cùng lúc, mà ``players`` lại đánh khoá theo uid nên mỗi máy cần một uid khác
# nhau (__bot__, __bot__2, __bot__3).
BOT_UID_PREFIX = "__bot__"
BOT_UID = BOT_UID_PREFIX


def bot_uid(slot: int = 0) -> str:
    """uid của máy thứ ``slot``. Máy đầu giữ nguyên "__bot__" để không phá vỡ
    các phòng/test đã dùng hằng cũ."""
    return BOT_UID_PREFIX if slot <= 0 else f"{BOT_UID_PREFIX}{slot + 1}"


def is_bot_uid(uid: str) -> bool:
    return (uid or "").startswith(BOT_UID_PREFIX)


class GameError(Exception):
    """Hành động không hợp lệ. Thông điệp hiển thị thẳng cho người chơi."""


def clean_name(raw: str) -> str:
    """Bỏ ký tự điều khiển và giới hạn độ dài để tên không phá vỡ giao diện."""
    text = "".join(ch for ch in (raw or "") if ch.isprintable()).strip()
    return text[:NAME_MAX] or "Người chơi"


def clean_text(raw: str, limit: int = CHAT_MAX) -> str:
    text = "".join(ch for ch in (raw or "") if ch.isprintable() or ch == " ").strip()
    return text[:limit]


def other_mark(mark: str) -> str:
    return "O" if mark == "X" else "X"


def int_field(msg: dict, key: str, default: int = 0) -> int:
    """Đọc số nguyên an toàn từ gói tin client; chặn Infinity/NaN gây OverflowError."""
    raw = msg.get(key, default)
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return default
        return int(raw)
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(val):
        return default
    return int(val)


@dataclass
class Player:
    uid: str
    name: str
    color: str = "#6366f1"
    mark: str = ""          # "X", "O", hoặc "" nếu là khán giả
    connected: bool = True
    last_chat: float = 0.0
    bot: bool = False       # True nếu đây là máy, không phải người
    level: str = ""         # độ khó của máy: easy | normal | hard


# --------------------------------------------------------------------------- #
# phòng
# --------------------------------------------------------------------------- #
class SeatedRoom:
    """Phòng có ghế. Lớp con cài luật chơi qua các hook ở cuối file này."""

    CHANNEL = ""                    # "caro" | "ship" | "bluff" | ...
    MODES: dict[str, dict] = {}     # id chế độ -> {label, ...}
    DEFAULT_MODE = ""
    START_STATUS = "playing"        # trạng thái khi vừa đủ người
    #: Danh sách ghế, theo đúng THỨ TỰ LƯỢT. Lớp con nhiều người ghi đè, hoặc
    #: đặt lại trong __init__ nếu số ghế phụ thuộc chế độ (Sòng Bịp 2/3/4 người).
    SEATS: tuple[str, ...] = MARKS
    #: True nếu phòng có đồng hồ riêng và cần hub gọi ``tick()`` định kỳ.
    HAS_CLOCK = False

    def __init__(self, code: str, mode: str = "") -> None:
        mode = mode or self.DEFAULT_MODE
        if mode not in self.MODES:
            raise GameError("Chế độ không hợp lệ.")
        self.code = code
        self.mode = mode
        # Ghi lên INSTANCE: số ghế có thể phụ thuộc chế độ, nên phải chốt ngay
        # ở đây, trước mọi thứ đọc tới self.SEATS (tỉ số, ghế trống...).
        self.SEATS = self.seats_for(mode)
        self.players: dict[str, Player] = {}
        self.status = "waiting"     # waiting | (START_STATUS) | finished
        self.winner = ""            # id ghế thắng, "draw", hoặc ""
        self.scores = self._blank_scores()
        self.rematch: set[str] = set()
        self.chat: list[dict] = []
        self.first_turn = self.SEATS[0]
        # Phòng chơi đơn: có một ghế là máy. Không hiện ở sảnh chờ chung vì đó
        # là ván riêng của một người, không phải chỗ để người khác nhảy vào.
        self.solo = False
        self.avatar_for = None
        self.touched = time.time()

    # ---- thuộc tính dẫn xuất ---------------------------------------------- #
    @classmethod
    def seats_for(cls, mode: str) -> tuple[str, ...]:
        """Danh sách ghế của một chế độ. Ghi đè khi số ghế thay đổi theo chế độ."""
        return cls.SEATS

    def _blank_scores(self) -> dict[str, int]:
        return {**{seat: 0 for seat in self.SEATS}, "draw": 0}

    @property
    def label(self) -> str:
        return self.MODES[self.mode]["label"]

    def seat(self, mark: str) -> Player | None:
        return next((p for p in self.players.values() if p.mark == mark), None)

    def free_marks(self) -> list[str]:
        taken = {p.mark for p in self.players.values() if p.mark}
        return [m for m in self.SEATS if m not in taken]

    def has_connection(self) -> bool:
        """Còn NGƯỜI nào đang kết nối không.

        Máy bị loại khỏi phép tính có chủ ý: máy luôn "connected", nếu tính nó
        thì phòng chơi đơn sẽ sống mãi và không bao giờ bị dọn.
        """
        return any(p.connected for p in self.players.values() if not p.bot)

    def in_progress(self) -> bool:
        return self.status not in ("waiting", "finished")

    # ---- máy (chơi đơn) ---------------------------------------------------- #
    def add_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Đặt máy vào một ghế. Mặc định lấy ghế CUỐI còn trống để người vào
        sau nhận ghế X — cờ vua/cờ tướng cho ghế X đi trước ở ván đầu, nên
        người chơi được đi trước.

        Game nhiều người ghi đè hàm này để đặt nhiều máy một lượt, nhưng LUÔN
        phải chừa ít nhất một ghế cho người tạo phòng: ``RoomManager.solo()``
        tạo phòng rồi gọi hàm này trước khi người chơi kịp ngồi vào.
        """
        if self.bot_player() is not None:
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        if mark:
            if mark not in free:
                raise GameError("Ghế đó đã có người.")
        elif free:
            mark = free[-1]
        else:
            raise GameError("Không còn ghế cho máy.")
        return self._seat_bot(mark, level, self.bot_name(level))

    def _seat_bot(self, mark: str, level: str, name: str, slot: int = 0) -> Player:
        """Đặt một máy vào ghế đã chọn. Dùng chung cho bàn 2 ghế và bàn N ghế."""
        uid = bot_uid(slot)
        player = Player(uid=uid, name=name, color="#64748b",
                        mark=mark, connected=True, bot=True, level=level)
        self.players[uid] = player
        self.solo = True
        self.system(f"{player.name} vào ghế {self._seat_label(mark)}.")
        self._try_start()
        self.touched = time.time()
        return player

    @staticmethod
    def bot_name(level: str) -> str:
        return {"easy": "Máy (dễ)", "normal": "Máy (thường)",
                "hard": "Máy (khó)"}.get(level, "Máy")

    def bot_players(self) -> list[Player]:
        """Mọi máy trong phòng, theo thứ tự ghế để hành vi lặp lại được."""
        order = {seat: i for i, seat in enumerate(self.SEATS)}
        return sorted((p for p in self.players.values() if p.bot),
                      key=lambda p: order.get(p.mark, 99))

    def bot_player(self) -> Player | None:
        """Máy đầu tiên trong phòng, hoặc None. Giữ lại cho phòng 2 ghế."""
        bots_here = self.bot_players()
        return bots_here[0] if bots_here else None

    def bot_should_act(self) -> bool:
        """Máy có việc phải làm ngay bây giờ không."""
        return self.bot_to_act() is not None

    def bot_to_act(self) -> Player | None:
        """Máy nào phải đi NGAY BÂY GIỜ, hoặc None nếu chưa tới việc của máy.

        Hub gọi hàm này trong vòng lặp máy, nên bàn có ba máy vẫn chỉ cần một
        vòng lặp: mỗi lượt nó hỏi lại "giờ tới máy nào".
        """
        if not self.in_progress():
            return None
        for bot in self.bot_players():
            if bot.mark and self.bot_pending(bot.mark):
                return bot
        return None

    def bot_to_vote(self) -> Player | None:
        """Máy nào còn chưa bấm đánh lại. Máy chỉ hưởng ứng sau khi có người
        bấm trước — nó không tự đòi chơi tiếp."""
        if self.status != "finished" or not self.rematch:
            return None
        for bot in self.bot_players():
            if bot.mark and bot.mark not in self.rematch:
                return bot
        return None

    def bot_pending(self, mark: str) -> bool:
        """Mặc định: chỉ tới lượt mới đi. Lớp con override nếu có pha mà cả hai
        bên hành động cùng lúc (Bắn tàu: pha xếp tàu)."""
        return getattr(self, "turn", "") == mark

    def tick(self) -> bool:
        """Đồng hồ của phòng. Trả về True nếu trạng thái vừa đổi và cần phát lại.

        Chỉ những phòng đặt ``HAS_CLOCK = True`` được hub gọi tới. Mặc định
        không có đồng hồ nào nên không làm gì.
        """
        return False

    def progress_token(self) -> tuple:
        """Dấu vết trạng thái ván, dùng để phát hiện bàn đã đổi trong lúc máy
        đang nghĩ ở thread khác. Lớp con nối thêm phần của riêng mình."""
        return (self.status, self.winner, getattr(self, "turn", ""))

    # ---- chat trong phòng -------------------------------------------------- #
    def system(self, text: str) -> None:
        self.chat.append({"kind": "system", "text": text, "ts": time.time()})
        del self.chat[:-CHAT_HISTORY]

    def say(self, uid: str, text: str) -> None:
        player = self.players.get(uid)
        if player is None:
            return
        message = clean_text(text)
        if not message:
            return
        now = time.time()
        if now - player.last_chat < CHAT_COOLDOWN:
            raise GameError("Gõ chậm thôi.")
        player.last_chat = now
        self.chat.append({"kind": "chat", "name": player.name, "color": player.color,
                          "mark": player.mark, "text": message, "ts": now})
        del self.chat[:-CHAT_HISTORY]
        self.touched = now

    # ---- ghế --------------------------------------------------------------- #
    def join(self, uid: str, name: str, color: str = "") -> Player:
        """Vào phòng. uid cũ được nối lại đúng ghế nên F5 không mất ván."""
        self.touched = time.time()
        player = self.players.get(uid)
        if player:
            if name:
                player.name = clean_name(name)
            if color:
                player.color = color
            if not player.connected:
                player.connected = True
                self.system(f"{player.name} đã kết nối lại.")
            return player

        player = Player(uid=uid, name=clean_name(name), color=color or "#6366f1")
        self.players[uid] = player
        free = self.free_marks()
        if free:
            player.mark = free[0]
            self._reset_scores()
            self.system(f"{player.name} vào ghế {self._seat_label(player.mark)}.")
        else:
            self.system(f"{player.name} vào xem.")
        self._try_start()
        return player

    def sit(self, uid: str) -> None:
        player = self.players[uid]
        if player.mark:
            raise GameError("Bạn đang ngồi rồi.")
        free = self.free_marks()
        if not free:
            raise GameError("Bàn đã kín ghế.")
        player.mark = free[0]
        self._reset_scores()
        self.system(f"{player.name} vào ghế {self._seat_label(player.mark)}.")
        self._try_start()
        self.touched = time.time()

    def stand(self, uid: str) -> None:
        """Rời ghế. Đang chơi thì ván bị hủy, phòng quay về trạng thái chờ."""
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        mark, player.mark = player.mark, ""
        self.rematch.discard(mark)
        self.system(f"{player.name} rời ghế {self._seat_label(mark)}.")
        if self.in_progress():
            self.status = "waiting"
            self.winner = ""
            self.reset_match()
            self.system("Ván bị hủy vì thiếu người.")
        elif self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    def disconnect(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None:
            return
        player.connected = False
        self.touched = time.time()
        if player.mark and not self.in_progress():
            # Chưa vào ván thì nhả ghế luôn để người khác vào chơi.
            mark, player.mark = player.mark, ""
            self.rematch.discard(mark)
            self.system(f"{player.name} rời phòng, ghế {self._seat_label(mark)} trống.")
        else:
            self.system(f"{player.name} mất kết nối.")
        if not player.mark:
            self.players.pop(uid, None)

    # ---- vòng đời ván ------------------------------------------------------ #
    def _reset_scores(self) -> None:
        """Cặp đấu đổi người thì tỉ số cũ không còn ý nghĩa."""
        self.scores = self._blank_scores()

    def _try_start(self) -> None:
        if self.in_progress():
            return
        if all(self.seat(m) for m in self.SEATS):
            self.winner = ""
            self.reset_match()
            self.status = self.START_STATUS
            self.on_match_start()

    def finish(self, winner: str) -> None:
        """Kết thúc ván: cộng điểm và cho người thua đi trước ván sau.

        Bản này (cùng với ``resign``) mang luật của bàn HAI ghế: "người kia" là
        một người xác định. Bàn nhiều ghế phải ghi đè cả hai.
        """
        self.status = "finished"
        self.winner = winner
        self.rematch.clear()
        if winner == "draw":
            self.scores["draw"] += 1
            self.first_turn = other_mark(self.first_turn)
        else:
            self.scores[winner] += 1
            self.first_turn = other_mark(winner)
        self.touched = time.time()

    def resign(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        self.system(f"{player.name} xin thua.")
        self.finish(other_mark(player.mark))

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ người đang ngồi mới xin đánh lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        # Phải ĐỦ ghế có người rồi mới tính phiếu: nếu một người ngắt kết nối
        # ngay lúc ván vừa xong thì ghế của họ được nhả ra (xem disconnect), lúc
        # đó "mọi người đã bấm" không được phép khởi động ván thiếu người.
        seated = {m for m in self.SEATS if self.seat(m)}
        if len(seated) == len(self.SEATS) and self.rematch >= seated:
            self.winner = ""
            self.reset_match()
            self.status = self.START_STATUS
            self.rematch.clear()
            self.on_match_start()
        else:
            self.system(f"{player.name} muốn đánh lại.")

    # ---- serialize --------------------------------------------------------- #
    def _seat_info(self, mark: str) -> dict | None:
        player = self.seat(mark)
        if player is None:
            return None
        avatar_fn = getattr(self, "avatar_for", None)
        return {"name": player.name, "color": player.color,
                "connected": player.connected, "uid": player.uid,
                "bot": player.bot, "level": player.level,
                "avatar": avatar_fn(player.uid) if (not player.bot and callable(avatar_fn)) else None}

    def view(self, uid: str) -> dict:
        """Trạng thái gửi cho một người cụ thể.

        Phải nhận uid vì có game cần che thông tin của đối thủ (Bắn tàu không
        được để client thấy vị trí tàu đối phương).
        """
        player = self.players.get(uid)
        base = {
            "code": self.code,
            "mode": self.mode,
            "label": self.label,
            "status": self.status,
            "winner": self.winner,
            "scores": self.scores,
            "seatOrder": list(self.SEATS),
            "seats": {m: self._seat_info(m) for m in self.SEATS},
            "seatLabels": {m: self._seat_label(m) for m in self.SEATS},
            "spectators": [{"name": p.name, "color": p.color}
                           for p in self.players.values() if not p.mark and p.connected],
            "rematch": sorted(self.rematch),
            "chat": self.chat[-40:],
            "you": {
                "uid": uid,
                "mark": player.mark if player else "",
                "name": player.name if player else "",
            },
        }
        base.update(self.match_view(uid))
        return base

    def summary(self) -> dict:
        """Một dòng trong danh sách phòng ở sảnh chờ."""
        seated = [self._seat_info(m) for m in self.SEATS]
        return {
            "code": self.code,
            "channel": self.CHANNEL,
            "mode": self.mode,
            "label": self.label,
            "status": self.status,
            "players": [s["name"] for s in seated if s],
            "seated": sum(1 for s in seated if s),
            "spectators": sum(1 for p in self.players.values() if not p.mark),
            "openSeats": len(self.free_marks()),
            "seatCount": len(self.SEATS),
            "solo": self.solo,
        }

    # ---- hook cho lớp con -------------------------------------------------- #
    def _seat_label(self, mark: str) -> str:
        """Tên ghế hiển thị cho người chơi, ví dụ "X" hoặc "Người 1"."""
        return mark

    def reset_match(self) -> None:
        """Dọn bàn cho ván mới. KHÔNG tự đặt self.status, phần đó base lo."""
        raise NotImplementedError

    def on_match_start(self) -> None:
        """Gọi ngay sau khi ván mới bắt đầu, dùng để thông báo trong chat."""

    def match_view(self, uid: str) -> dict:
        """Phần trạng thái riêng của game, đã che thông tin cần che."""
        raise NotImplementedError

    def apply_initial_config(self, config: dict) -> None:
        """Áp dụng cấu hình ban đầu khi tạo phòng từ sảnh (nếu game hỗ trợ)."""
        return None

    def handle(self, uid: str, action: str, msg: dict) -> None:
        """Xử lý hành động riêng của game. Ném GameError nếu không hợp lệ."""
        raise GameError("Hành động không hợp lệ.")


# --------------------------------------------------------------------------- #
# quản lý phòng
# --------------------------------------------------------------------------- #
class RoomManager:
    """Giữ phòng trong RAM. Tắt server là mất hết, đúng ý đồ cho game."""

    def __init__(self, room_class: type[SeatedRoom], limit: int = 300) -> None:
        self.room_class = room_class
        self.rooms: dict[str, SeatedRoom] = {}
        self.limit = limit

    def _new_code(self) -> str:
        for _ in range(800):
            code = "".join(random.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                return code
        raise GameError("Hết mã phòng, thử lại sau.")

    def create(self, mode: str = "", config: dict | None = None) -> SeatedRoom:
        if len(self.rooms) >= self.limit:
            self.prune(idle=0)
        if len(self.rooms) >= self.limit:
            raise GameError("Server đang đầy phòng.")
        room = self.room_class(self._new_code(), mode)
        if config:
            room.apply_initial_config(config)
        self.rooms[room.code] = room
        return room

    def get(self, code: str) -> SeatedRoom | None:
        return self.rooms.get((code or "").strip().upper())

    def quick(self, mode: str = "", config: dict | None = None) -> SeatedRoom:
        """Ghép nhanh: ưu tiên phòng chỉ còn một ghế trống (vào là chơi ngay).

        Phòng có máy không cần loại riêng: máy đã chiếm một ghế nên
        ``free_marks()`` chỉ còn trống khi chính người chơi đã rời ghế, lúc đó
        ghép thêm người vào là hợp lý.
        """
        mode = mode or self.room_class.DEFAULT_MODE
        candidates = [r for r in self.rooms.values()
                      if r.mode == mode and r.free_marks() and r.has_connection()]
        if candidates:
            return max(candidates, key=lambda r: (len(r.free_marks()) == 1, r.touched))
        return self.create(mode, config=config)

    def solo(self, mode: str = "", level: str = "normal", config: dict | None = None) -> SeatedRoom:
        """Phòng chơi đơn: tạo mới rồi đặt máy vào một ghế."""
        room = self.create(mode, config=config)
        try:
            room.add_bot(level)
        except GameError:
            self.rooms.pop(room.code, None)
            raise
        return room

    def lobby(self, limit: int = 40) -> list[dict]:
        """Danh sách phòng ở sảnh chờ.

        Phòng đấu với máy CŨNG hiện ở đây (cờ ``solo`` trong summary để giao
        diện đánh dấu "vs máy"). Người khác vào sẽ là khán giả vì hai ghế đã
        kín — xem được ván người ta đánh với máy cũng là điều hay.

        Vẫn lọc theo ``has_connection()``, mà hàm đó không tính máy, nên phòng
        người chơi đã rời đi sẽ tự rụng khỏi danh sách.
        """
        rooms = [r for r in self.rooms.values() if r.has_connection()]
        rooms.sort(key=lambda r: -r.touched)
        return [r.summary() for r in rooms[:limit]]

    def prune(self, idle: float = 1800.0) -> list[str]:
        """Xóa phòng không còn ai kết nối và đã im lặng quá ``idle`` giây."""
        now = time.time()
        dead = [code for code, room in self.rooms.items()
                if not room.has_connection() and now - room.touched > idle]
        for code in dead:
            self.rooms.pop(code, None)
        return dead
