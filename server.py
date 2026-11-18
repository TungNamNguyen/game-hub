"""Game Hub — nền tảng nhiều ứng dụng và trò chơi realtime.

Chạy:  python server.py
Rồi mở địa chỉ server in ra (hoặc qua reverse proxy HTTPS khi host online).

Gồm:
  - Trang chủ: ai đang online, phòng đang mở
  - Chat nhóm: nhiều kênh, emoji, gửi ảnh, biểu cảm, trả lời, thông báo tin mới
  - Cờ caro / XO: bàn từ 3x3 tới 50x50
  - Cờ vua: đủ luật (nhập thành, bắt tốt qua đường, phong cấp, chiếu hết)
  - Cờ tướng: đủ luật (chân mã, mắt tượng, ngòi pháo, cấm lộ mặt tướng)
  - Bắn tàu: 10x10, 5 tàu
  - Sòng Bịp: game bịp 2-4 người, đặt úp quân rồi nói dối, bị bắt thì xoay ổ đạn
  - Xì Tố (Texas Hold'em): 2-6 người, bàn cash & giải đấu
  - Địa Đồ (GeoGuessr): đoán tọa độ 360° toàn cầu & Việt Nam
  - Tạo avatar: sinh mặt người ngẫu nhiên, dùng luôn làm ảnh đại diện
  - Chơi đơn với máy ở các game hỗ trợ

An toàn:
  * Hub vào chơi ngay không cần tài khoản mật khẩu; chống giả mạo uid qua token
    bí mật gắn với từng trình duyệt.
  * Hub không đọc ổ đĩa của máy host và không có API duyệt file. Nó chỉ ghi vào
    đúng thư mục data/ bên cạnh file này (hoặc PostgreSQL + HF Dataset).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import os
import secrets
import socket
import time
import urllib.parse
import urllib.request
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import avatar as av
import bots
import db
import hf_sync
from chat import FILE_UPLOAD_MAX_BYTES, UPLOAD_MAX_BYTES, ChatError
from flags_quiz import COUNTRIES as FLAGS_COUNTRIES
from games import GameError, is_bot_uid
from hub import APPS, Hub

HOST = "0.0.0.0"
# Trên Cloud (Hugging Face Spaces, Render, Koyeb...), nền tảng truyền cổng qua
# biến PORT và tự bọc HTTPS ở lớp proxy ngoài.
HTTP_PORT = int(os.environ.get("PORT", "8780"))

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

# Kết nối Postgres (nếu có DATABASE_URL), chuyển dữ liệu cũ (nếu DB trống)
# và tải avatars từ HF Dataset TRƯỚC khi Hub đọc đĩa.
db.init()
hf_sync.migrate_legacy_to_db(DATA_DIR)
hf_sync.restore_data(DATA_DIR, skip_json=db.is_enabled())

hub = Hub(DATA_DIR)


# --------------------------------------------------------------------------- #
# vòng đời
# --------------------------------------------------------------------------- #
def lan_addresses() -> list[str]:
    found: set[str] = set()
    # Nối UDP tới địa chỉ dải TEST-NET không gửi packet nào, chỉ để hệ điều hành
    # cho biết card mạng nào đang là đường ra mặc định.
    with contextlib.suppress(OSError):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            found.add(probe.getsockname()[0])
        finally:
            probe.close()
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    return sorted(ip for ip in found if not ip.startswith("127."))


def banner() -> str:
    lines = ["", "  GAME HUB da chay.", f"    May nay:  http://127.0.0.1:{HTTP_PORT}"]
    addresses = lan_addresses()
    for ip in addresses:
        lines.append(f"    LAN:      http://{ip}:{HTTP_PORT}")
    if db.is_enabled():
        lines.append("  Database: da ket noi Supabase Postgres.")
    if hf_sync.is_enabled():
        mode = "media only + lazy-load" if db.is_enabled() else "full + debounce"
        lines.append(f"  Dong bo anh/du lieu: Hugging Face Dataset ({mode}).")

    lines += ["", f"  Du lieu chat va anh: {DATA_DIR}", "  Dung server: Ctrl+C", ""]
    return "\n".join(lines)


def quiet_reset_errors(loop: asyncio.AbstractEventLoop) -> None:
    """Chặn traceback rác của asyncio trên Windows khi người dùng tắt tab.

    Windows trả WinError 10054 và asyncio in cả traceback từ trong transport của
    nó. Đó là chuyện bình thường, không phải lỗi server.
    """
    def handler(active_loop, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
            return
        active_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def keepalive_target() -> str:
    """URL công khai dùng để tự ping /healthz (hỗ trợ Render không bị sleep sớm)."""
    if os.environ.get("DISABLE_KEEPALIVE", "").lower() in ("1", "true", "yes"):
        return ""
    base = (os.environ.get("KEEPALIVE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return base if base.endswith("/healthz") else f"{base}/healthz"


async def keepalive_loop() -> None:
    """Ping định kỳ ra URL công khai để giữ kết nối trên Render Free."""
    target = keepalive_target()
    if not target:
        return
    try:
        interval = max(60, int(os.environ.get("KEEPALIVE_INTERVAL", "600")))
    except ValueError:
        interval = 600

    def _ping() -> None:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={"User-Agent": "GameHub-KeepAlive/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read(64)

    # Chờ vài giây sau khi server lên rồi mới chạy chu kỳ ping.
    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_ping)


@asynccontextmanager
async def lifespan(_: FastAPI):
    quiet_reset_errors(asyncio.get_running_loop())
    background = [
        asyncio.create_task(hub.prune_loop()),
        # Đồng hồ phòng: Sòng Bịp và Địa Đồ đếm lùi thời gian, đẩy chuyển pha tự động.
        asyncio.create_task(hub.tick_loop()),
        asyncio.create_task(rt_reaper_loop()),
        asyncio.create_task(hf_sync.sync_loop(DATA_DIR, skip_json=db.is_enabled())),
        asyncio.create_task(keepalive_loop()),
    ]
    print(banner(), flush=True)
    try:
        yield
    finally:
        for task in background:
            task.cancel()
        for task in background:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        hub.poker_board.close()
        db.close()


class SmartGZipMiddleware(GZipMiddleware):
    """Không nén luồng realtime /api/rt/* để tránh giữ buffer làm trễ SSE."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/rt/"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app = FastAPI(title="Game Hub", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SmartGZipMiddleware, minimum_size=512)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # nosniff quan trọng với ảnh do người dùng tải lên: chặn trình duyệt tự đoán
    # lại kiểu nội dung rồi thực thi nó.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    path = request.url.path
    if path.startswith("/api/") or path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/uploads/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/avatars/"):
        response.headers["Cache-Control"] = "public, max-age=604800"
    elif path.startswith("/static/"):
        # JS/CSS đổi thường xuyên trong giai đoạn phát triển; nếu trình duyệt
        # cache bản cũ, người dùng thấy UI cũ dù server đã có code mới (từng
        # gây lỗi avatar "không bấm được" vì JS cũ chưa có tính năng đó).
        # no-cache vẫn cho cache nhưng LUÔN phải revalidate (If-None-Match)
        # trước khi dùng, nên vẫn nhanh (304) mà không bao giờ phục vụ đồ cũ.
        response.headers["Cache-Control"] = "no-cache"
    return response


# --------------------------------------------------------------------------- #
# WebSocket + HTTP Realtime Fallback (SSE & Long-Polling cho mạng doanh nghiệp)
# --------------------------------------------------------------------------- #
RT_POLL_TIMEOUT = 20.0
RT_SSE_PING_EVERY = 15.0
RT_SESSION_TTL = 35.0


class HttpSessionSock:
    """Socket ảo gắn vào Hub cho client chạy qua SSE / HTTP Long-Polling."""

    def __init__(self, sid: str, uid: str, name: str) -> None:
        self.sid = sid
        self.uid = uid
        self.name = name
        self.queue: deque[tuple[int, dict]] = deque(maxlen=250)
        self.next_seq = 1
        self.sent_seq = 0
        self.event = asyncio.Event()
        self.last_seen = time.monotonic()
        self.closed = False

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    async def send_json(self, payload: dict) -> None:
        if self.closed:
            raise RuntimeError("http session closed")
        seq = self.next_seq
        self.next_seq += 1
        self.queue.append((seq, payload))
        self.event.set()

    def ack(self, ack_seq: int) -> None:
        if ack_seq <= 0:
            return
        while self.queue and self.queue[0][0] <= ack_seq:
            self.queue.popleft()

    def collect_since(self, cursor: int) -> tuple[int, list[dict]]:
        """Lấy các gói có seq > cursor và cập nhật sent_seq."""
        msgs = [item for seq, item in self.queue if seq > cursor]
        top = self.queue[-1][0] if self.queue else self.sent_seq
        if top > self.sent_seq:
            self.sent_seq = top
        self.event.clear()
        return self.sent_seq, msgs


http_sessions: dict[str, HttpSessionSock] = {}


def _validate_identity(uid: str, token: str) -> dict | None:
    """Trả về gói fatal nếu danh tính không hợp lệ, None nếu hợp lệ."""
    if not uid or len(uid) > 64:
        return {"ch": "hub", "t": "fatal", "message": "Thiếu mã người dùng."}
    if is_bot_uid(uid):
        return {"ch": "hub", "t": "fatal", "message": "Mã người dùng không hợp lệ."}
    if not hub.directory.verify_or_bind_token(uid, token):
        return {
            "ch": "hub",
            "t": "fatal",
            "code": "uid_conflict",
            "message": "Mã định danh đã thuộc về phiên khác, đang cấp lại mã mới…",
        }
    return None


async def _close_http_session(sid: str) -> None:
    sock = http_sessions.pop(sid, None)
    if sock is None:
        return
    sock.closed = True
    sock.event.set()
    await hub.unregister(sock)


async def rt_reaper_loop() -> None:
    """Tự động thu hồi phiên HTTP không còn poll/ping sau RT_SESSION_TTL giây."""
    while True:
        await asyncio.sleep(5.0)
        now = time.monotonic()
        expired = [
            sid for sid, sock in list(http_sessions.items())
            if now - sock.last_seen > RT_SESSION_TTL
        ]
        for sid in expired:
            with contextlib.suppress(Exception):
                await _close_http_session(sid)


class RtOpenBody(BaseModel):
    uid: str = ""
    name: str = ""
    token: str = ""


class RtSendBody(BaseModel):
    sid: str = ""
    ack: int = 0
    messages: list[dict] = []


class RtCloseBody(BaseModel):
    sid: str = ""


@app.post("/api/rt/open")
async def api_rt_open(payload: RtOpenBody):
    err = _validate_identity(payload.uid, payload.token)
    if err is not None:
        return {"ok": False, "fatal": err}

    sid = secrets.token_urlsafe(24)
    sock = HttpSessionSock(sid=sid, uid=payload.uid, name=payload.name)
    http_sessions[sid] = sock
    await hub.register(sock, payload.uid, payload.name)
    seq, msgs = sock.collect_since(0)
    return {"ok": True, "sid": sid, "seq": seq, "messages": msgs}


@app.get("/api/rt/poll")
async def api_rt_poll(request: Request, sid: str = "", ack: int = 0):
    sock = http_sessions.get(sid)
    if sock is None or sock.closed:
        raise HTTPException(404, "Phiên kết nối không tồn tại hoặc đã hết hạn.")

    sock.touch()
    sock.ack(ack)

    # Nếu client chưa nhận hết gói đã phát trước đó (ack < sent_seq), trả ngay.
    cursor = ack if ack < sock.sent_seq else sock.sent_seq
    seq, msgs = sock.collect_since(cursor)
    if msgs:
        return {"ok": True, "seq": seq, "messages": msgs}

    deadline = time.monotonic() + RT_POLL_TIMEOUT
    while not sock.closed:
        if await request.is_disconnected():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            await asyncio.wait_for(sock.event.wait(), timeout=min(remaining, 2.0))
        except asyncio.TimeoutError:
            sock.touch()
            continue
        seq, msgs = sock.collect_since(sock.sent_seq)
        if msgs:
            sock.touch()
            return {"ok": True, "seq": seq, "messages": msgs}

    sock.touch()
    return {"ok": True, "seq": sock.sent_seq, "messages": []}


@app.get("/api/rt/stream")
async def api_rt_stream(request: Request, sid: str = "", ack: int = 0):
    sock = http_sessions.get(sid)
    if sock is None or sock.closed:
        raise HTTPException(404, "Phiên kết nối không tồn tại hoặc đã hết hạn.")

    sock.touch()
    sock.ack(ack)

    async def event_gen():
        # Đệm 2KB comment lúc mở để ép một số proxy doanh nghiệp xả buffer ngay.
        yield ":" + (" " * 2048) + "\n\n"
        yield "event: ready\ndata: {}\n\n"

        cursor = ack if ack < sock.sent_seq else sock.sent_seq
        seq, initial_msgs = sock.collect_since(cursor)
        if initial_msgs:
            yield f"data: {json.dumps({'seq': seq, 'messages': initial_msgs}, ensure_ascii=False)}\n\n"

        last_ping = time.monotonic()
        while not sock.closed:
            if await request.is_disconnected():
                break
            try:
                await asyncio.wait_for(sock.event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                sock.touch()
                now = time.monotonic()
                if now - last_ping >= RT_SSE_PING_EVERY:
                    last_ping = now
                    yield ": ping\n\n"
                continue

            sock.touch()
            seq, msgs = sock.collect_since(sock.sent_seq)
            if msgs:
                yield f"data: {json.dumps({'seq': seq, 'messages': msgs}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/rt/send")
async def api_rt_send(payload: RtSendBody):
    sock = http_sessions.get(payload.sid)
    if sock is None or sock.closed:
        raise HTTPException(404, "Phiên kết nối không tồn tại hoặc đã hết hạn.")
    session = hub.sessions.get(sock)
    if session is None:
        raise HTTPException(404, "Phiên kết nối không tồn tại.")

    sock.touch()
    sock.ack(payload.ack)
    for msg in payload.messages:
        if isinstance(msg, dict):
            await hub.dispatch(session, msg)

    seq, msgs = sock.collect_since(sock.sent_seq)
    return {"ok": True, "seq": seq, "messages": msgs}


@app.post("/api/rt/close")
async def api_rt_close(request: Request):
    sid = ""
    with contextlib.suppress(Exception):
        raw = await request.body()
        if raw:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                sid = str(data.get("sid", ""))
    if sid:
        await _close_http_session(sid)
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(sock: WebSocket, uid: str = "", name: str = "", token: str = ""):
    await sock.accept()
    err = _validate_identity(uid, token)
    if err is not None:
        await sock.send_json(err)
        await sock.close()
        return

    session = await hub.register(sock, uid, name)
    try:
        while True:
            message = await sock.receive_json()
            if isinstance(message, dict):
                await hub.dispatch(session, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Client gửi rác hoặc mạng đứt giữa lúc đọc: coi như ngắt kết nối.
        pass
    finally:
        await hub.unregister(sock)


# --------------------------------------------------------------------------- #
# HTTP: sảnh chờ game
# --------------------------------------------------------------------------- #
class CreateRoom(BaseModel):
    channel: str = "caro"
    mode: str = ""
    level: str = bots.DEFAULT_LEVEL
    config: dict | None = None


def game_manager(channel: str):
    manager = hub.managers.get(channel)
    if manager is None:
        raise HTTPException(404, "Ứng dụng không tồn tại")
    return manager


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    """Endpoint nhẹ cho Render/UptimeRobot Health Check và dịch vụ ping giữ thức."""
    return {"ok": True, "db": db.ping() if db.is_enabled() else None}


@app.get("/api/apps")
def api_apps():
    return {"apps": APPS}


@app.get("/api/modes/{channel}")
def api_modes(channel: str):
    manager = game_manager(channel)
    room_class = manager.room_class
    return {"modes": [{"id": k, **v} for k, v in room_class.MODES.items()],
            "default": room_class.DEFAULT_MODE}


@app.get("/api/rooms")
def api_rooms():
    return {"rooms": {ch: mgr.lobby() for ch, mgr in hub.managers.items()},
            "online": len(hub.presence())}


@app.post("/api/rooms")
def api_create_room(payload: CreateRoom):
    manager = game_manager(payload.channel)
    try:
        return {"code": manager.create(payload.mode, config=payload.config).code}
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rooms/quick")
def api_quick_room(payload: CreateRoom):
    manager = game_manager(payload.channel)
    try:
        return {"code": manager.quick(payload.mode, config=payload.config).code}
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rooms/solo")
def api_solo_room(payload: CreateRoom):
    """Phòng chơi với máy. Máy ngồi sẵn một ghế, người tạo vào ghế còn lại."""
    manager = game_manager(payload.channel)
    if not bots.supports(payload.channel):
        raise HTTPException(400, "Game này chưa có máy để chơi đơn.")
    level = payload.level if payload.level in bots.LEVELS else bots.DEFAULT_LEVEL
    try:
        return {"code": manager.solo(payload.mode, level, config=payload.config).code, "level": level}
    except GameError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/bots")
def api_bots():
    return {"channels": bots.bot_channels(), "levels": bots.levels_info(),
            "default": bots.DEFAULT_LEVEL}


@app.get("/api/poker/leaderboard")
def api_poker_leaderboard():
    """Bảng \"Vô địch ngày\" của Xì Tố — net chip thắng trong ngày, theo uid."""
    rows = hub.poker_board.today_board(limit=10)
    for row in rows:
        row["avatar"] = hub.avatars.url(row["uid"])
    return {"board": rows}


@app.get("/api/flags/countries")
def api_flags_countries():
    """Danh sách rút gọn 197 quốc gia & thủ đô dùng làm gợi ý gõ nhanh phía client."""
    return {
        "countries": [
            {
                "code": c["code"],
                "continent": c["continent"],
                "nameVi": c["nameVi"],
                "nameEn": c["nameEn"],
                "capitalVi": c["capitalVi"],
                "capitalEn": c["capitalEn"],
            }
            for c in FLAGS_COUNTRIES
        ]
    }


# --------------------------------------------------------------------------- #
# HTTP: chat (kênh + ảnh)
# --------------------------------------------------------------------------- #
class NewChannel(BaseModel):
    title: str = ""


@app.get("/api/chat/channels")
def api_chat_channels(uid: str = ""):
    return {"channels": hub.chat.channel_list(uid)}


@app.post("/api/chat/channels")
def api_chat_create(payload: NewChannel):
    try:
        return hub.chat.create_channel(payload.title)
    except ChatError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chat/upload")
def api_chat_upload(file: UploadFile = File(...)):
    """Nhận ảnh.

    Hàm sync có chủ ý: FastAPI sẽ chạy nó trên threadpool, nên lúc Pillow
    re-encode một ảnh lớn thì event loop vẫn phục vụ được chat và game.
    Đọc quá hạn mức 1 byte để phát hiện file vượt cỡ mà không nạp hết vào RAM.
    """
    raw = file.file.read(UPLOAD_MAX_BYTES + 1)
    if len(raw) > UPLOAD_MAX_BYTES:
        raise HTTPException(413, f"Ảnh quá lớn, tối đa {UPLOAD_MAX_BYTES // (1024 * 1024)}MB.")
    try:
        return hub.chat.save_image(raw)
    except ChatError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/chat/upload-file")
def api_chat_upload_file(file: UploadFile = File(...)):
    """Nhận file đính kèm trong chat (tối đa 15MB)."""
    raw = file.file.read(FILE_UPLOAD_MAX_BYTES + 1)
    if len(raw) > FILE_UPLOAD_MAX_BYTES:
        raise HTTPException(
            413,
            f"File quá lớn, tối đa {FILE_UPLOAD_MAX_BYTES // (1024 * 1024)}MB.",
        )
    try:
        return hub.chat.save_file(raw, file.filename or "file")
    except ChatError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/uploads/file/{file_id}")
def api_download_file(file_id: str, name: str = ""):
    found = hub.chat.file_response(file_id, name)
    if found is None:
        raise HTTPException(404, "Không tìm thấy file")
    path, dl_name = found
    encoded = urllib.parse.quote(dl_name, safe="")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


@app.get("/uploads/{image_id}")
def api_image(image_id: str):
    found = hub.chat.image_response(image_id)
    if found is None:
        raise HTTPException(404, "Không tìm thấy ảnh")
    path, mime = found
    return FileResponse(path, media_type=mime,
                        headers={"Content-Disposition": "inline"})


# --------------------------------------------------------------------------- #
# HTTP: avatar
# --------------------------------------------------------------------------- #
@app.post("/api/avatar")
def api_avatar_upload(uid: str, token: str = "", file: UploadFile = File(...)):
    if not hub.directory.verify_or_bind_token(uid, token):
        raise HTTPException(403, "Không có quyền đổi ảnh đại diện của người khác.")
    raw = file.file.read(av.UPLOAD_MAX_BYTES + 1)
    if len(raw) > av.UPLOAD_MAX_BYTES:
        raise HTTPException(413, f"Ảnh quá lớn, tối đa {av.UPLOAD_MAX_BYTES // (1024 * 1024)}MB.")
    try:
        return {"url": hub.avatars.save(uid, raw)}
    except av.AvatarError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/avatar")
def api_avatar_delete(uid: str, token: str = ""):
    if not hub.directory.verify_or_bind_token(uid, token):
        raise HTTPException(403, "Không có quyền xóa ảnh đại diện của người khác.")
    hub.avatars.remove(uid)
    return {"ok": True}


@app.get("/avatars/{filename}")
def api_avatar_file(filename: str):
    uid = filename[:-4] if filename.endswith(".jpg") else filename
    path = hub.avatars.file_path(uid)
    if path is None:
        raise HTTPException(404, "Chưa có avatar")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Content-Disposition": "inline"})


# --------------------------------------------------------------------------- #
# frontend
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    entry = STATIC_DIR / "index.html"
    if not entry.exists():
        return JSONResponse({"detail": "Thieu static/index.html"}, status_code=500)
    return FileResponse(entry)


@app.get("/favicon.ico")
def favicon():
    """Nhiều thứ đi thẳng tới /favicon.ico mà không đọc <link> trong HTML:
    Safari cũ, Windows khi ghim trang, app chat lúc dán link xem trước. Trả
    đúng file thay vì 204 để chỗ nào cũng thấy logo."""
    path = STATIC_DIR / "favicon.ico"
    if not path.exists():
        # 204 bắt buộc không có body, nên không dùng JSONResponse ở đây.
        return Response(status_code=204)
    return FileResponse(path, media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})


# Windows registry hay map .js sang text/plain, làm trình duyệt từ chối ES
# module. Đặt lại kiểu đúng trước khi mount StaticFiles.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=HTTP_PORT, log_level="warning",
                ws_ping_interval=20)
