"""Bảng xếp hạng "Vô địch ngày" của Xì Tố.

Cùng nguyên tắc với ``ProfileStore`` trong hub.py: giữ một dict nhỏ trong RAM,
ghi đè nguyên file JSON ra đĩa mỗi lần đổi. Khác chat/game, đây là số liệu
muốn SỐNG QUA restart server trong cùng một ngày — tắt server giữa buổi chơi
không được xoá sạch thành tích đang tranh hạng.

Đo bằng NET CHIP THẮNG trong ngày (tổng chip thắng trừ tổng chip đã góp vào
pot thua), cộng dồn qua mọi bàn Xì Tố, theo uid. Số có thể âm (thua nhiều hơn
thắng) — vẫn hiện trên bảng, xếp dưới, để biết "ai đang gỡ".

NGÀY được tính theo giờ địa phương của máy chạy server (``date.today()``) vì
hub này chạy LAN nội bộ một múi giờ, không cần xử lý timezone phức tạp. Sang
ngày mới thì bảng cũ được lưu riêng theo khoá ngày, bảng ngày mới bắt đầu từ 0
— không cần tác vụ "reset" nào, chỉ cần đổi khoá đọc/ghi.
"""

from __future__ import annotations

import contextlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import db


class PokerBoard:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "poker_leaderboard.json"
        # {"2026-10-02": {uid: {"name":.., "color":.., "net": int, "hands": int}}}
        self.data: dict[str, dict[str, dict]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="poker-db")
        if db.is_enabled():
            self._load_db()
        elif self.path.exists():
            with contextlib.suppress(Exception):
                self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def _load_db(self) -> None:
        with db.connection() as conn:
            rows = conn.execute(
                "select day::text, uid, name, color, net, hands from public.poker_leaderboard"
            ).fetchall()
        for day_str, uid, name, color, net, hands in rows:
            day = self.data.setdefault(day_str, {})
            day[uid] = {
                "name": name,
                "color": color,
                "net": int(net),
                "hands": int(hands),
            }

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def _save(self) -> None:
        with contextlib.suppress(Exception):
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _persist_db(today: str, rows: list[tuple[str, str, str, int]]) -> None:
        if not db.is_enabled() or not rows:
            return
        with contextlib.suppress(Exception), db.connection() as conn, conn.transaction():
            for uid, name, color, delta in rows:
                conn.execute(
                    """
                    insert into public.poker_leaderboard (day, uid, name, color, net, hands)
                    values (%s::date, %s, %s, %s, %s, 1)
                    on conflict (day, uid)
                    do update set
                        name = excluded.name,
                        color = excluded.color,
                        net = public.poker_leaderboard.net + excluded.net,
                        hands = public.poker_leaderboard.hands + 1
                    """,
                    (today, uid, name, color, delta),
                )

    def record(self, net_by_uid: dict[str, int], names: dict[str, dict]) -> None:
        """Cộng dồn kết quả MỘT ván vào bảng ngày hôm nay.

        ``names`` là {uid: {"name", "color"}} — truyền kèm mỗi lần ghi vì
        PokerBoard không giữ danh bạ riêng (hub.py đã có ProfileStore cho
        việc đó); lấy ngay lúc ghi để tên hiển thị luôn mới nhất.
        """
        if not net_by_uid:
            return
        today = self._today()
        day = self.data.setdefault(today, {})
        db_rows: list[tuple[str, str, str, int]] = []
        for uid, delta in net_by_uid.items():
            entry = day.setdefault(uid, {"name": uid[:8], "color": "#6366f1",
                                         "net": 0, "hands": 0})
            info = names.get(uid) or {}
            if info.get("name"):
                entry["name"] = info["name"]
            if info.get("color"):
                entry["color"] = info["color"]
            entry["net"] += int(delta)
            entry["hands"] += 1
            db_rows.append((uid, entry["name"], entry["color"], int(delta)))

        if db.is_enabled():
            self._executor.submit(self._persist_db, today, db_rows)
        else:
            self._save()

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def today_board(self, limit: int = 10) -> list[dict]:
        day = self.data.get(self._today(), {})
        rows = [{"uid": uid, **info} for uid, info in day.items()]
        rows.sort(key=lambda r: -r["net"])
        return rows[:limit]

    def champion_today(self) -> dict | None:
        board = self.today_board(limit=1)
        return board[0] if board else None
