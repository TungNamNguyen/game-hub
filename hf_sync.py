"""Đồng bộ ảnh & dữ liệu với Hugging Face Private Dataset (tối ưu băng thông & commit).

Khi chạy kèm Supabase Postgres (``skip_json=True``):
  - HF Dataset CHỈ đóng vai trò kho lưu ảnh (``uploads/``, ``avatars/``).
  - Lúc khởi động chỉ tải ``avatars/`` (nhẹ), ảnh chat trong ``uploads/``
    được tải lười (lazy-load) khi có người mở xem.
  - Ảnh/avatar mới upload được đẩy lên Dataset ngay lập tức ở luồng nền.

Khi chạy độc lập không có Postgres (``skip_json=False``):
  - Đồng bộ thêm file JSON/JSONL theo chu kỳ debounce 180 giây, bỏ qua
    ``reads.json`` khỏi bộ kích hoạt commit để tránh spam commit.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYNC_INTERVAL_FALLBACK = 180   # giây (chỉ dùng khi không có Postgres)
SYNC_INTERVAL_MEDIA = 300      # giây (quét an toàn dự phòng cho ảnh)

_IGNORE_DIRS = {".cache", ".huggingface", "__pycache__"}
_IGNORE_FILES = {".gitattributes", "README.md"}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hf-sync")
_fetch_locks_guard = threading.Lock()
_fetch_locks: dict[str, threading.Lock] = {}
_media_dirty = threading.Event()


def _config() -> tuple[str, str]:
    token = os.environ.get("HF_TOKEN", "").strip()
    dataset = os.environ.get("HF_DATASET", "").strip()
    return token, dataset


def is_enabled() -> bool:
    token, dataset = _config()
    return bool(token and dataset)


def _fetch_lock_for(rel_path: str) -> threading.Lock:
    with _fetch_locks_guard:
        lock = _fetch_locks.get(rel_path)
        if lock is None:
            lock = threading.Lock()
            _fetch_locks[rel_path] = lock
        return lock


def _dir_signature(data_dir: Path, *, media_only: bool = False) -> tuple[tuple[str, int, int], ...]:
    """Chụp nhanh (relative_path, size, mtime_ns) để phát hiện thay đổi."""
    if not data_dir.exists():
        return ()
    entries: list[tuple[str, int, int]] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(data_dir)
        if any(part in _IGNORE_DIRS for part in rel.parts):
            continue
        if rel.name in _IGNORE_FILES or rel.name.endswith(".tmp"):
            continue
        if media_only and rel.parts[0] not in ("uploads", "avatars"):
            continue
        if not media_only and rel.as_posix() == "chat/reads.json":
            # reads.json đổi liên tục mỗi lần mở kênh; không kích hoạt commit riêng.
            continue
        with contextlib.suppress(OSError):
            st = path.stat()
            entries.append((rel.as_posix(), st.st_size, st.st_mtime_ns))
    return tuple(entries)


def restore_data(data_dir: Path, *, skip_json: bool = False) -> None:
    """Tải dữ liệu từ HF Dataset lúc khởi động (lazy-load uploads/)."""
    token, dataset = _config()
    if not (token and dataset):
        return

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[hf_sync] Thieu thu vien huggingface_hub, bo qua restore.", flush=True)
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    ignore = [
        ".gitattributes", "README.md",
        "uploads/*", "uploads/**",  # Lazy-load khi có người mở ảnh
    ]
    if skip_json:
        ignore.extend([
            "chat/*", "chat/**",
            "profiles.json",
            "poker_leaderboard.json",
        ])

    mode = "avatars only" if skip_json else "json + avatars"
    print(f"[hf_sync] Dang khoi phuc du lieu ({mode}) tu '{dataset}'...", flush=True)
    try:
        snapshot_download(
            repo_id=dataset,
            repo_type="dataset",
            local_dir=str(data_dir),
            token=token,
            ignore_patterns=ignore,
        )
        print("[hf_sync] Da khoi phuc xong du lieu ban dau.", flush=True)
    except Exception as exc:
        print(f"[hf_sync] Khong the tai dataset (co the repo dang trong): {exc}", flush=True)


def fetch_file(data_dir: Path, rel_path: str) -> Path | None:
    """Tải lười một file (ảnh chat / avatar) từ HF Dataset về cache local."""
    dest = data_dir / rel_path
    if dest.is_file():
        return dest

    token, dataset = _config()
    if not (token and dataset):
        return None

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None

    lock = _fetch_lock_for(rel_path)
    with lock:
        if dest.is_file():
            return dest
        try:
            hf_hub_download(
                repo_id=dataset,
                repo_type="dataset",
                filename=rel_path,
                local_dir=str(data_dir),
                token=token,
            )
            return dest if dest.is_file() else None
        except Exception:
            return None


def _upload_single_sync(data_dir: Path, rel_path: str) -> None:
    token, dataset = _config()
    if not (token and dataset):
        return
    file_path = data_dir / rel_path
    if not file_path.is_file():
        return
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        api.upload_file(
            path_or_fileobj=str(file_path),
            path_in_repo=rel_path,
            repo_id=dataset,
            repo_type="dataset",
            commit_message=f"Upload {rel_path}",
        )
    except Exception as exc:
        _media_dirty.set()
        print(f"[hf_sync] Loi upload {rel_path}: {exc}", flush=True)


def _delete_single_sync(rel_path: str) -> None:
    token, dataset = _config()
    if not (token and dataset):
        return
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        api.delete_file(
            path_in_repo=rel_path,
            repo_id=dataset,
            repo_type="dataset",
            commit_message=f"Delete {rel_path}",
        )
    except Exception:
        pass


def enqueue_upload(data_dir: Path, rel_path: str) -> None:
    """Đẩy ngay một file ảnh/avatar mới lên HF Dataset ở luồng nền."""
    if not is_enabled():
        return
    _executor.submit(_upload_single_sync, data_dir, rel_path)


def enqueue_delete(rel_path: str) -> None:
    """Xóa một file khỏi HF Dataset ở luồng nền."""
    if not is_enabled():
        return
    _executor.submit(_delete_single_sync, rel_path)


def upload_data_sync(data_dir: Path, *, media_only: bool = False) -> bool:
    """Đẩy thư mục data_dir lên HF Dataset (dùng cho chế độ dự phòng / shutdown)."""
    token, dataset = _config()
    if not (token and dataset) or not data_dir.exists():
        return False

    try:
        from huggingface_hub import HfApi
    except ImportError:
        return False

    ignore = [
        ".cache/*", ".cache/**",
        ".huggingface/*", ".huggingface/**",
        ".gitattributes", "README.md", "*.tmp",
    ]
    if media_only:
        ignore.extend(["chat/*", "chat/**", "profiles.json", "poker_leaderboard.json"])

    try:
        api = HfApi(token=token)
        api.upload_folder(
            folder_path=str(data_dir),
            repo_id=dataset,
            repo_type="dataset",
            commit_message="Sync VPHub media" if media_only else "Sync VPHub data",
            ignore_patterns=ignore,
        )
        return True
    except Exception as exc:
        print(f"[hf_sync] Loi khi dong bo len HF Dataset: {exc}", flush=True)
        return False


async def sync_loop(data_dir: Path, *, skip_json: bool = False) -> None:
    """Vòng lặp chạy nền: dự phòng cho ảnh lỗi mạng hoặc debounce JSON khi không có DB."""
    if not is_enabled():
        return

    interval = SYNC_INTERVAL_MEDIA if skip_json else SYNC_INTERVAL_FALLBACK
    last_sig = _dir_signature(data_dir, media_only=skip_json)

    try:
        while True:
            await asyncio.sleep(interval)
            if skip_json and not _media_dirty.is_set():
                continue
            current_sig = _dir_signature(data_dir, media_only=skip_json)
            if current_sig != last_sig and current_sig:
                ok = await asyncio.to_thread(upload_data_sync, data_dir, media_only=skip_json)
                if ok:
                    last_sig = current_sig
                    _media_dirty.clear()
                    print("[hf_sync] Da dong bo du lieu len HF Dataset.", flush=True)
    except asyncio.CancelledError:
        if not skip_json or _media_dirty.is_set():
            current_sig = _dir_signature(data_dir, media_only=skip_json)
            if current_sig != last_sig and current_sig:
                print("[hf_sync] Dang dong bo lan cuoi truoc khi tat...", flush=True)
                await asyncio.to_thread(upload_data_sync, data_dir, media_only=skip_json)
        _executor.shutdown(wait=True, cancel_futures=False)
        raise


def migrate_legacy_to_db(data_dir: Path) -> None:
    """Chuyển dữ liệu JSON/JSONL cũ từ HF Dataset sang Supabase Postgres (1 lần duy nhất).

    Chỉ chạy khi Postgres chưa có tin nhắn và chưa có hồ sơ nào, giúp giữ
    nguyên toàn bộ lịch sử chat cũ khi nâng cấp từ HF Dataset sang Supabase.
    """
    import json
    import db

    if not (db.is_enabled() and is_enabled()):
        return

    with db.connection() as conn:
        has_msgs = conn.execute("select 1 from public.messages limit 1").fetchone()
        has_profiles = conn.execute("select 1 from public.profiles limit 1").fetchone()
        if has_msgs or has_profiles:
            return

    token, dataset = _config()
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=dataset,
            repo_type="dataset",
            local_dir=str(data_dir),
            token=token,
            allow_patterns=["chat/*", "profiles.json", "poker_leaderboard.json"],
        )
    except Exception:
        return

    migrated_msgs = 0
    migrated_profiles = 0

    with db.connection() as conn, conn.transaction():
        # 1. Profiles
        profiles_file = data_dir / "profiles.json"
        if profiles_file.is_file():
            with contextlib.suppress(Exception):
                profiles = json.loads(profiles_file.read_text(encoding="utf-8"))
                for uid, info in profiles.items():
                    conn.execute(
                        """
                        insert into public.profiles (uid, name, color)
                        values (%s, %s, %s)
                        on conflict (uid) do nothing
                        """,
                        (uid, info.get("name", uid[:8]), info.get("color", "#6366f1")),
                    )
                    migrated_profiles += 1

        # 2. Channels
        known_channels: set[str] = set()
        channels_file = data_dir / "chat" / "channels.json"
        if channels_file.is_file():
            with contextlib.suppress(Exception):
                chans = json.loads(channels_file.read_text(encoding="utf-8"))
                for name, info in chans.items():
                    conn.execute(
                        """
                        insert into public.channels (name, title, created_at)
                        values (%s, %s, %s)
                        on conflict (name) do nothing
                        """,
                        (name, info.get("title") or name, float(info.get("created", 0.0))),
                    )
                    known_channels.add(name)

        # 3. Messages
        chat_dir = data_dir / "chat"
        if chat_dir.is_dir():
            for jsonl_file in sorted(chat_dir.glob("*.jsonl")):
                chan = jsonl_file.stem
                if chan not in known_channels:
                    conn.execute(
                        """
                        insert into public.channels (name, title, created_at)
                        values (%s, %s, %s)
                        on conflict (name) do nothing
                        """,
                        (chan, chan, 0.0),
                    )
                    known_channels.add(chan)
                with contextlib.suppress(Exception):
                    for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        with contextlib.suppress(Exception):
                            m = json.loads(line)
                            conn.execute(
                                """
                                insert into public.messages
                                    (id, channel, uid, name, color, text, image, reply_to, ts, reactions, deleted)
                                values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s)
                                on conflict (id) do nothing
                                """,
                                (
                                    m["id"],
                                    m.get("channel") or chan,
                                    m["uid"],
                                    m.get("name", ""),
                                    m.get("color", "#6366f1"),
                                    m.get("text", ""),
                                    json.dumps(m["image"], ensure_ascii=False) if m.get("image") is not None else None,
                                    json.dumps(m["replyTo"], ensure_ascii=False) if m.get("replyTo") is not None else None,
                                    float(m.get("ts", 0.0)),
                                    json.dumps(m.get("reactions") or {}, ensure_ascii=False),
                                    bool(m.get("deleted", False)),
                                ),
                            )
                            migrated_msgs += 1

        # 4. Reads
        reads_file = data_dir / "chat" / "reads.json"
        if reads_file.is_file():
            with contextlib.suppress(Exception):
                reads = json.loads(reads_file.read_text(encoding="utf-8"))
                for uid, chan_map in reads.items():
                    for chan, ts in (chan_map or {}).items():
                        if chan in known_channels:
                            conn.execute(
                                """
                                insert into public.reads (uid, channel, last_read_ts)
                                values (%s, %s, %s)
                                on conflict (uid, channel) do nothing
                                """,
                                (uid, chan, float(ts)),
                            )

        # 5. Poker leaderboard
        pb_file = data_dir / "poker_leaderboard.json"
        if pb_file.is_file():
            with contextlib.suppress(Exception):
                pb = json.loads(pb_file.read_text(encoding="utf-8"))
                for day_str, users in pb.items():
                    for uid, info in (users or {}).items():
                        conn.execute(
                            """
                            insert into public.poker_leaderboard (day, uid, name, color, net, hands)
                            values (%s::date, %s, %s, %s, %s, %s)
                            on conflict (day, uid) do nothing
                            """,
                            (
                                day_str,
                                uid,
                                info.get("name", uid[:8]),
                                info.get("color", "#6366f1"),
                                int(info.get("net", 0)),
                                int(info.get("hands", 0)),
                            ),
                        )

    if migrated_msgs or migrated_profiles:
        print(
            f"[hf_sync] Da chuyen {migrated_msgs} tin nhan va {migrated_profiles} ho so cu sang Supabase Postgres.",
            flush=True,
        )

