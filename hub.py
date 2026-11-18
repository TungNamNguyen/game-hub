"""Nhân của hub: danh tính, ai đang online, và định tuyến WebSocket.

Cả hub dùng MỘT kết nối WebSocket cho mỗi người, các ứng dụng chia nhau qua
field ``ch`` (channel) trong mỗi gói tin. Làm vậy vì:
  - Mở 4 socket cho 4 app thì presence và thông báo chéo app rất khó đồng bộ.
  - Một socket thì biết chắc một người còn online hay không.

Khuôn gói tin:  {"ch": "hub|caro|ship|chess|xiangqi|chat", "t": "<loại>", ...dữ liệu}
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import time
import traceback
from dataclasses import dataclass, field

import bots
import db
from avatar import AvatarStore
from battleship import ShipRoom
from bluff import BluffRoom
from caro import CaroRoom
from chat import REACTIONS, ChatError, ChatStore
from chessgame import ChessRoom
from flags_quiz import FlagsRoom
from games import GameError, RoomManager, clean_name
from geoguessr import GeoRoom
from poker import PokerRoom
from poker_board import PokerBoard
from xiangqi import XiangqiRoom

GAME_CHANNELS = ("caro", "ship", "chess", "xiangqi", "bluff", "poker", "geo", "flags")

# Nhịp gọi ``room.tick()`` cho những phòng có đồng hồ riêng (Sòng Bịp: đếm lùi
# 30 giây mỗi lượt, và chuỗi pha lật quân -> xoay ổ đạn -> nổ súng). 0.35s đủ mịn
# để animation không bị lệch mà vẫn gần như không tốn gì.
TICK_EVERY = 0.35

# Tối đa bao nhiêu lượt máy đi liên tiếp trong một vòng lặp. Bắn tàu cho bắn
# tiếp khi trúng, và một vòng Sòng Bịp có thể có tới 20 lượt đặt quân trước khi
# ai đó hô bịp (bàn 4 người × 5 quân, mỗi lượt ít nhất 1 quân) — lại còn có thể
# toàn bộ là máy nếu người chơi đã bị loại và đang ngồi xem. Giới hạn để một ván
# lỗi không quay vòng vô hạn và giữ event loop luôn thoát ra được.
BOT_MAX_STEPS = 60

# Màu gán theo uid để cùng một người luôn ra cùng màu trên mọi máy.
PALETTE = (
    "#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6",
    "#ef4444", "#06b6d4", "#84cc16", "#f97316", "#a855f7",
)

APPS = [
    {"id": "home", "name": "Trang chủ", "desc": "Ai đang online và phòng đang mở"},
    {"id": "chat", "name": "Chat nhóm", "desc": "Nhắn tin, gửi ảnh, biểu cảm"},
    {"id": "caro", "name": "Cờ caro", "desc": "Caro / XO tới 2.500 ô"},
    {"id": "chess", "name": "Cờ vua", "desc": "Đủ luật: nhập thành, phong cấp, chiếu hết"},
    {"id": "xiangqi", "name": "Cờ tướng", "desc": "Xiangqi 9x10, đủ luật mã - tượng - pháo"},
    {"id": "ship", "name": "Bắn tàu", "desc": "Battleship 10x10, 5 tàu"},
    {"id": "bluff", "name": "Sòng Bịp",
     "desc": "Đặt úp 1-3 quân và nói dối. Bị bắt bài thì xoay ổ đạn"},
    {"id": "poker", "name": "Xì Tố",
     "desc": "Texas Hold'em 2-6 người, 100.000 chip ảo mỗi lần vào bàn"},
    {"id": "geo", "name": "Địa Đồ",
     "desc": "Đoán tọa độ thế giới & Việt Nam 1-6 người"},
    {"id": "flags", "name": "Đố Cờ & Thủ Đô",
     "desc": "Đoán tên nước từ quốc kỳ & thủ đô của 197 quốc gia"},
    {"id": "faces", "name": "Tạo avatar",
     "desc": "Bấm một nút ra một mặt người mới, dùng làm ảnh đại diện"},
]


def color_for(uid: str) -> str:
    return PALETTE[sum(uid.encode()) % len(PALETTE)]


class ProfileStore:
    """uid -> {name, color} mới nhất. Lưu xuống Postgres (hoặc profiles.json)
    để tên hiển thị đúng ngay cả khi server restart."""

    def __init__(self, data_dir) -> None:
        self.path = data_dir / "profiles.json"
        self.tokens_path = data_dir / "tokens.json"
        self.data: dict[str, dict] = {}
        self.tokens: dict[str, str] = {}
        if self.tokens_path.exists():
            with contextlib.suppress(Exception):
                loaded = json.loads(self.tokens_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.tokens = {str(k): str(v) for k, v in loaded.items()}
        if db.is_enabled():
            with db.connection() as conn:
                rows = conn.execute("select uid, name, color from public.profiles").fetchall()
            for uid, name, color in rows:
                self.data[uid] = {"name": name, "color": color}
        elif self.path.exists():
            with contextlib.suppress(Exception):
                self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def verify_or_bind_token(self, uid: str, token: str) -> bool:
        """Xác thực hoặc gắn chặt secret token lần đầu cho ``uid``.

        Chống giả mạo ``uid`` của người khác qua DevTools / tham số URL khi chạy
        công khai trên Internet mà vẫn giữ trải nghiệm vào chơi ngay không cần
        tài khoản mật khẩu.
        """
        clean_tok = (token or "").strip()
        existing = self.tokens.get(uid)
        if not clean_tok:
            return existing is None
        if len(clean_tok) > 128:
            return False
        digest = hashlib.sha256(clean_tok.encode("utf-8")).hexdigest()
        if existing is None:
            self.tokens[uid] = digest
            with contextlib.suppress(Exception):
                self.tokens_path.write_text(
                    json.dumps(self.tokens, ensure_ascii=False), encoding="utf-8"
                )
            return True
        return hmac.compare_digest(existing, digest)

    def update(self, uid: str, name: str, color: str) -> None:
        self.data[uid] = {"name": name, "color": color}
        if db.is_enabled():
            with contextlib.suppress(Exception), db.connection() as conn:
                conn.execute(
                    """
                    insert into public.profiles (uid, name, color)
                    values (%s, %s, %s)
                    on conflict (uid)
                    do update set
                        name = excluded.name,
                        color = excluded.color,
                        updated_at = now()
                    """,
                    (uid, name, color),
                )
        else:
            with contextlib.suppress(Exception):
                self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def snapshot(self, avatars: AvatarStore | None = None) -> dict[str, dict]:
        """avatar không lưu ở đây (AvatarStore đã tự quản theo uid) — ghép vào
        khi trả ra để client chỉ cần đọc một map duy nhất."""
        if avatars is None:
            return dict(self.data)
        return {uid: {**profile, "avatar": avatars.url(uid)}
                for uid, profile in self.data.items()}


@dataclass
class Session:
    """Một kết nối WebSocket của một người."""
    sock: object
    uid: str
    name: str
    color: str
    avatar: str | None = None                              # url, None nếu chưa có
    rooms: dict[str, str] = field(default_factory=dict)   # channel -> mã phòng
    app: str = "home"
    joined: float = field(default_factory=time.time)


class Hub:
    def __init__(self, data_dir) -> None:
        self.sessions: dict[object, Session] = {}
        self.managers: dict[str, RoomManager] = {
            "caro": RoomManager(CaroRoom),
            "chess": RoomManager(ChessRoom),
            "xiangqi": RoomManager(XiangqiRoom),
            "ship": RoomManager(ShipRoom),
            "bluff": RoomManager(BluffRoom),
            "poker": RoomManager(PokerRoom),
            "geo": RoomManager(GeoRoom),
            "flags": RoomManager(FlagsRoom),
        }
        self.chat = ChatStore(data_dir)
        self.avatars = AvatarStore(data_dir)
        # Xếp hạng "Vô địch ngày" của Xì Tố — sống qua restart trong cùng một
        # ngày (xem poker_board.py), khác hẳn self.managers["poker"] (RAM mất
        # khi tắt server). PokerRoom tự nó không ghi đĩa (nguyên tắc games.py:
        # luật chơi thuần, không I/O); nó chỉ gọi ``room.on_hand_end(net)`` mà
        # ta gắn thủ công mỗi khi tạo/lấy phòng, xem ``_wire_poker_room``.
        self.poker_board = PokerBoard(data_dir)
        # (channel, mã phòng) -> task đang chạy nước đi của máy. Có để không bao
        # giờ có hai task cùng đánh cho một phòng: mỗi lần broadcast lại gọi
        # schedule_bot(), mà một ván chỉ được có một tay nghĩ.
        self.bot_tasks: dict[tuple[str, str], asyncio.Task] = {}
        # Giới hạn số lượt tìm kiếm chạy cùng lúc. Tìm kiếm là CPU đặc và Python
        # giữ GIL, nên 5 ván cờ cùng nghĩ sẽ làm chat của cả đội giật. Xếp hàng
        # còn hơn để tất cả cùng chậm.
        try:
            bot_concurrency = max(1, int(os.environ.get("BOT_CONCURRENCY", "2")))
        except ValueError:
            bot_concurrency = 2
        self.bot_slots = asyncio.Semaphore(bot_concurrency)
        # uid -> {name, color} mới nhất, còn sống qua mọi lần disconnect/restart
        # (không mất khi người dùng rời trang, khác với Session chỉ tồn tại
        # trong lúc kết nối). Dùng để chat hiển thị tên/màu MỚI NHẤT của người
        # gửi trên toàn bộ lịch sử, kể cả tin nhắn gửi từ rất lâu, thay vì tên
        # cũ đóng băng lúc gửi. Avatar không cần trong directory này vì
        # AvatarStore đã tự tra được theo uid, không phụ thuộc session.
        self.directory = ProfileStore(data_dir)

    # ---- gửi tin ----------------------------------------------------------- #
    async def send(self, session: Session, payload: dict) -> bool:
        try:
            await session.sock.send_json(payload)
            return True
        except Exception:
            return False

    async def send_error(self, session: Session, channel: str, message: str) -> None:
        await self.send(session, {"ch": channel, "t": "error", "message": message})

    async def fan_out(self, sessions, payload_for) -> None:
        """Gửi cho nhiều người, mỗi người một payload riêng nếu cần."""
        for session in list(sessions):
            payload = payload_for(session)
            if payload is not None:
                await self.send(session, payload)

    # ---- danh tính, presence ----------------------------------------------- #
    def presence(self) -> list[dict]:
        """Danh sách người online, gộp các tab của cùng một người."""
        seen: dict[str, dict] = {}
        for session in self.sessions.values():
            entry = seen.setdefault(session.uid, {
                "uid": session.uid, "name": session.name, "color": session.color,
                "avatar": session.avatar, "app": session.app, "tabs": 0,
                "since": session.joined,
            })
            entry["tabs"] += 1
            entry["since"] = min(entry["since"], session.joined)
            if session.app != "home":
                entry["app"] = session.app       # ưu tiên hiện app đang dùng thật
        return sorted(seen.values(), key=lambda u: u["name"].lower())

    async def broadcast_presence(self) -> None:
        users = self.presence()
        await self.fan_out(self.sessions.values(),
                           lambda s: {"ch": "hub", "t": "presence", "users": users})

    async def register(self, sock, uid: str, name: str) -> Session:
        session = Session(sock=sock, uid=uid, name=clean_name(name), color=color_for(uid),
                          avatar=self.avatars.url(uid))
        self.sessions[sock] = session
        await asyncio.to_thread(self.directory.update, session.uid, session.name, session.color)
        await self.send(session, {
            "ch": "hub", "t": "welcome",
            "you": {"uid": session.uid, "name": session.name, "color": session.color,
                    "avatar": session.avatar},
            "apps": APPS,
            "reactions": list(REACTIONS),
            "directory": self.directory.snapshot(self.avatars),
        })
        await self.send_chat_channels(session)
        await self.broadcast_presence()
        return session

    async def unregister(self, sock) -> None:
        session = self.sessions.pop(sock, None)
        if session is None:
            return
        # Chỉ báo rời phòng khi người này không còn tab nào khác đang mở.
        still_here = any(s.uid == session.uid for s in self.sessions.values())
        for channel in GAME_CHANNELS:
            code = session.rooms.get(channel)
            if not code:
                continue
            room = self.managers[channel].get(code)
            if room is None:
                continue
            if not still_here:
                room.disconnect(session.uid)
            await self.broadcast_room(channel, code)
        await self.broadcast_presence()

    # ---- Xì Tố: gắn callback ghi bảng xếp hạng --------------------------- #
    def _wire_poker_room(self, room) -> None:
        """Gắn hook ghi leaderboard vào một PokerRoom, nếu chưa gắn.

        PokerRoom chủ động không tự ghi đĩa (xem poker.py: luật chơi thuần,
        test được không cần filesystem) — nó chỉ gọi
        ``self.on_hand_end(net_by_uid)`` sau mỗi ván nếu thuộc tính đó tồn
        tại. Hub là nơi duy nhất biết tên/màu hiện tại của từng uid
        (``self.directory``), nên khớp tên cho leaderboard cũng làm ở đây.
        """
        if getattr(room, "on_hand_end", None) is not None:
            return

        def on_hand_end(net_by_uid: dict[str, int]) -> None:
            names = {uid: self.directory.data.get(uid, {}) for uid in net_by_uid}
            self.poker_board.record(net_by_uid, names)

        room.on_hand_end = on_hand_end
        # Ảnh đại diện người dùng tự tải lên (Cài đặt / Tạo avatar) hiện ngay
        # trên ghế — PokerRoom không tự biết AvatarStore nên hỏi qua hook này.
        room.avatar_for = self.avatars.url

    # ---- phòng game -------------------------------------------------------- #
    def room_sessions(self, channel: str, code: str):
        return [s for s in self.sessions.values() if s.rooms.get(channel) == code]

    async def broadcast_room(self, channel: str, code: str) -> None:
        room = self.managers[channel].get(code)
        peers = self.room_sessions(channel, code)
        if room is None:
            await self.fan_out(peers, lambda s: {"ch": channel, "t": "closed"})
            return
        if getattr(room, "avatar_for", None) is None:
            room.avatar_for = self.avatars.url
        await self.fan_out(peers, lambda s: {"ch": channel, "t": "state", **room.view(s.uid)})
        # Gọi sau khi phát trạng thái: người chơi thấy nước của mình trước, rồi
        # mới tới lượt máy nghĩ.
        self.schedule_bot(channel, code)

    # ---- máy chơi đơn ------------------------------------------------------ #
    def schedule_bot(self, channel: str, code: str) -> None:
        """Khởi động vòng lặp máy nếu phòng có máy và chưa có task nào chạy."""
        key = (channel, code)
        task = self.bot_tasks.get(key)
        if task is not None and not task.done():
            return
        room = self.managers[channel].get(code)
        if room is None or not room.bot_players():
            self.bot_tasks.pop(key, None)
            return
        # Không kiểm bot_should_act() ở đây: sau khi ván xong máy vẫn còn việc
        # (tự đồng ý đánh lại), vòng lặp bên dưới tự quyết định khi nào thoát.
        self.bot_tasks[key] = asyncio.create_task(self._bot_loop(channel, code))

    async def _bot_loop(self, channel: str, code: str) -> None:
        """Đánh thay máy tới khi hết việc.

        Điểm sống còn: phần tính nước đi chạy ở thread khác qua ``to_thread``.
        Trong lúc đó event loop VẪN xử lý gói tin của người chơi, nên bàn có thể
        đã đổi khi máy tính xong (người xin thua, rời ghế, xin đánh lại...).
        Vì vậy phải chụp ``progress_token`` trước khi nghĩ và so lại sau khi
        nghĩ; lệch thì bỏ nước vừa tính và vòng lại. Không có bước này thì máy
        sẽ đi một nước tính trên bàn cũ.
        """
        manager = self.managers[channel]
        try:
            for _step in range(BOT_MAX_STEPS):
                room = manager.get(code)
                if room is None:
                    return
                if not room.bot_players():
                    return

                # Ván xong: máy luôn sẵn sàng đánh lại, nhưng chỉ sau khi người
                # chơi bấm — không tự đòi chơi tiếp. Bàn Sòng Bịp có tới ba máy,
                # nên vòng lặp này bấm hộ từng máy một, mỗi vòng một phiếu.
                if room.status == "finished":
                    voter = room.bot_to_vote()
                    if voter is not None:
                        await asyncio.sleep(0.5)
                        with contextlib.suppress(GameError):
                            room.vote_rematch(voter.uid)
                        await self.broadcast_room(channel, code)
                        # PHẢI vòng lại, không được return: phiếu của máy vừa
                        # làm ván mới bắt đầu, mà ván mới có thể tới lượt máy đi
                        # trước (cờ vua/cờ tướng đổi màu sau mỗi ván). Return ở
                        # đây thì không còn ai đánh thức máy nữa — broadcast vừa
                        # gọi schedule_bot nhưng task này còn sống nên nó bỏ qua.
                        continue
                    return

                # Hỏi phòng "giờ tới máy nào" thay vì giả định chỉ có một máy:
                # bàn nhiều ghế đi lần lượt Tư Lì -> Cô Ba -> Lão Sáu trong cùng
                # một vòng lặp.
                bot = room.bot_to_act()
                if bot is None:
                    return
                # Không còn người nào kết nối thì thôi, khỏi đánh với chính mình.
                if not room.has_connection():
                    return

                engine = bots.make_bot(channel, bot.level)
                before = room.progress_token()
                try:
                    async with self.bot_slots:
                        moves = await asyncio.to_thread(engine.actions, room, bot.mark)
                except bots.BotError:
                    return
                except Exception:
                    # Lỗi trong engine không được làm sập hub hay treo phòng.
                    return

                await asyncio.sleep(engine.think_delay)

                room = manager.get(code)
                if room is None or room.bot_player() is None:
                    return
                if room.progress_token() != before:
                    continue        # bàn đã đổi trong lúc nghĩ, tính lại

                acted = False
                for action, payload in moves or ():
                    try:
                        room.handle(bot.uid, action, payload)
                        acted = True
                    except GameError:
                        # Nước không hợp lệ: bỏ phần còn lại, vòng sau tính lại
                        # trên bàn mới nhất.
                        break
                if acted:
                    await self.broadcast_room(channel, code)
                if not acted:
                    return
        except asyncio.CancelledError:
            raise
        finally:
            # Chỉ dọn ô của CHÍNH task này, không xoá task mới ai đó vừa đặt vào.
            key = (channel, code)
            if self.bot_tasks.get(key) is asyncio.current_task():
                self.bot_tasks.pop(key, None)

    async def leave_game(self, session: Session, channel: str) -> None:
        code = session.rooms.pop(channel, None)
        if not code:
            return
        room = self.managers[channel].get(code)
        if room is not None:
            others = [s for s in self.room_sessions(channel, code) if s.uid == session.uid]
            if not others:
                room.disconnect(session.uid)
            await self.broadcast_room(channel, code)

    async def handle_game(self, session: Session, channel: str, kind: str, msg: dict) -> None:
        manager = self.managers[channel]

        if kind == "join":
            room = manager.get(str(msg.get("room", "")))
            if room is None:
                await self.send(session, {"ch": channel, "t": "closed",
                                          "message": "Phòng không tồn tại hoặc đã đóng."})
                return
            if channel == "poker":
                self._wire_poker_room(room)
            elif getattr(room, "avatar_for", None) is None:
                room.avatar_for = self.avatars.url
            if session.rooms.get(channel) != room.code:
                await self.leave_game(session, channel)
            session.rooms[channel] = room.code
            session.app = channel
            room.join(session.uid, session.name, session.color)
            await self.broadcast_room(channel, room.code)
            await self.broadcast_presence()
            return

        if kind == "leave":
            await self.leave_game(session, channel)
            session.app = "home"
            await self.broadcast_presence()
            return

        code = session.rooms.get(channel)
        room = manager.get(code) if code else None
        if room is None:
            await self.send_error(session, channel, "Bạn chưa ở trong phòng nào.")
            return

        uid = session.uid
        if kind == "sit":
            room.sit(uid)
        elif kind == "stand":
            room.stand(uid)
        elif kind == "resign":
            room.resign(uid)
        elif kind == "rematch":
            room.vote_rematch(uid)
        elif kind == "say":
            room.say(uid, str(msg.get("text", "")))
        else:
            room.handle(uid, kind, msg)
        await self.broadcast_room(channel, code)

    # ---- chat -------------------------------------------------------------- #
    async def send_chat_channels(self, session: Session) -> None:
        await self.send(session, {"ch": "chat", "t": "channels",
                                  "channels": self.chat.channel_list(session.uid)})

    async def broadcast_chat_channels(self) -> None:
        """Danh sách kênh khác nhau theo từng người vì số tin chưa đọc là riêng."""
        await self.fan_out(self.sessions.values(), lambda s: {
            "ch": "chat", "t": "channels",
            "channels": self.chat.channel_list(s.uid)})

    async def notify_message(self, sender: Session, room: str, message: dict) -> None:
        """Đẩy thông báo "có tin nhắn mới" cho mọi người trừ chính người gửi.

        Gói tin này đi trên channel "hub" (không phải "chat") có chủ ý: người
        đang ở Cờ vua hay Xuất dữ liệu vẫn phải nhận được, mà view chat của họ
        thì không hề được mount.

        Server KHÔNG tự quyết định ai nên thấy thông báo. Nó chỉ biết người đó
        đang mở app nào, chứ không biết tab có đang hiện hay đã bị ẩn, cũng
        không biết người dùng đã tắt thông báo hay chưa. Client có đủ dữ kiện
        đó nên phần lọc nằm ở client (notify.js).
        """
        notice = {
            "ch": "hub", "t": "notify", "kind": "chat",
            "id": message["id"],
            "room": room,
            "roomTitle": self.chat.channel_title(room),
            "uid": sender.uid,
            "name": sender.name,
            "color": sender.color,
            "avatar": self.avatars.url(sender.uid),
            "text": self.chat.preview_of(message),
            "ts": message["ts"],
        }
        await self.fan_out([s for s in self.sessions.values() if s.uid != sender.uid],
                           lambda s: notice)

    async def handle_chat(self, session: Session, kind: str, msg: dict) -> None:
        store = self.chat

        if kind == "join":
            name = store.ensure(str(msg.get("room", "chung")))
            session.rooms["chat"] = name
            session.app = "chat"
            await asyncio.to_thread(store.mark_read, session.uid, name)
            await self.send(session, {"ch": "chat", "t": "history", "room": name,
                                      "messages": store.history(name)})
            await self.send_chat_channels(session)
            await self.broadcast_presence()
            return

        if kind == "leave":
            session.rooms.pop("chat", None)
            session.app = "home"
            await self.broadcast_presence()
            return

        if kind == "channels":
            await self.send_chat_channels(session)
            return

        if kind == "create":
            info = await asyncio.to_thread(store.create_channel, str(msg.get("title", "")))
            await self.broadcast_chat_channels()
            await self.send(session, {"ch": "chat", "t": "created", "room": info["name"]})
            return

        room = session.rooms.get("chat")
        if not room:
            await self.send_error(session, "chat", "Bạn chưa mở kênh nào.")
            return

        author = {"uid": session.uid, "name": session.name, "color": session.color}

        if kind == "say":
            file_info = msg.get("file") if isinstance(msg.get("file"), dict) else {}
            message = await asyncio.to_thread(
                store.post, room, author, str(msg.get("text", "")),
                str(msg.get("image", "")), str(msg.get("replyTo", "")),
                str(file_info.get("id", "")), str(file_info.get("name", "")),
            )
            await asyncio.to_thread(store.mark_read, session.uid, room)
            await self.fan_out(
                [s for s in self.sessions.values() if s.rooms.get("chat") == room],
                lambda s: {"ch": "chat", "t": "message", "message": message})
            # Người đang ở app khác cũng cần thấy badge chưa đọc nhảy lên.
            await self.broadcast_chat_channels()
            await self.notify_message(session, room, message)
            return

        if kind == "react":
            message = await asyncio.to_thread(
                store.react, room, str(msg.get("id", "")), session.uid,
                str(msg.get("emoji", "")),
            )
            await self.fan_out(
                [s for s in self.sessions.values() if s.rooms.get("chat") == room],
                lambda s: {"ch": "chat", "t": "update", "message": message})
            return

        if kind == "delete":
            message = await asyncio.to_thread(
                store.delete, room, str(msg.get("id", "")), session.uid,
            )
            await self.fan_out(
                [s for s in self.sessions.values() if s.rooms.get("chat") == room],
                lambda s: {"ch": "chat", "t": "update", "message": message})
            await self.broadcast_chat_channels()
            return

        if kind == "typing":
            await self.fan_out(
                [s for s in self.sessions.values()
                 if s.rooms.get("chat") == room and s.uid != session.uid],
                lambda s: {"ch": "chat", "t": "typing",
                           "name": session.name, "uid": session.uid})
            return

        if kind == "read":
            await asyncio.to_thread(store.mark_read, session.uid, room)
            await self.send_chat_channels(session)
            return

        raise ChatError("Hành động không hợp lệ.")

    # ---- định tuyến -------------------------------------------------------- #
    async def dispatch(self, session: Session, msg: dict) -> None:
        channel = str(msg.get("ch", ""))
        kind = str(msg.get("t", ""))

        if channel == "hub":
            if kind == "ping":
                await self.send(session, {"ch": "hub", "t": "pong"})
            elif kind == "rename":
                session.name = clean_name(str(msg.get("name", "")))
                await asyncio.to_thread(self.directory.update, session.uid, session.name, session.color)
                for game_channel in GAME_CHANNELS:
                    code = session.rooms.get(game_channel)
                    room = self.managers[game_channel].get(code) if code else None
                    if room and session.uid in room.players:
                        room.players[session.uid].name = session.name
                        await self.broadcast_room(game_channel, code)
                await self.send(session, {"ch": "hub", "t": "welcome",
                                          "you": {"uid": session.uid, "name": session.name,
                                                  "color": session.color},
                                          "apps": APPS})
                await self.broadcast_presence()
                # Đổi tên phải cập nhật ngay trên MỌI lịch sử chat đang mở ở
                # máy người khác, không chỉ presence — nên phát directory mới
                # cho tất cả, không riêng người vừa đổi tên.
                await self.fan_out(self.sessions.values(), lambda s: {
                    "ch": "hub", "t": "directory",
                    "directory": self.directory.snapshot(self.avatars)})
            elif kind == "app":
                session.app = str(msg.get("app", "home"))[:20]
                await self.broadcast_presence()
            elif kind == "avatar":
                # Server đã lưu ảnh qua HTTP trước đó (POST /api/avatar); gói
                # tin này chỉ đồng bộ session hiện tại + mọi người xem presence.
                session.avatar = self.avatars.url(session.uid)
                await self.send(session, {"ch": "hub", "t": "welcome",
                                          "you": {"uid": session.uid, "name": session.name,
                                                  "color": session.color,
                                                  "avatar": session.avatar},
                                          "apps": APPS})
                await self.broadcast_presence()
                # Avatar đổi phải hiện ngay trên lịch sử chat cũ và phòng game
                # mà người này đang ngồi (Sòng Bịp, Xì Tố...).
                await self.fan_out(self.sessions.values(), lambda s: {
                    "ch": "hub", "t": "avatar-changed",
                    "uid": session.uid, "avatar": session.avatar})
                for ch, room_code in list(session.rooms.items()):
                    if ch in GAME_CHANNELS:
                        await self.broadcast_room(ch, room_code)
            return

        try:
            if channel in GAME_CHANNELS:
                await self.handle_game(session, channel, kind, msg)
            elif channel == "chat":
                await self.handle_chat(session, kind, msg)
        except (GameError, ChatError) as exc:
            await self.send_error(session, channel, str(exc))
        except (TypeError, ValueError, KeyError):
            await self.send_error(session, channel, "Dữ liệu không hợp lệ.")
        except Exception:
            traceback.print_exc()
            await self.send_error(session, channel, "Lỗi nội bộ khi xử lý thao tác.")

    # ---- đồng hồ của phòng ------------------------------------------------- #
    async def tick_loop(self, every: float = TICK_EVERY) -> None:
        """Đẩy đồng hồ của những phòng có hạn thời gian.

        Chỉ Sòng Bịp cần: nó đếm lùi 30 giây mỗi lượt và có chuỗi pha lật quân ->
        xoay ổ đạn -> nổ súng, mỗi pha một mốc thời gian để client kịp chạy
        animation. Các game khác đặt ``HAS_CLOCK = False`` nên bị bỏ qua hoàn
        toàn ở vòng lặp này, không tốn gì.
        """
        while True:
            await asyncio.sleep(every)
            with contextlib.suppress(Exception):
                await self._tick_once()

    async def _tick_once(self) -> None:
        for channel, manager in self.managers.items():
            if not getattr(manager.room_class, "HAS_CLOCK", False):
                continue
            # list() vì broadcast có thể làm phòng bị xoá giữa lúc đang lặp.
            for code, room in list(manager.rooms.items()):
                # Phòng không còn ai xem thì đóng băng, không để máy tự đấu với
                # nhau tới hết ván trong một phòng vắng.
                if not room.has_connection():
                    continue
                if room.tick():
                    await self.broadcast_room(channel, code)

    # ---- dọn phòng chết ---------------------------------------------------- #
    async def prune_loop(self, every: float = 120.0, idle: float = 1800.0) -> None:
        while True:
            await asyncio.sleep(every)
            with contextlib.suppress(Exception):
                for manager in self.managers.values():
                    manager.prune(idle)
