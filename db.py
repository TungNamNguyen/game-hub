"""Kết nối PostgreSQL (Supabase) dùng Connection Pool tương thích Transaction Pooler.

Nếu biến môi trường ``DATABASE_URL`` không được đặt, module ở trạng thái tắt
và toàn bộ ứng dụng tự động dùng hệ thống file JSON/JSONL trong ``data/`` như cũ.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

_pool = None

_SCHEMA_SQL = """
create table if not exists public.profiles (
  uid text primary key,
  name text not null,
  color text not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.channels (
  name text primary key,
  title text not null,
  created_at double precision not null
);

create table if not exists public.messages (
  id text primary key,
  channel text not null references public.channels(name) on delete cascade,
  uid text not null,
  name text not null,
  color text not null,
  text text not null default '',
  image jsonb,
  file jsonb,
  reply_to jsonb,
  ts double precision not null,
  reactions jsonb not null default '{}'::jsonb,
  deleted boolean not null default false
);

alter table public.messages add column if not exists file jsonb;

create index if not exists messages_channel_ts_idx
  on public.messages (channel, ts desc);

create table if not exists public.reads (
  uid text not null,
  channel text not null references public.channels(name) on delete cascade,
  last_read_ts double precision not null,
  primary key (uid, channel)
);

create index if not exists reads_channel_idx
  on public.reads (channel);

create table if not exists public.poker_leaderboard (
  day date not null,
  uid text not null,
  name text not null,
  color text not null,
  net bigint not null default 0,
  hands bigint not null default 0,
  primary key (day, uid)
);

create index if not exists poker_leaderboard_day_net_idx
  on public.poker_leaderboard (day, net desc);
"""


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_enabled() -> bool:
    return _pool is not None


def init() -> bool:
    """Khởi tạo connection pool nếu có DATABASE_URL. Trả về True nếu đã bật."""
    global _pool
    if _pool is not None:
        return True

    dsn = _dsn()
    if not dsn:
        return False

    try:
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError(
            "Đã cấu hình DATABASE_URL nhưng thiếu thư viện psycopg[binary,pool]."
        ) from exc

    # prepare_threshold=None bắt buộc khi đi qua Supabase Transaction Pooler (cổng 6543)
    # để tránh lỗi xung đột prepared statement giữa các phiên dùng chung kết nối.
    pool = ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=5,
        timeout=10.0,
        open=True,
        kwargs={"prepare_threshold": None, "autocommit": True},
    )
    try:
        with pool.connection() as conn:
            conn.execute(_SCHEMA_SQL)
    except Exception:
        pool.close()
        raise

    _pool = pool
    print("[db] Da ket noi Supabase Postgres (pooler ready).", flush=True)
    return True


@contextmanager
def connection() -> Iterator[object]:
    if _pool is None:
        raise RuntimeError("Database chưa được khởi tạo.")
    with _pool.connection() as conn:
        yield conn


def ping() -> bool:
    if _pool is None:
        return False
    try:
        with _pool.connection() as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
