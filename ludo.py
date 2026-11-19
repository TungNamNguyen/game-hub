"""Cờ Cá Ngựa (Ludo 4 người) — đủ luật xuất quân, cản đường, đá tiến, Đá Hậu, leo chuồng 1–6.

Quy ước bàn cờ 56 ô vòng ngoài (0..55) theo chiều kim đồng hồ:
  - R (Đỏ):         xuất ở 0,  cửa chuồng ở 55
  - B (Xanh dương): xuất ở 14, cửa chuồng ở 13
  - Y (Vàng):       xuất ở 28, cửa chuồng ở 27
  - G (Xanh lá):    xuất ở 42, cửa chuồng ở 41

Trạng thái mỗi quân ngựa (`pos`):
  - -1      : trong chuồng xuất phát
  - 0..55   : tiến độ bước trên đường vòng ngoài (0 = ô xuất quân, 55 = cửa chuồng đích)
  - 56..61  : trong chuồng đích bậc 1..6 (56 = bậc 1, ..., 61 = bậc 6)

Thắng cuộc: 4 quân của một màu chiếm đủ 4 bậc cao nhất trong chuồng đích (58, 59, 60, 61 = bậc 3, 4, 5, 6).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from games import GameError, Player, SeatedRoom, bot_uid

COLORS = ("R", "B", "Y", "G")
COLOR_NAME = {
    "R": "Đỏ",
    "B": "Xanh dương",
    "Y": "Vàng",
    "G": "Xanh lá",
}
COLOR_HEX = {
    "R": "#ef4444",
    "B": "#3b82f6",
    "Y": "#eab308",
    "G": "#22c55e",
}
START_OFFSET = {
    "R": 0,
    "B": 14,
    "Y": 28,
    "G": 42,
}
TRACK_LEN = 56
HOME_DOOR_PROGRESS = TRACK_LEN - 1  # 55
HOME_TARGET = [58, 59, 60, 61]      # bậc 3, 4, 5, 6
TURN_SECONDS = 30.0
BOT_NAMES = ("Ngựa Xích Thố", "Chiến Mã Xanh", "Hoàng Phi", "Lục Phong")


@dataclass
class LudoMove:
    piece: int
    kind: str               # deploy | deploy_kick | move | kick | kick_back | enter_home | climb_home
    from_pos: int
    to_pos: int
    from_global: int | None
    to_global: int | None
    kicked_color: str = ""
    kicked_piece: int = -1

    def to_dict(self) -> dict:
        return {
            "piece": self.piece,
            "kind": self.kind,
            "fromPos": self.from_pos,
            "toPos": self.to_pos,
            "fromGlobal": self.from_global,
            "toGlobal": self.to_global,
            "kickedColor": self.kicked_color,
            "kickedPiece": self.kicked_piece,
        }


class LudoRoom(SeatedRoom):
    CHANNEL = "ludo"
    SEATS = COLORS
    START_STATUS = "playing"
    HAS_CLOCK = True
    DEFAULT_MODE = "classic"
    MODES = {
        "classic": {"label": "Chuẩn (Xuất 1 & 6 · Đá Hậu)", "deploy": "1and6", "backKick": True},
        "strict": {"label": "Cổ điển (Xuất 6 · Đá Hậu)", "deploy": "6only", "backKick": True},
    }

    def __init__(self, code: str, mode: str = "") -> None:
        self.rng = random.Random()
        super().__init__(code, mode)
        mode_meta = self.MODES.get(self.mode, self.MODES[self.DEFAULT_MODE])
        self.config: dict = {
            "deployRule": mode_meta.get("deploy", "1and6"),  # 1and6 | 6only
            "backKick": bool(mode_meta.get("backKick", True)),
        }
        self.host_uid: str = ""
        self.active_seats: list[str] = []
        self.eliminated: set[str] = set()
        self.pieces: dict[str, list[int]] = {}
        self.turn: str = ""
        self.phase: str = "waiting"       # waiting | roll | move | finished
        self.dice: int = 0
        self.consecutive_sixes: int = 0
        self.legal_moves: list[LudoMove] = []
        self.last_roll: dict | None = None
        self.last_rolls: dict[str, int] = {}
        self.last_event: dict | None = None
        self.deadline: float = 0.0
        self.feed: list[dict] = []
        self._event_seq: int = 0
        self.reset_match()

    def _seat_label(self, mark: str) -> str:
        return COLOR_NAME.get(mark, mark)

    def _note(self, text: str, tone: str = "") -> None:
        self.feed.append({"text": text, "tone": tone, "ts": time.time()})
        del self.feed[:-50]

    def _name(self, mark: str) -> str:
        p = self.seat(mark)
        return p.name if p else self._seat_label(mark)

    def _ensure_host(self) -> None:
        """Đảm bảo luôn có 1 người thật đang ngồi giữ quyền Chủ phòng (nếu còn người ngồi)."""
        if self.host_uid:
            hp = self.players.get(self.host_uid)
            if hp is not None and hp.mark and not hp.bot and hp.connected:
                return
        for m in self.SEATS:
            p = self.seat(m)
            if p is not None and not p.bot and p.connected:
                self.host_uid = p.uid
                return
        for m in self.SEATS:
            p = self.seat(m)
            if p is not None and not p.bot:
                self.host_uid = p.uid
                return
        self.host_uid = ""

    def host_mark(self) -> str:
        if not self.host_uid:
            return ""
        p = self.players.get(self.host_uid)
        return p.mark if p and p.mark else ""

    def reset_match(self) -> None:
        self.pieces = {c: [-1, -1, -1, -1] for c in self.SEATS}
        self.active_seats = []
        self.eliminated = set()
        self.turn = ""
        self.phase = "waiting"
        self.dice = 0
        self.consecutive_sixes = 0
        self.legal_moves = []
        self.last_roll = None
        self.last_rolls = {}
        self.last_event = None
        self.deadline = 0.0
        self.feed = []

    def apply_initial_config(self, config: dict) -> None:
        if not isinstance(config, dict):
            return
        dr = config.get("deployRule")
        if dr in ("1and6", "6only"):
            self.config["deployRule"] = dr
        if "backKick" in config:
            self.config["backKick"] = bool(config["backKick"])

    def _seated_marks(self) -> list[str]:
        return [m for m in self.SEATS if self.seat(m) is not None]

    def _try_start(self) -> None:
        """Auto-start ngay khi đủ 4 ghế có người ngồi."""
        if self.in_progress():
            return
        if len(self._seated_marks()) == len(self.SEATS):
            self._start_match()

    def _start_match(self) -> None:
        seated = self._seated_marks()
        if len(seated) < 2:
            raise GameError("Cần ít nhất 2 người chơi (hoặc thêm Máy) để bắt đầu.")
        self.winner = ""
        self.reset_match()
        self.active_seats = list(seated)
        self.status = self.START_STATUS
        self.rematch.clear()
        first = self.active_seats[0]
        self._begin_turn(first, reset_sixes=True)
        self.on_match_start()

    def on_match_start(self) -> None:
        names = ", ".join(f"{self._name(m)} ({self._seat_label(m)})" for m in self.active_seats)
        self.system(f"Ván Cờ Cá Ngựa bắt đầu: {names}.")
        self._note(f"Bắt đầu ván mới ({len(self.active_seats)} người chơi).", "start")

    def join(self, uid: str, name: str, color: str = "") -> Player:
        player = super().join(uid, name, color)
        self._ensure_host()
        return player

    def sit(self, uid: str) -> None:
        super().sit(uid)
        self._ensure_host()

    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        if self.in_progress():
            mark = player.mark
            player.mark = ""
            self.rematch.discard(mark)
            self._forfeit_seat(mark, f"{player.name} rời bàn")
            self._ensure_host()
            self.touched = time.time()
            return
        super().stand(uid)
        self._ensure_host()

    def disconnect(self, uid: str) -> None:
        super().disconnect(uid)
        self._ensure_host()

    def add_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Thêm 3 máy cho phòng chơi đơn (chừa ghế R cho người tạo)."""
        if self.bot_players():
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        if not any(p.mark and not p.bot for p in self.players.values()):
            if len(free) < 2:
                raise GameError("Không còn ghế cho máy.")
            free = free[1:]
        if not free:
            raise GameError("Không còn ghế cho máy.")
        last = None
        for idx, m in enumerate(free):
            last = self._seat_bot(m, level, BOT_NAMES[idx % len(BOT_NAMES)], slot=idx)
        return last

    def add_single_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Chủ phòng thêm từng máy vào một ghế trống cụ thể hoặc ghế trống tiếp theo."""
        free = self.free_marks()
        if not free:
            raise GameError("Bàn đã đủ 4 người.")
        target = mark if mark in free else free[0]
        if mark and mark not in free:
            raise GameError("Ghế đó đã có người.")
        slot = 0
        while bot_uid(slot) in self.players:
            slot += 1
        lvl = level if level in ("easy", "normal", "hard") else "normal"
        name = BOT_NAMES[COLORS.index(target) % len(BOT_NAMES)]
        return self._seat_bot(target, lvl, f"{name} (Máy)", slot=slot)

    def remove_bot_seat(self, mark: str) -> None:
        if self.in_progress():
            raise GameError("Không thể gỡ máy khi ván đang chạy.")
        p = self.seat(mark)
        if p is None or not p.bot:
            raise GameError("Ghế này không có máy.")
        self.players.pop(p.uid, None)
        self.rematch.discard(mark)
        self.system(f"Đã bỏ {p.name} khỏi ghế {self._seat_label(mark)}.")
        if self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    # ---- toán học đường chạy ------------------------------------------------ #
    @staticmethod
    def global_index(color: str, progress: int) -> int | None:
        if 0 <= progress < TRACK_LEN:
            return (START_OFFSET[color] + progress) % TRACK_LEN
        return None

    def _track_occupancy(self) -> dict[int, tuple[str, int]]:
        """Map global_index (0..55) -> (color, piece_idx)."""
        occ: dict[int, tuple[str, int]] = {}
        for c in self.active_seats:
            if c in self.eliminated:
                continue
            for idx, pos in enumerate(self.pieces.get(c, [])):
                if 0 <= pos < TRACK_LEN:
                    g = (START_OFFSET[c] + pos) % TRACK_LEN
                    occ[g] = (c, idx)
        return occ

    def compute_legal_moves(self, color: str, dice: int) -> list[LudoMove]:
        if dice < 1 or dice > 6 or color in self.eliminated:
            return []
        occ = self._track_occupancy()
        my_pieces = self.pieces.get(color, [])
        can_deploy_nums = (1, 6) if self.config.get("deployRule", "1and6") == "1and6" else (6,)
        back_kick_on = bool(self.config.get("backKick", True))
        moves: list[LudoMove] = []

        for idx, pos in enumerate(my_pieces):
            # 1. Xuất quân từ chuồng (-1 -> 0)
            if pos == -1:
                if dice in can_deploy_nums:
                    g0 = START_OFFSET[color]
                    occupant = occ.get(g0)
                    if occupant is None:
                        moves.append(LudoMove(idx, "deploy", -1, 0, None, g0))
                    elif occupant[0] != color:
                        moves.append(LudoMove(idx, "deploy_kick", -1, 0, None, g0, occupant[0], occupant[1]))
                continue

            # 2. Đang trên đường vòng ngoài (0..55)
            if 0 <= pos <= HOME_DOOR_PROGRESS:
                from_g = self.global_index(color, pos)

                # 2a. Đang đứng tại cửa chuồng (55) -> nhảy thẳng vào bậc `dice` trong chuồng đích
                if pos == HOME_DOOR_PROGRESS:
                    target_pos = HOME_DOOR_PROGRESS + dice
                    blocked_home = any(
                        p_pos in range(HOME_DOOR_PROGRESS + 1, target_pos + 1)
                        for p_pos in my_pieces
                    )
                    if not blocked_home:
                        moves.append(LudoMove(idx, "enter_home", pos, target_pos, from_g, None))

                # 2b. Tiến trên vòng ngoài (không vượt quá cửa chuồng 55)
                if pos + dice <= HOME_DOOR_PROGRESS:
                    blocked = False
                    for step in range(1, dice):
                        mid_g = (START_OFFSET[color] + pos + step) % TRACK_LEN
                        if mid_g in occ:
                            blocked = True
                            break
                    if not blocked:
                        dest_pos = pos + dice
                        dest_g = (START_OFFSET[color] + dest_pos) % TRACK_LEN
                        occupant = occ.get(dest_g)
                        if occupant is None:
                            moves.append(LudoMove(idx, "move", pos, dest_pos, from_g, dest_g))
                        elif occupant[0] != color:
                            moves.append(LudoMove(idx, "kick", pos, dest_pos, from_g, dest_g, occupant[0], occupant[1]))

                # 2c. Đá Hậu (lùi đúng `dice` bước trên vòng ngoài để đá quân địch phía sau)
                if back_kick_on and pos - dice >= 0:
                    blocked_back = False
                    for step in range(1, dice):
                        mid_g = (START_OFFSET[color] + pos - step) % TRACK_LEN
                        if mid_g in occ:
                            blocked_back = True
                            break
                    if not blocked_back:
                        back_pos = pos - dice
                        back_g = (START_OFFSET[color] + back_pos) % TRACK_LEN
                        occupant = occ.get(back_g)
                        if occupant is not None and occupant[0] != color:
                            moves.append(LudoMove(
                                idx, "kick_back", pos, back_pos, from_g, back_g, occupant[0], occupant[1]
                            ))
                continue

            # 3. Đang ở trong chuồng đích (56..60 -> bậc 1..5): cần tung đúng số bậc kế tiếp
            if HOME_DOOR_PROGRESS < pos < 61:
                cur_rank = pos - HOME_DOOR_PROGRESS
                next_rank = cur_rank + 1
                if dice == next_rank and (pos + 1) not in my_pieces:
                    moves.append(LudoMove(idx, "climb_home", pos, pos + 1, None, None))

        return moves

    # ---- điều phối lượt ---------------------------------------------------- #
    def _alive_active_seats(self) -> list[str]:
        return [c for c in self.active_seats if c not in self.eliminated]

    def _next_turn_seat(self, current: str) -> str:
        alive = self._alive_active_seats()
        if not alive:
            return ""
        if current not in self.active_seats:
            return alive[0]
        idx = self.active_seats.index(current)
        for step in range(1, len(self.active_seats) + 1):
            cand = self.active_seats[(idx + step) % len(self.active_seats)]
            if cand not in self.eliminated:
                return cand
        return alive[0]

    def _begin_turn(self, color: str, *, reset_sixes: bool = False) -> None:
        self.turn = color
        self.phase = "roll"
        self.dice = 0
        self.legal_moves = []
        if reset_sixes:
            self.consecutive_sixes = 0
        self.deadline = time.time() + TURN_SECONDS
        self.touched = time.time()

    def _advance_turn(self) -> None:
        nxt = self._next_turn_seat(self.turn)
        if not nxt:
            self.finish("draw")
            return
        self._begin_turn(nxt, reset_sixes=True)

    def _forfeit_seat(self, mark: str, reason: str) -> None:
        if mark in self.eliminated or mark not in self.active_seats:
            return
        self.eliminated.add(mark)
        self.pieces[mark] = [-1, -1, -1, -1]
        self._note(f"{reason} — {self._seat_label(mark)} bị loại.", "quit")
        self.system(f"{reason} — ghế {self._seat_label(mark)} rời cuộc chơi.")
        alive = self._alive_active_seats()
        if len(alive) <= 1:
            self.finish(alive[0] if alive else "draw")
            return
        if self.turn == mark:
            self._advance_turn()

    def _check_victory(self, color: str) -> bool:
        return sorted(self.pieces.get(color, [])) == HOME_TARGET

    def finish(self, winner: str) -> None:
        self.status = "finished"
        self.phase = "finished"
        self.winner = winner
        self.turn = ""
        self.legal_moves = []
        self.deadline = 0.0
        self.rematch.clear()
        if winner in self.scores:
            self.scores[winner] += 1
            self._note(f"🏆 {self._name(winner)} ({self._seat_label(winner)}) về đích thắng cuộc!", "win")
            self.system(f"{self._name(winner)} ({self._seat_label(winner)}) chiến thắng!")
        else:
            self.scores["draw"] += 1
            self._note("Ván đấu kết thúc hòa.", "void")
        self.touched = time.time()

    def resign(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        if player.mark in self.eliminated or player.mark not in self.active_seats:
            raise GameError("Bạn đã rời ván rồi.")
        self._forfeit_seat(player.mark, f"{player.name} xin thua")

    # ---- hành động người chơi ---------------------------------------------- #
    def handle(self, uid: str, action: str, msg: dict) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn cần ngồi vào ghế để thao tác.")

        if action == "config":
            if self.in_progress():
                raise GameError("Không thể đổi luật khi ván đang diễn ra.")
            if self.host_uid and uid != self.host_uid:
                raise GameError("Chỉ Chủ phòng mới được đổi cài đặt.")
            self.apply_initial_config(msg)
            self.touched = time.time()
            return

        if action == "add_bot":
            if self.in_progress():
                raise GameError("Không thể thêm máy khi ván đang chạy.")
            if self.host_uid and uid != self.host_uid:
                raise GameError("Chỉ Chủ phòng mới được thêm máy.")
            level = str(msg.get("level", "normal"))
            mark = str(msg.get("mark", ""))
            self.add_single_bot(level=level, mark=mark)
            return

        if action == "remove_bot":
            if self.in_progress():
                raise GameError("Không thể bỏ máy khi ván đang chạy.")
            if self.host_uid and uid != self.host_uid:
                raise GameError("Chỉ Chủ phòng mới được bỏ máy.")
            self.remove_bot_seat(str(msg.get("mark", "")))
            return

        if action == "start":
            if self.in_progress():
                raise GameError("Ván đang diễn ra.")
            if self.host_uid and uid != self.host_uid:
                raise GameError("Chỉ Chủ phòng mới có quyền bắt đầu sớm.")
            seated = self._seated_marks()
            if len(seated) == 1:
                # Nếu Chủ phòng chơi 1 mình và bấm Bắt đầu ngay, tự thêm 1 Máy để có đối thủ.
                self.add_single_bot(level="normal")
            self._start_match()
            return

        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")

        mark = player.mark
        if mark in self.eliminated or mark not in self.active_seats:
            raise GameError("Bạn không tham gia ván này.")
        if self.turn != mark:
            raise GameError("Chưa tới lượt bạn.")

        if action == "roll":
            if self.phase != "roll":
                raise GameError("Bạn đã tung xúc xắc rồi, hãy chọn quân đi.")
            self._do_roll(mark)
            return

        if action == "move":
            if self.phase != "move":
                raise GameError("Hãy tung xúc xắc trước.")
            piece_idx = int(msg.get("piece", -1))
            kind = str(msg.get("kind", ""))
            self._do_move(mark, piece_idx, kind)
            return

        raise GameError("Hành động không hợp lệ.")

    def _do_roll(self, mark: str) -> None:
        val = self.rng.randint(1, 6)
        self.dice = val
        if val == 6:
            self.consecutive_sixes += 1
        else:
            self.consecutive_sixes = 0

        self._event_seq += 1
        self.last_roll = {"seq": self._event_seq, "color": mark, "value": val}
        self.last_rolls[mark] = val

        if self.consecutive_sixes >= 3:
            self._note(f"{self._name(mark)} tung 3 lần 6 liên tiếp — mất lượt!", "warn")
            self.last_event = {
                "seq": self._event_seq,
                "type": "triple6",
                "color": mark,
                "dice": val,
            }
            self._advance_turn()
            return

        moves = self.compute_legal_moves(mark, val)
        if not moves:
            self._note(f"{self._name(mark)} tung được {val} — không có nước đi.", "skip")
            self.last_event = {
                "seq": self._event_seq,
                "type": "nomove",
                "color": mark,
                "dice": val,
            }
            self._advance_turn()
            return

        self.legal_moves = moves
        self.phase = "move"
        self.deadline = time.time() + TURN_SECONDS
        self.touched = time.time()

    def _do_move(self, mark: str, piece_idx: int, kind: str = "") -> None:
        matches = [m for m in self.legal_moves if m.piece == piece_idx]
        if kind:
            matches = [m for m in matches if m.kind == kind] or matches
        if not matches:
            raise GameError("Nước đi không hợp lệ cho quân này.")
        # Nếu cùng 1 quân vừa đi tiến vừa Đá Hậu (với cùng số xúc xắc) mà client gửi rõ kind -> đã lọc ở trên;
        # nếu không gửi kind, ưu tiên Đá Hậu / Đá tiến trước.
        if len(matches) > 1:
            prio = {"kick_back": 0, "kick": 1, "deploy_kick": 2, "enter_home": 3, "climb_home": 4, "move": 5, "deploy": 6}
            matches.sort(key=lambda m: prio.get(m.kind, 9))
        mv = matches[0]

        self.pieces[mark][mv.piece] = mv.to_pos
        kicked = False
        if mv.kicked_color and mv.kicked_piece >= 0:
            self.pieces[mv.kicked_color][mv.kicked_piece] = -1
            kicked = True

        self._event_seq += 1
        self.last_event = {
            "seq": self._event_seq,
            "type": mv.kind,
            "color": mark,
            "dice": self.dice,
            **mv.to_dict(),
        }

        label_me = self._name(mark)
        if mv.kind == "kick_back":
            self._note(
                f"⚔️ {label_me} ĐÁ HẬU văng ngựa của {self._name(mv.kicked_color)} về chuồng!",
                "backkick",
            )
        elif mv.kind in ("kick", "deploy_kick"):
            self._note(
                f"💥 {label_me} đá văng ngựa của {self._name(mv.kicked_color)} về chuồng!",
                "kick",
            )
        elif mv.kind == "deploy":
            self._note(f"🐎 {label_me} xuất quân ra bàn (tung {self.dice}).", "move")
        elif mv.kind in ("enter_home", "climb_home"):
            rank = mv.to_pos - HOME_DOOR_PROGRESS
            self._note(f"🏁 {label_me} đưa ngựa lên bậc {rank}!", "home")
        else:
            self._note(f"{label_me} đi {self.dice} bước.", "move")

        if self._check_victory(mark):
            self.finish(mark)
            return

        if self.dice == 6 or kicked:
            self._begin_turn(mark, reset_sixes=(self.dice != 6))
        else:
            self._advance_turn()

    # ---- đồng hồ & bot ---------------------------------------------------- #
    def tick(self) -> bool:
        if not self.in_progress() or not self.deadline:
            return False
        if time.time() < self.deadline:
            return False
        mark = self.turn
        if not mark:
            return False
        if self.phase == "roll":
            self._note(f"{self._name(mark)} hết giờ — tự tung xúc xắc.", "timeout")
            self._do_roll(mark)
            return True
        if self.phase == "move" and self.legal_moves:
            mv = self.rng.choice(self.legal_moves)
            self._note(f"{self._name(mark)} hết giờ — tự đi một nước.", "timeout")
            self._do_move(mark, mv.piece, mv.kind)
            return True
        self._advance_turn()
        return True

    def bot_pending(self, mark: str) -> bool:
        return self.in_progress() and self.turn == mark and self.phase in ("roll", "move")

    def progress_token(self) -> tuple:
        return (self.status, self.phase, self.turn, self.dice, self._event_seq, self.winner)

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ người đang ngồi mới xin đánh lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        seated = set(self._seated_marks())
        if len(seated) >= 2 and self.rematch >= seated:
            self._start_match()
        else:
            self.system(f"{player.name} muốn chơi ván mới.")

    # ---- serialize --------------------------------------------------------- #
    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        my_mark = player.mark if player else ""
        host_m = self.host_mark()
        # Tóm tắt vị trí quân ở mức global để frontend dễ vẽ
        board_pieces: dict[str, list[dict]] = {}
        for c in self.SEATS:
            arr = []
            for idx, pos in enumerate(self.pieces.get(c, [-1, -1, -1, -1])):
                if pos == -1:
                    zone = "stable"
                    g = None
                    rank = 0
                elif 0 <= pos <= HOME_DOOR_PROGRESS:
                    zone = "track"
                    g = self.global_index(c, pos)
                    rank = 0
                else:
                    zone = "home"
                    g = None
                    rank = pos - HOME_DOOR_PROGRESS
                arr.append({
                    "id": idx,
                    "pos": pos,
                    "zone": zone,
                    "global": g,
                    "rank": rank,
                })
            board_pieces[c] = arr

        is_my_turn = self.in_progress() and my_mark == self.turn
        return {
            "phase": self.phase,
            "config": dict(self.config),
            "hostUid": self.host_uid,
            "hostMark": host_m,
            "isHost": bool(uid and uid == self.host_uid),
            "activeSeats": list(self.active_seats),
            "eliminated": sorted(self.eliminated),
            "turn": self.turn,
            "dice": self.dice,
            "consecutiveSixes": self.consecutive_sixes,
            "pieces": board_pieces,
            "legalMoves": [m.to_dict() for m in self.legal_moves] if is_my_turn else [],
            "lastRoll": self.last_roll,
            "lastRolls": dict(self.last_rolls),
            "lastEvent": self.last_event,
            "now": time.time(),
            "deadline": self.deadline,
            "feed": self.feed[-25:],
            "colorHex": COLOR_HEX,
            "startOffset": START_OFFSET,
        }
