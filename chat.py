"""Ứng dụng chat của hub: nhiều kênh, emoji, gửi ảnh, reaction, trả lời.

Lịch sử được ghi ra đĩa (data/chat/*.jsonl) nên restart server không mất tin
nhắn — khác với game, chat là thứ người ta cần đọc lại.

An toàn khi nhận ảnh:
  - Chặn theo kích thước trước khi đọc hết vào RAM.
  - Mở bằng Pillow để xác nhận đây thật là ảnh, không tin phần mở rộng hay
    Content-Type do client khai.
  - Re-encode PNG/JPEG/WEBP để loại bỏ mọi thứ nhúng kèm (script, EXIF, payload
    dán sau phần ảnh). GIF giữ nguyên byte để không mất animation, nhưng vẫn
    phải qua Pillow xác thực.
  - SVG bị chặn hẳn: nó là XML và chạy được script.
  - Tên file do người dùng đặt không bao giờ được dùng làm tên file trên đĩa.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path

from PIL import Image

import db
import hf_sync

# Chặn ảnh kích thước pixel quá lớn gây tràn RAM khi giải mã (decompression bomb).
MAX_IMAGE_PIXELS = 25_000_000
MAX_SIDE_PX = 8192
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

TEXT_MAX = 4000
TITLE_MAX = 40
CHANNEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
HISTORY_IN_MEMORY = 400      # số tin nhắn giữ trong RAM mỗi kênh
HISTORY_ON_DISK = 4000       # quá mức này thì gọn file lại khi khởi động
SEND_COOLDOWN = 0.25         # giây, chặn spam

# ảnh & file đính kèm
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
FILE_UPLOAD_MAX_BYTES = 15 * 1024 * 1024
UPLOAD_MAX_TOTAL = 600 * 1024 * 1024
MAX_DIMENSION = 2000
ALLOWED_FORMATS = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}
MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg",
               "gif": "image/gif", "webp": "image/webp"}
BLOCKED_FILE_EXTS = {
    "exe", "bat", "cmd", "com", "msi", "scr", "pif", "vbs", "vbe",
    "ps1", "psm1", "hta", "cpl", "dll", "sys",
}
_IMAGE_SEMAPHORE = threading.Semaphore(2)

REACTIONS = (
    "👍", "👎", "❤️", "🔥", "😂", "🤣", "😍", "😮",
    "😢", "😭", "😡", "🎉", "💯", "🙏", "👏", "🫡",
    "🤔", "😎", "🤡", "💀", "🗿", "👑", "💎", "👀",
)

DEFAULT_CHANNELS = [
    ("chung", "Kênh chung"),
    ("cong-viec", "Công việc"),
    ("tam-phao", "Tám phào"),
]


class ChatError(Exception):
    """Lỗi hiển thị thẳng cho người dùng."""


def clean_text(raw: str, limit: int = TEXT_MAX) -> str:
    """Giữ được xuống dòng và emoji, chỉ bỏ ký tự điều khiển."""
    text = "".join(ch for ch in (raw or "")
                   if ch == "\n" or ch == "\t" or ch.isprintable())
    return text.strip()[:limit]


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: "Kênh Dự án" -> "Kenh Du an".

    NFD tách nguyên âm khỏi dấu để xoá dấu đi, nhưng đ/Đ không phải nguyên âm
    có dấu nên phải thay tay.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(raw: str) -> str:
    text = strip_accents((raw or "").strip()).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:24]


class ChatStore:
    """Toàn bộ trạng thái chat. Mọi thao tác đổi dữ liệu đều nằm trong lock vì
    endpoint upload chạy trên threadpool, không cùng luồng với WebSocket."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = data_dir
        self.chat_dir = data_dir / "chat"
        self.upload_dir = data_dir / "uploads"
        self.chat_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        self.lock = threading.Lock()
        self.channels: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.reads: dict[str, dict[str, float]] = {}     # uid -> kênh -> ts
        self.last_send: dict[str, float] = {}
        self._image_dims: dict[str, tuple[int, int]] = {}
        self._files_meta: dict[str, dict] = {}

        self._load()

    # ---- nạp / ghi --------------------------------------------------------- #
    @property
    def _meta_file(self) -> Path:
        return self.chat_dir / "channels.json"

    @property
    def _reads_file(self) -> Path:
        return self.chat_dir / "reads.json"

    def _load(self) -> None:
        if db.is_enabled():
            self._load_db()
            return

        meta = {}
        if self._meta_file.exists():
            try:
                meta = json.loads(self._meta_file.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        if self._reads_file.exists():
            try:
                self.reads = json.loads(self._reads_file.read_text(encoding="utf-8"))
            except Exception:
                self.reads = {}

        for name, title in DEFAULT_CHANNELS:
            meta.setdefault(name, {"title": title, "created": time.time()})

        for name, info in meta.items():
            if not CHANNEL_RE.match(name):
                continue
            self.channels[name] = {"name": name,
                                   "title": info.get("title") or name,
                                   "created": info.get("created", time.time())}
            self.messages[name] = self._read_log(name)
        self._save_meta()

    def _load_db(self) -> None:
        now = time.time()
        with db.connection() as conn:
            for name, title in DEFAULT_CHANNELS:
                conn.execute(
                    """
                    insert into public.channels (name, title, created_at)
                    values (%s, %s, %s)
                    on conflict (name) do nothing
                    """,
                    (name, title, now),
                )

            rows = conn.execute(
                "select name, title, created_at from public.channels"
            ).fetchall()
            for name, title, created_at in rows:
                if not CHANNEL_RE.match(name):
                    continue
                self.channels[name] = {
                    "name": name,
                    "title": title or name,
                    "created": float(created_at),
                }
                msg_rows = conn.execute(
                    """
                    select id, channel, uid, name, color, text, image, file,
                           reply_to, ts, reactions, deleted
                    from public.messages
                    where channel = %s
                    order by ts desc
                    limit %s
                    """,
                    (name, HISTORY_IN_MEMORY),
                ).fetchall()
                msgs = [
                    {
                        "id": r[0],
                        "channel": r[1],
                        "uid": r[2],
                        "name": r[3],
                        "color": r[4],
                        "text": r[5],
                        "image": r[6],
                        "file": r[7],
                        "replyTo": r[8],
                        "ts": float(r[9]),
                        "reactions": r[10] or {},
                        "deleted": bool(r[11]),
                    }
                    for r in reversed(msg_rows)
                ]
                self.messages[name] = msgs

            read_rows = conn.execute(
                "select uid, channel, last_read_ts from public.reads"
            ).fetchall()
            for uid, channel, last_read_ts in read_rows:
                self.reads.setdefault(uid, {})[channel] = float(last_read_ts)

    def _log_file(self, channel: str) -> Path:
        return self.chat_dir / f"{channel}.jsonl"

    def _read_log(self, channel: str) -> list[dict]:
        path = self._log_file(channel)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        if len(lines) > HISTORY_ON_DISK:
            # Gọn file lại một lần khi khởi động, không để nó phình mãi.
            lines = lines[-HISTORY_ON_DISK:]
            try:
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception:
                pass
        out = []
        for line in lines[-HISTORY_IN_MEMORY:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    def _append_log(self, channel: str, message: dict) -> None:
        try:
            with self._log_file(channel).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        except Exception:
            pass    # mất một dòng log không được làm sập chat

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            with contextlib.suppress(OSError):
                if tmp.exists():
                    tmp.unlink()

    def _rewrite_log(self, channel: str) -> None:
        """Ghi lại file an toàn (atomic) khi sửa/xóa tin nhắn cũ mà KHÔNG cắt mất lịch sử trên đĩa."""
        path = self._log_file(channel)
        by_id = {m["id"]: m for m in self.messages.get(channel, []) if isinstance(m, dict) and "id" in m}
        try:
            out_lines: list[str] = []
            seen: set[str] = set()
            if path.exists():
                for raw_line in path.read_text(encoding="utf-8").splitlines()[-HISTORY_ON_DISK:]:
                    if not raw_line.strip():
                        continue
                    try:
                        parsed = json.loads(raw_line)
                    except Exception:
                        continue
                    mid = parsed.get("id") if isinstance(parsed, dict) else None
                    if mid and mid in by_id:
                        out_lines.append(json.dumps(by_id[mid], ensure_ascii=False))
                        seen.add(mid)
                    else:
                        out_lines.append(raw_line)
            for msg in self.messages.get(channel, []):
                mid = msg.get("id")
                if mid and mid not in seen:
                    out_lines.append(json.dumps(msg, ensure_ascii=False))
                    seen.add(mid)
            self._atomic_write_text(path, ("\n".join(out_lines) + "\n") if out_lines else "")
        except Exception:
            pass

    def _save_meta(self) -> None:
        try:
            data = {name: {"title": info["title"], "created": info["created"]}
                    for name, info in self.channels.items()}
            self._atomic_write_text(
                self._meta_file,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        except Exception:
            pass

    def _save_reads(self) -> None:
        try:
            self._atomic_write_text(
                self._reads_file,
                json.dumps(self.reads, ensure_ascii=False),
            )
        except Exception:
            pass

    # ---- kênh -------------------------------------------------------------- #
    def ensure(self, channel: str) -> str:
        name = (channel or "chung").strip().lower()
        if name not in self.channels:
            raise ChatError("Kênh không tồn tại.")
        return name

    def create_channel(self, title: str) -> dict:
        clean_title = clean_text(title, TITLE_MAX) or "Kênh mới"
        name = slugify(clean_title)
        if not name or not CHANNEL_RE.match(name):
            raise ChatError("Tên kênh cần có chữ hoặc số không dấu.")
        created = time.time()
        with self.lock:
            if name in self.channels:
                raise ChatError("Kênh này đã có rồi.")
            if len(self.channels) >= 40:
                raise ChatError("Đã đạt giới hạn số kênh.")
            info = {"name": name, "title": clean_title, "created": created}
            if db.is_enabled():
                with db.connection() as conn:
                    conn.execute(
                        """
                        insert into public.channels (name, title, created_at)
                        values (%s, %s, %s)
                        """,
                        (name, clean_title, created),
                    )
            self.channels[name] = info
            self.messages[name] = []
            if not db.is_enabled():
                self._save_meta()
        return self.channels[name]

    def channel_list(self, uid: str) -> list[dict]:
        """Danh sách kênh kèm tin cuối và số tin chưa đọc của riêng ``uid``."""
        read_marks = self.reads.get(uid, {})
        out = []
        for name, info in self.channels.items():
            msgs = self.messages.get(name, [])
            visible = [m for m in msgs if not m.get("deleted")]
            last = visible[-1] if visible else None
            since = read_marks.get(name, 0)
            unread = sum(1 for m in visible if m["ts"] > since and m["uid"] != uid)
            out.append({
                "name": name,
                "title": info["title"],
                "unread": unread,
                "lastTs": last["ts"] if last else info["created"],
                "preview": self._preview(last) if last else "",
                "lastName": last["name"] if last else "",
            })
        out.sort(key=lambda c: -c["lastTs"])
        return out

    @staticmethod
    def _preview(message: dict) -> str:
        if message.get("image"):
            return "📷 Ảnh" + (f" · {message['text'][:40]}" if message.get("text") else "")
        if message.get("file"):
            fname = message["file"].get("name") or "File"
            return f"📎 {fname[:40]}" + (f" · {message['text'][:28]}" if message.get("text") else "")
        return (message.get("text") or "")[:60]

    # Bản công khai của _preview, dùng cho thông báo đẩy (hub.py). Cùng một
    # cách rút gọn nội dung với danh sách kênh, nên preview trong thông báo và
    # preview ở sidebar không bao giờ lệch nhau.
    preview_of = _preview

    def channel_title(self, channel: str) -> str:
        info = self.channels.get(channel)
        return info["title"] if info else channel

    def history(self, channel: str, limit: int = 200) -> list[dict]:
        name = self.ensure(channel)
        return self.messages[name][-limit:]

    def mark_read(self, uid: str, channel: str) -> None:
        name = self.ensure(channel)
        now = time.time()
        with self.lock:
            self.reads.setdefault(uid, {})[name] = now
            if db.is_enabled():
                with db.connection() as conn:
                    conn.execute(
                        """
                        insert into public.reads (uid, channel, last_read_ts)
                        values (%s, %s, %s)
                        on conflict (uid, channel)
                        do update set last_read_ts = excluded.last_read_ts
                        """,
                        (uid, name, now),
                    )
            else:
                self._save_reads()

    # ---- tin nhắn ---------------------------------------------------------- #
    def post(self, channel: str, author: dict, text: str,
             image_id: str = "", reply_to: str = "",
             file_id: str = "", file_name: str = "") -> dict:
        name = self.ensure(channel)
        body = clean_text(text)
        image = None
        attached_file = None

        # Lấy metadata ảnh/file bên ngoài self.lock để tránh giữ lock khi đọc đĩa hoặc tải lười từ HF.
        if image_id:
            image = self._image_meta(image_id)
            if image is None:
                raise ChatError("Ảnh không còn tồn tại.")
        if file_id:
            attached_file = self._file_meta(file_id, file_name)
            if attached_file is None:
                raise ChatError("File đính kèm không còn tồn tại.")

        with self.lock:
            if not body and image is None and attached_file is None:
                raise ChatError("Tin nhắn trống.")

            now = time.time()
            if now - self.last_send.get(author["uid"], 0) < SEND_COOLDOWN:
                raise ChatError("Gõ chậm thôi.")
            self.last_send[author["uid"]] = now

            reply = None
            if reply_to:
                target = next((m for m in self.messages[name] if m["id"] == reply_to), None)
                if target and not target.get("deleted"):
                    reply = {"id": target["id"], "uid": target["uid"], "name": target["name"],
                             "text": self._preview(target)}

            message = {
                "id": "m" + secrets.token_hex(8),
                "channel": name,
                "uid": author["uid"],
                "name": author["name"],
                "color": author.get("color", "#6366f1"),
                "text": body,
                "image": image,
                "file": attached_file,
                "replyTo": reply,
                "ts": now,
                "reactions": {},
                "deleted": False,
            }
            if db.is_enabled():
                with db.connection() as conn:
                    conn.execute(
                        """
                        insert into public.messages
                            (id, channel, uid, name, color, text, image, file, reply_to, ts, reactions, deleted)
                        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s)
                        """,
                        (
                            message["id"],
                            name,
                            message["uid"],
                            message["name"],
                            message["color"],
                            body,
                            json.dumps(image, ensure_ascii=False) if image is not None else None,
                            json.dumps(attached_file, ensure_ascii=False) if attached_file is not None else None,
                            json.dumps(reply, ensure_ascii=False) if reply is not None else None,
                            now,
                            "{}",
                            False,
                        ),
                    )
            else:
                self._append_log(name, message)
            self.messages[name].append(message)
            del self.messages[name][:-HISTORY_IN_MEMORY]
        return message

    def react(self, channel: str, message_id: str, uid: str, emoji: str) -> dict:
        name = self.ensure(channel)
        if emoji not in REACTIONS:
            raise ChatError("Biểu cảm không hợp lệ.")
        with self.lock:
            message = next((m for m in self.messages[name] if m["id"] == message_id), None)
            if message is None or message.get("deleted"):
                raise ChatError("Không tìm thấy tin nhắn.")
            users = message["reactions"].setdefault(emoji, [])
            if uid in users:
                users.remove(uid)         # bấm lần nữa là bỏ biểu cảm
                if not users:
                    message["reactions"].pop(emoji, None)
            else:
                users.append(uid)
            if db.is_enabled():
                with db.connection() as conn:
                    conn.execute(
                        "update public.messages set reactions = %s::jsonb where id = %s",
                        (json.dumps(message["reactions"], ensure_ascii=False), message_id),
                    )
            else:
                self._rewrite_log(name)
        return message

    def delete(self, channel: str, message_id: str, uid: str) -> dict:
        name = self.ensure(channel)
        with self.lock:
            message = next((m for m in self.messages[name] if m["id"] == message_id), None)
            if message is None:
                raise ChatError("Không tìm thấy tin nhắn.")
            if message["uid"] != uid:
                raise ChatError("Chỉ xóa được tin nhắn của mình.")
            message["deleted"] = True
            message["text"] = ""
            message["image"] = None
            message["file"] = None
            message["reactions"] = {}
            if db.is_enabled():
                with db.connection() as conn:
                    conn.execute(
                        """
                        update public.messages
                        set deleted = true, text = '', image = null, file = null, reactions = '{}'::jsonb
                        where id = %s
                        """,
                        (message_id,),
                    )
            else:
                self._rewrite_log(name)
        return message

    # ---- ảnh --------------------------------------------------------------- #
    @staticmethod
    def _valid_image_id(image_id: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{16,32}\.(png|jpg|gif|webp)", image_id or ""))

    def _upload_path(self, image_id: str) -> Path | None:
        """Đường dẫn của ảnh, hoặc None nếu id không hợp lệ.

        id chỉ được là hex + phần mở rộng đã biết, nên không có cách nào dựng
        được đường dẫn đi ra ngoài thư mục uploads.
        """
        if not self._valid_image_id(image_id):
            return None
        path = self.upload_dir / image_id
        if path.is_file():
            return path
        if hf_sync.is_enabled():
            return hf_sync.fetch_file(self.dir, f"uploads/{image_id}")
        return None

    def _image_meta(self, image_id: str) -> dict | None:
        if not self._valid_image_id(image_id):
            return None
        dims = self._image_dims.get(image_id)
        if dims is not None and (self.upload_dir / image_id).is_file():
            return {"id": image_id, "w": dims[0], "h": dims[1]}
        path = self._upload_path(image_id)
        if path is None:
            return None
        try:
            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            return None
        self._image_dims[image_id] = (width, height)
        return {"id": image_id, "w": width, "h": height}

    def _total_upload_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.upload_dir.glob("*") if p.is_file())

    def save_image(self, raw: bytes) -> dict:
        if not raw:
            raise ChatError("File rỗng.")
        if len(raw) > UPLOAD_MAX_BYTES:
            raise ChatError(f"Ảnh quá lớn, tối đa {UPLOAD_MAX_BYTES // (1024*1024)}MB.")

        with _IMAGE_SEMAPHORE:
            # Pillow là bên quyết định đây có phải ảnh hay không, không tin client.
            try:
                with Image.open(io.BytesIO(raw)) as probe:
                    pw, ph = probe.size
                    if pw <= 0 or ph <= 0 or pw > MAX_SIDE_PX or ph > MAX_SIDE_PX or (pw * ph) > MAX_IMAGE_PIXELS:
                        raise ChatError("Độ phân giải ảnh quá lớn (tối đa 25MP / 8192px).")
                    probe.verify()
                with Image.open(io.BytesIO(raw)) as img:
                    fmt = (img.format or "").upper()
                    width, height = img.size
                    if width <= 0 or height <= 0 or width > MAX_SIDE_PX or height > MAX_SIDE_PX or (width * height) > MAX_IMAGE_PIXELS:
                        raise ChatError("Độ phân giải ảnh quá lớn (tối đa 25MP / 8192px).")
                    mode = img.mode
                    animated = getattr(img, "n_frames", 1) > 1
            except ChatError:
                raise
            except Exception:
                raise ChatError("File này không phải ảnh hợp lệ.") from None

            if fmt not in ALLOWED_FORMATS:
                raise ChatError("Chỉ nhận PNG, JPG, GIF hoặc WEBP.")
            ext = ALLOWED_FORMATS[fmt]

            with self.lock:
                if self._total_upload_bytes() > UPLOAD_MAX_TOTAL:
                    raise ChatError("Kho ảnh đã đầy, nhờ admin dọn thư mục uploads.")

            if fmt == "GIF" and animated:
                # Re-encode sẽ làm mất animation. GIF không chứa được script nên
                # giữ nguyên byte sau khi Pillow đã xác thực là an toàn.
                data = raw
            else:
                data, width, height, ext = self._reencode(raw, fmt, ext)

        image_id = secrets.token_hex(12) + "." + ext
        (self.upload_dir / image_id).write_bytes(data)
        self._image_dims[image_id] = (width, height)
        hf_sync.enqueue_upload(self.dir, f"uploads/{image_id}")
        return {"id": image_id, "w": width, "h": height,
                "bytes": len(data), "format": fmt, "mode": mode}

    @staticmethod
    def _reencode(raw: bytes, fmt: str, ext: str) -> tuple[bytes, int, int, str]:
        """Vẽ lại ảnh từ pixel, bỏ hết metadata và mọi thứ dán kèm."""
        with Image.open(io.BytesIO(raw)) as img:
            if fmt == "JPEG":
                # Giải mã ở độ phân giải gần ngưỡng MAX_DIMENSION để tiết kiệm RAM.
                img.draft("RGB", (MAX_DIMENSION, MAX_DIMENSION))
            img.load()
            if max(img.size) > MAX_DIMENSION:
                img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
            buffer = io.BytesIO()
            if fmt == "JPEG":
                img.convert("RGB").save(buffer, format="JPEG", quality=86, optimize=True)
            elif fmt == "PNG":
                if img.mode in ("RGBA", "LA", "P"):
                    img.convert("RGBA").save(buffer, format="PNG", optimize=True)
                else:
                    # PNG không trong suốt (ảnh chụp màn hình/ảnh thường) chuyển sang WEBP
                    # nhẹ hơn nhiều và ít tốn CPU nén trên server.
                    img.convert("RGB").save(buffer, format="WEBP", quality=86)
                    ext = "webp"
            elif fmt == "WEBP":
                img.save(buffer, format="WEBP", quality=86)
            else:
                img.save(buffer, format="GIF")
            return buffer.getvalue(), img.size[0], img.size[1], ext

    def image_response(self, image_id: str) -> tuple[Path, str] | None:
        path = self._upload_path(image_id)
        if path is None:
            return None
        return path, MIME_BY_EXT[path.suffix.lstrip(".")]

    # ---- file đính kèm ----------------------------------------------------- #
    @staticmethod
    def _valid_file_id(file_id: str) -> bool:
        return bool(re.fullmatch(r"f_[0-9a-f]{16,32}(\.[a-z0-9]{1,12})?", file_id or ""))

    @staticmethod
    def _clean_filename(raw_name: str) -> tuple[str, str]:
        base = Path(str(raw_name or "file")).name
        cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '/\\<>:"|?*').strip()
        if not cleaned:
            cleaned = "file"
        cleaned = cleaned[:120]
        ext = Path(cleaned).suffix.lstrip(".").lower()
        ext = re.sub(r"[^a-z0-9]", "", ext)[:12]
        return cleaned, ext

    def _file_upload_path(self, file_id: str) -> Path | None:
        if not self._valid_file_id(file_id):
            return None
        path = self.upload_dir / file_id
        if path.is_file():
            return path
        if hf_sync.is_enabled():
            return hf_sync.fetch_file(self.dir, f"uploads/{file_id}")
        return None

    def _file_meta(self, file_id: str, fallback_name: str = "") -> dict | None:
        if not self._valid_file_id(file_id):
            return None
        cached = self._files_meta.get(file_id)
        if cached is not None and (self.upload_dir / file_id).is_file():
            return dict(cached)
        path = self._file_upload_path(file_id)
        if path is None:
            return None
        clean_name, ext = self._clean_filename(fallback_name or file_id)
        if not ext and path.suffix:
            ext = path.suffix.lstrip(".").lower()
        meta = {
            "id": file_id,
            "name": clean_name,
            "size": path.stat().st_size,
            "ext": ext,
        }
        self._files_meta[file_id] = meta
        return dict(meta)

    def save_file(self, raw: bytes, filename: str = "file") -> dict:
        if not raw:
            raise ChatError("File rỗng.")
        if len(raw) > FILE_UPLOAD_MAX_BYTES:
            raise ChatError(
                f"File quá lớn, tối đa {FILE_UPLOAD_MAX_BYTES // (1024 * 1024)}MB."
            )
        clean_name, ext = self._clean_filename(filename)
        if ext in BLOCKED_FILE_EXTS:
            raise ChatError("Không cho phép gửi định dạng file thực thi này.")

        with self.lock:
            if self._total_upload_bytes() > UPLOAD_MAX_TOTAL:
                raise ChatError("Kho lưu trữ đã đầy, nhờ admin dọn thư mục uploads.")

        file_id = f"f_{secrets.token_hex(12)}" + (f".{ext}" if ext else "")
        (self.upload_dir / file_id).write_bytes(raw)
        meta = {
            "id": file_id,
            "name": clean_name,
            "size": len(raw),
            "ext": ext,
        }
        self._files_meta[file_id] = meta
        hf_sync.enqueue_upload(self.dir, f"uploads/{file_id}")
        return meta

    def file_response(self, file_id: str, requested_name: str = "") -> tuple[Path, str] | None:
        path = self._file_upload_path(file_id)
        if path is None:
            return None
        meta = self._files_meta.get(file_id)
        name = (meta and meta.get("name")) or requested_name or file_id
        clean_name, _ = self._clean_filename(name)
        return path, clean_name
