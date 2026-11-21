"""Ảnh đại diện (avatar) của từng người dùng trong hub.

Khác với ảnh chat (mỗi ảnh một file mới, giữ vĩnh viễn trong lịch sử), avatar
chỉ có ĐÚNG MỘT file cho mỗi uid — đổi avatar là ghi đè, không tích lũy rác.

An toàn khi nhận ảnh: cùng nguyên tắc với chat.py —
  - Chặn theo kích thước trước khi đọc hết vào RAM.
  - Mở bằng Pillow để xác nhận đây thật là ảnh, không tin phần mở rộng hay
    Content-Type do client khai.
  - Luôn re-encode ra JPEG vuông, loại bỏ mọi thứ nhúng kèm (EXIF, script dán
    kèm, payload lạ). Không giữ nguyên byte gốc như GIF động ở chat, vì avatar
    không cần animation và luôn phải vuông + nhỏ.
  - uid dùng làm tên file phải qua kiểm tra định dạng (hub.py đã đảm bảo uid
    là uuid/chuỗi ngắn an toàn), không nhận trực tiếp từ nội dung do client gõ.
"""

from __future__ import annotations

import io
import re
import threading
import time
from pathlib import Path

from PIL import Image, ImageOps

import hf_sync

MAX_IMAGE_PIXELS = 25_000_000
MAX_SIDE_PX = 8192
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

UPLOAD_MAX_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 256                      # ảnh lưu vuông, cạnh này, đủ nét cho avatar lg (40px) x6
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_AVATAR_SEMAPHORE = threading.Semaphore(2)


class AvatarError(Exception):
    """Lỗi hiển thị thẳng cho người dùng."""


class AvatarStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.dir = data_dir / "avatars"
        self.dir.mkdir(parents=True, exist_ok=True)
        # uid -> "version" (mtime dạng int) để URL avatar đổi mỗi lần cập nhật,
        # nhờ vậy trình duyệt không cache nhầm ảnh cũ.
        self._versions: dict[str, int] = {}
        for path in self.dir.glob("*.jpg"):
            self._versions[path.stem] = int(path.stat().st_mtime)

    def _path(self, uid: str) -> Path:
        return self.dir / f"{uid}.jpg"

    def version(self, uid: str) -> int | None:
        return self._versions.get(uid)

    def url(self, uid: str) -> str | None:
        version = self._versions.get(uid)
        if version is None:
            return None
        return f"/avatars/{uid}.jpg?v={version}"

    def save(self, uid: str, raw: bytes) -> str:
        if not UID_RE.match(uid or ""):
            raise AvatarError("Mã người dùng không hợp lệ.")
        if not raw:
            raise AvatarError("File rỗng.")
        if len(raw) > UPLOAD_MAX_BYTES:
            raise AvatarError(f"Ảnh quá lớn, tối đa {UPLOAD_MAX_BYTES // (1024*1024)}MB.")

        with _AVATAR_SEMAPHORE:
            try:
                with Image.open(io.BytesIO(raw)) as probe:
                    pw, ph = probe.size
                    if pw <= 0 or ph <= 0 or pw > MAX_SIDE_PX or ph > MAX_SIDE_PX or (pw * ph) > MAX_IMAGE_PIXELS:
                        raise AvatarError("Độ phân giải ảnh quá lớn (tối đa 25MP / 8192px).")
                    probe.verify()
                with Image.open(io.BytesIO(raw)) as img:
                    fmt = (img.format or "").upper()
                    w, h = img.size
                    if w <= 0 or h <= 0 or w > MAX_SIDE_PX or h > MAX_SIDE_PX or (w * h) > MAX_IMAGE_PIXELS:
                        raise AvatarError("Độ phân giải ảnh quá lớn (tối đa 25MP / 8192px).")
            except AvatarError:
                raise
            except Exception:
                raise AvatarError("File này không phải ảnh hợp lệ.") from None

            if fmt not in ALLOWED_FORMATS:
                raise AvatarError("Chỉ nhận JPG, PNG, GIF hoặc WEBP.")

            with Image.open(io.BytesIO(raw)) as img:
                if fmt == "JPEG":
                    img.draft("RGB", (AVATAR_SIZE * 2, AVATAR_SIZE * 2))
                img.load()
                # EXIF orientation: ảnh chụp từ điện thoại thường bị xoay sai nếu
                # không áp lại orientation trước khi cắt vuông.
                img = ImageOps.exif_transpose(img)
                rgb = img.convert("RGB")
                side = min(rgb.size)
                left = (rgb.width - side) // 2
                top = (rgb.height - side) // 2
                square = rgb.crop((left, top, left + side, top + side))
                square = square.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
                buffer = io.BytesIO()
                square.save(buffer, format="JPEG", quality=88, optimize=True)

        path = self._path(uid)
        path.write_bytes(buffer.getvalue())
        version = int(time.time())
        self._versions[uid] = version
        hf_sync.enqueue_upload(self.data_dir, f"avatars/{uid}.jpg")
        return self.url(uid)

    def remove(self, uid: str) -> None:
        if not UID_RE.match(uid or ""):
            return
        self._path(uid).unlink(missing_ok=True)
        self._versions.pop(uid, None)
        hf_sync.enqueue_delete(f"avatars/{uid}.jpg")

    def file_path(self, uid: str) -> Path | None:
        if not UID_RE.match(uid or ""):
            return None
        path = self._path(uid)
        if path.is_file():
            return path
        if hf_sync.is_enabled():
            fetched = hf_sync.fetch_file(self.data_dir, f"avatars/{uid}.jpg")
            if fetched is not None:
                self._versions.setdefault(uid, int(fetched.stat().st_mtime))
                return fetched
        return None
