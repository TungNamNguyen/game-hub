"""Kiểm thử Cờ Cá Ngựa (LudoRoom, LudoBot) và nâng cấp Hub ping/pong."""

from __future__ import annotations

import asyncio

from bot_ludo import LudoBot
from games import GameError
from hub import Hub
from ludo import LudoRoom


def test_auto_start_at_4_players():
    room = LudoRoom("LD01", "classic")
    room.join("u1", "P1", "#111")
    room.join("u2", "P2", "#222")
    room.join("u3", "P3", "#333")
    assert room.status == "waiting"
    assert room.host_uid == "u1"

    room.join("u4", "P4", "#444")
    assert room.status == "playing"
    assert room.active_seats == ["R", "B", "Y", "G"]
    assert room.turn == "R"
    assert room.phase == "roll"


def test_host_manual_start_and_permissions():
    room = LudoRoom("LD02", "classic")
    room.join("u1", "Host", "#111")
    room.join("u2", "Guest", "#222")
    assert room.status == "waiting"

    # Khách không phải chủ phòng -> không được start sớm hoặc đổi config
    try:
        room.handle("u2", "start", {})
        raise AssertionError("Expected GameError for non-host start")
    except GameError:
        pass

    try:
        room.handle("u2", "config", {"deployRule": "6only"})
        raise AssertionError("Expected GameError for non-host config")
    except GameError:
        pass

    # Chủ phòng đổi config & start ngay với 2 người
    room.handle("u1", "config", {"deployRule": "6only"})
    assert room.config["deployRule"] == "6only"
    room.handle("u1", "start", {})
    assert room.status == "playing"
    assert room.active_seats == ["R", "B"]

    # Chủ phòng 1 mình bấm Start -> tự thêm 1 máy
    solo = LudoRoom("LD03", "classic")
    solo.join("u1", "SoloHost", "#111")
    solo.handle("u1", "start", {})
    assert solo.status == "playing"
    assert len(solo.active_seats) == 2
    assert len(solo.bot_players()) == 1


    # Kiểm tra khi ngựa chưa xuất chuồng và tung ra số không đi được (VD: 4) -> lastRoll & lastRolls vẫn lưu đúng
    room.rng.randint = lambda a, b: 4
    assert room.turn == "R"
    room.handle("u1", "roll", {})
    view = room.match_view("u1")
    assert view["lastRoll"]["color"] == "R" and view["lastRoll"]["value"] == 4
    assert view["lastRolls"]["R"] == 4
    assert view["lastEvent"]["type"] == "nomove" and view["lastEvent"]["dice"] == 4
    assert room.turn == "B"


def test_blocking_kick_and_back_kick():
    room = LudoRoom("LD04", "classic")
    room.join("u1", "Red", "#111")
    room.join("u2", "Blue", "#222")
    room.handle("u1", "start", {})

    # Đặt ngựa Đỏ ở pos=10 (global=10), ngựa Xanh ở pos=54 -> global=(14+54)%56 = 12 (cách Đỏ +2)
    # Và 1 ngựa Xanh khác ở global=7 (cách Đỏ -3 -> pos=10-3=7) để test Đá Hậu!
    # Với Blue (START_OFFSET=14): global=7 <=> progress=(7-14)%56 = 49
    room.pieces["R"] = [10, -1, -1, -1]
    room.pieces["B"] = [54, 49, -1, -1]

    # Trường hợp 1: Đổ xúc xắc = 2 -> Đỏ tiến 2 đá Xanh#0 ở global=12
    moves_2 = room.compute_legal_moves("R", 2)
    kinds_2 = {m.kind for m in moves_2}
    assert "kick" in kinds_2

    # Trường hợp 2: Đổ xúc xắc = 3 -> Đỏ lùi 3 (global 10 -> 7) ĐÁ HẬU Xanh#1!
    moves_3 = room.compute_legal_moves("R", 3)
    back_moves = [m for m in moves_3 if m.kind == "kick_back"]
    assert len(back_moves) == 1
    assert back_moves[0].kicked_color == "B"
    assert back_moves[0].kicked_piece == 1
    assert back_moves[0].to_pos == 7

    # Thực thi nước Đá Hậu qua room.handle -> Xanh#1 về chuồng (-1) và Đỏ được thưởng lượt!
    room.phase = "move"
    room.dice = 3
    room.legal_moves = moves_3
    room.handle("u1", "move", {"piece": 0, "kind": "kick_back"})
    assert room.pieces["R"][0] == 7
    assert room.pieces["B"][1] == -1
    assert room.turn == "R"
    assert room.phase == "roll"
    assert room.last_event["type"] == "kick_back"

    # Trường hợp 3: Cản đường (khi có quân đứng chắn giữa không được nhảy qua đầu)
    room.pieces["R"] = [10, 12, -1, -1]  # R#1 đứng ở 12 chắn R#0 khi đi 4
    moves_4 = room.compute_legal_moves("R", 4)
    p0_moves = [m for m in moves_4 if m.piece == 0]
    assert not p0_moves

    # Trường hợp 4: Không Đá Hậu lùi quá ô xuất phát (pos=1, dice=3 -> 1-3 < 0)
    room.pieces["R"] = [1, -1, -1, -1]
    # Đặt Xanh ở global 54 -> sau R#0 3 bước trên vòng tròn nhưng R#0 mới ở pos=1
    room.pieces["B"] = [40, -1, -1, -1]  # (14+40)%56 = 54
    moves_bwd = room.compute_legal_moves("R", 3)
    assert all(m.kind != "kick_back" for m in moves_bwd)

    # Trường hợp 5: Tắt backKick -> không sinh kick_back
    room.config["backKick"] = False
    room.pieces["R"] = [10, -1, -1, -1]
    room.pieces["B"] = [49, -1, -1, -1]
    assert all(m.kind != "kick_back" for m in room.compute_legal_moves("R", 3))


def test_home_climb_and_victory():
    room = LudoRoom("LD05", "classic")
    room.join("u1", "Red", "#111")
    room.join("u2", "Blue", "#222")
    room.handle("u1", "start", {})

    # 3 quân đã ở bậc 4, 5, 6 (59, 60, 61); quân #0 đang ở bậc 2 (57) -> cần 3 để lên bậc 3 (58)
    room.pieces["R"] = [57, 59, 60, 61]
    moves_3 = room.compute_legal_moves("R", 3)
    assert len(moves_3) == 1
    assert moves_3[0].kind == "climb_home"
    assert moves_3[0].to_pos == 58

    room.phase = "move"
    room.dice = 3
    room.legal_moves = moves_3
    room.handle("u1", "move", {"piece": 0, "kind": "climb_home"})
    assert room.status == "finished"
    assert room.winner == "R"


def test_ludo_bot_and_hub_ping_pong(tmp_path):
    room = LudoRoom("LD06", "classic")
    room.join("u1", "Human", "#111")
    room.add_bot("hard")
    assert room.status == "playing"

    bot = LudoBot("hard")
    room.turn = "B"
    room.phase = "roll"
    assert bot.actions(room, "B") == [("roll", {})]

    room.phase = "move"
    room.dice = 6
    room.legal_moves = room.compute_legal_moves("B", 6)
    acts = bot.actions(room, "B")
    assert len(acts) == 1 and acts[0][0] == "move"

    # Kiểm tra Hub trả về pong kèm ts
    hub = Hub(tmp_path)
    sent = []

    class FakeSock:
        async def send_json(self, payload):
            sent.append(payload)

    async def _run():
        sess = await hub.register(FakeSock(), "u_ping", "Tester")
        sent.clear()
        await hub.dispatch(sess, {"ch": "hub", "t": "ping", "ts": 1234.5})
        assert sent == [{"ch": "hub", "t": "pong", "ts": 1234.5}]

    asyncio.run(_run())
