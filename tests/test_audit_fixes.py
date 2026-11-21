"""Kiểm thử toàn diện các bản vá bảo mật, ổn định, tối ưu mạng 15 Hz và gameplay."""
from __future__ import annotations

import asyncio
import json
import math
import time

import pytest
from fastapi.testclient import TestClient

from bluff import AWAY_TURN_SECONDS as BLUFF_AWAY_SEC, BluffRoom
from caro import CaroRoom
from chat import ChatError, ChatStore, HISTORY_IN_MEMORY
from chessgame import ChessRoom
from flags_quiz import FlagsRoom, MAX_TYPING_TRIES
from games import GameError, int_field
from hub import Hub
from ludo import AWAY_TURN_SECONDS as LUDO_AWAY_SEC, LudoRoom
import server
from server import HttpSessionSock, app
from xiangqi import XiangqiRoom
from zombie import WEAPONS, ZombieRoom


class DummySock:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def test_hub_tick_isolates_crashing_room_and_closes_after_5_errors(tmp_path):
    async def scenario():
        h = Hub(tmp_path)
        bad = h.managers["ludo"].create("classic")
        good = h.managers["ludo"].create("classic")
        s1, s2 = DummySock(), DummySock()
        ses1 = await h.register(s1, "u_bad", "Bad")
        ses2 = await h.register(s2, "u_good", "Good")
        await h.handle_game(ses1, "ludo", "join", {"room": bad.code})
        await h.handle_game(ses2, "ludo", "join", {"room": good.code})

        good_ticked = 0

        def boom():
            raise RuntimeError("boom")

        def ok_tick():
            nonlocal good_ticked
            good_ticked += 1
            return False

        bad.tick = boom
        good.tick = ok_tick

        for _ in range(5):
            await h._tick_once()

        # Phòng tốt vẫn được tick đủ 5 lần dù phòng lỗi ném ngoại lệ ở ngay trước nó
        assert good_ticked == 5
        # Phòng lỗi liên tiếp 5 lần phải tự đóng và gửi thông báo closed
        assert h.managers["ludo"].get(bad.code) is None
        assert any(m.get("t") == "closed" for m in s1.sent)

    asyncio.run(scenario())


def test_hub_unregister_per_room_prevents_ghost_player(tmp_path):
    async def scenario():
        h = Hub(tmp_path)
        room = h.managers["caro"].create("xo")
        s_game, s_chat = DummySock(), DummySock()
        ses_game = await h.register(s_game, "u_multi", "Multi")
        ses_chat = await h.register(s_chat, "u_multi", "Multi")

        await h.handle_game(ses_game, "caro", "join", {"room": room.code})
        await h.handle_chat(ses_chat, "join", {"room": "chung"})
        assert room.players["u_multi"].connected is True

        # Đóng tab đang ở phòng Caro trong khi tab Chat vẫn mở -> phải disconnect khỏi phòng Caro!
        await h.unregister(s_game)
        assert "u_multi" not in room.players or room.players["u_multi"].connected is False

    asyncio.run(scenario())


def test_chat_rewrite_log_preserves_messages_beyond_memory_window(tmp_path):
    store = ChatStore(tmp_path)
    log_path = store._log_file("chung")
    # Tạo 450 tin nhắn cũ trên đĩa (> HISTORY_IN_MEMORY = 400)
    lines = []
    for i in range(HISTORY_IN_MEMORY + 50):
        lines.append(json.dumps({
            "id": f"m_{i:04d}",
            "channel": "chung",
            "uid": "u1",
            "name": "Alice",
            "color": "#6366f1",
            "text": f"msg {i}",
            "image": None,
            "file": None,
            "replyTo": None,
            "ts": 1000.0 + i,
            "reactions": {},
            "deleted": False,
        }))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    reloaded = ChatStore(tmp_path)
    assert len(reloaded.messages["chung"]) == HISTORY_IN_MEMORY
    target_id = reloaded.messages["chung"][-1]["id"]
    reloaded.react("chung", target_id, "u2", "👍")

    # Sau khi react, file trên đĩa vẫn phải giữ đủ 450 dòng, không bị cắt còn 400!
    after_lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(after_lines) == HISTORY_IN_MEMORY + 50
    last_saved = json.loads(after_lines[-1])
    assert last_saved["reactions"]["👍"] == ["u2"]


def test_http_session_sock_coalesces_states_merges_events_and_keeps_static():
    async def scenario():
        sock = HttpSessionSock("sid1", "u1", "Alice")
        await sock.send_json({"ch": "chat", "t": "message", "id": "m1"})
        await sock.send_json({
            "ch": "zombie", "t": "state",
            "catalog": {"weapons": {}}, "arena": {"w": 1400},
            "events": [{"seq": 1, "t": "shot"}],
        })
        await sock.send_json({
            "ch": "zombie", "t": "state",
            "events": [{"seq": 2, "t": "kill"}],
        })

        # Queue chỉ còn 2 mục (1 chat + 1 zombie state đã gộp)
        assert len(sock.queue) == 2
        seq, msgs = sock.collect_since(0)
        assert seq == 3
        assert len(msgs) == 2
        assert msgs[0]["t"] == "message" and msgs[0]["_seq"] == 1
        st = msgs[1]
        assert st["t"] == "state" and st["_seq"] == 3
        assert "catalog" in st and "arena" in st
        assert [e["seq"] for e in st["events"]] == [1, 2]

    asyncio.run(scenario())


def test_chat_http_endpoints_require_auth(tmp_path):
    client = TestClient(app)
    r_no_auth = client.post("/api/chat/channels", json={"title": "No Auth"})
    assert r_no_auth.status_code == 401

    # Dùng thư mục tạm cho tokens_path để test không ghi vào data/ thật
    old_path = server.hub.directory.tokens_path
    old_tokens = dict(server.hub.directory.tokens)
    try:
        server.hub.directory.tokens_path = tmp_path / "tokens.json"
        uid = "u_auth_test_1"
        assert server.hub.directory.verify_or_bind_token(uid, "good-secret") is True
        r_bad = client.post(
            "/api/chat/channels",
            json={"title": "Bad Tok"},
            headers={"X-Hub-Uid": uid, "X-Hub-Token": "wrong-secret"},
        )
        assert r_bad.status_code == 403
    finally:
        server.hub.directory.tokens_path = old_path
        server.hub.directory.tokens = old_tokens


def test_flags_hides_codes_preloads_and_limits_typing_tries():
    room = FlagsRoom("FLG1", "world")
    room.join("u1", "Alice", "#6366f1")
    room.handle("u1", "config", {"quizType": "flag", "answerMode": "choice"})
    room.handle("u1", "start", {})

    v = room.match_view("u1")
    q = v["question"]
    assert q["nextFlagUrl"] == ""
    assert q["preloadFlags"] == []
    assert len(q["options"]) == 4
    for opt in q["options"]:
        assert "code" not in opt
        assert isinstance(opt["idx"], int)

    # Trả lời bằng chỉ số option (0..3) hoạt động chuẩn
    correct_code = room.questions[0]["country"]["code"]
    correct_idx = next(i for i, o in enumerate(room.questions[0]["options"]) if o["code"] == correct_code)
    room.handle("u1", "answer", {"choice": str(correct_idx)})
    assert room.phase == "reveal"
    assert room.answers["1"]["correct"] is True
    # Sang pha reveal mới cho phép gửi nextFlagUrl
    assert room.match_view("u1")["question"]["nextFlagUrl"] != ""

    # Kiểm tra chế độ typing: giới hạn tối đa MAX_TYPING_TRIES lần đoán sai
    r2 = FlagsRoom("FLG2", "world")
    r2.join("u1", "Bob", "#ec4899")
    r2.handle("u1", "config", {"quizType": "flag", "answerMode": "typing"})
    r2.handle("u1", "start", {})
    for attempt in range(MAX_TYPING_TRIES):
        r2.last_try_at["1"] = 0.0  # bỏ qua cooldown trong test
        r2.handle("u1", "answer", {"text": f"wrong_country_{attempt}"})
    assert r2.phase == "reveal"
    assert r2.answers["1"]["correct"] is False


def test_int_field_and_chess_xiangqi_undo_clock():
    assert int_field({"x": float("inf")}, "x", -1) == -1
    assert int_field({"x": float("nan")}, "x", -1) == -1
    assert int_field({"x": "12"}, "x", -1) == 12

    # Caro không văng OverflowError khi nhận Infinity
    caro = CaroRoom("CR1", "xo")
    caro.join("u1", "A")
    caro.join("u2", "B")
    with pytest.raises(GameError):
        caro.handle("u1", "move", {"index": float("inf")})

    # Chess undo không cho ăn gian đồng hồ (kể cả increment)
    chess = ChessRoom("CH1", "standard")
    chess.apply_initial_config({"clock": "180+2"})
    chess.join("u1", "Human")
    chess.add_bot("easy")
    chess.turn_started_at = time.time() - 5.0
    chess.handle("u1", "move", {"from": 52, "to": 36})  # e2-e4
    remain_after_move = chess.clock_remain["X"]
    chess.turn_started_at = time.time() - 4.0
    chess.handle("u1", "undo", {})
    assert chess.clock_remain["X"] < remain_after_move

    # Xiangqi undo cũng bảo toàn đồng hồ tương tự
    xq = XiangqiRoom("XQ1", "standard")
    xq.apply_initial_config({"clock": "180+2"})
    xq.join("u1", "Human")
    xq.add_bot("easy")
    frm = next(iter(xq.legal.keys()))
    to = xq.legal[frm][0]
    xq.turn_started_at = time.time() - 3.0
    xq.handle("u1", "move", {"from": frm, "to": to})
    remain_xq = xq.clock_remain["X"]
    xq.handle("u1", "undo", {})
    assert xq.clock_remain["X"] < remain_xq


def test_ludo_and_bluff_shorten_deadline_on_disconnect():
    ludo = LudoRoom("LD1", "classic")
    ludo.join("u1", "A")
    ludo.join("u2", "B")
    ludo.handle("u1", "start", {})
    cur = ludo.turn
    uid_cur = ludo.seat(cur).uid
    ludo.disconnect(uid_cur)
    assert ludo.deadline <= time.time() + LUDO_AWAY_SEC + 0.5

    bluff = BluffRoom("BL1", "p2")
    bluff.join("u1", "A")
    bluff.join("u2", "B")
    cur_b = bluff.turn
    uid_b = bluff.seat(cur_b).uid
    bluff.disconnect(uid_b)
    assert bluff.deadline <= time.time() + BLUFF_AWAY_SEC + 0.5


def test_zombie_z1_to_z8_and_delta_shared_view():
    room = ZombieRoom("ZFIX", "outpost")
    room.join("u1", "P1", "#38bdf8")
    room.join("u2", "P2", "#f59e0b")
    room.handle("u1", "start", {})

    # Z1: Gửi NaN / Infinity không làm hỏng tọa độ hay JSON serialize
    room.handle("u1", "input", {"vx": float("nan"), "vy": float("inf"), "aim": float("inf"), "firing": False})
    room.handle("u1", "grenade", {"tx": float("nan"), "ty": float("inf")})
    sv1 = room.survivors["1"]
    assert math.isfinite(sv1["vx"]) and math.isfinite(sv1["vy"]) and math.isfinite(sv1["aim"])
    json.dumps(room.shared_view(full=True), allow_nan=False)

    # Z2: u2 stand/resign giữa trận KHÔNG kết thúc trận của u1
    room.resign("u2")
    assert room.status == "playing"
    assert "2" not in room.survivors
    assert "1" in room.survivors

    # Z3: disconnect reset input
    sv1["vx"], sv1["vy"], sv1["firing"] = 1.0, 1.0, True
    room.disconnect("u1")
    assert sv1["vx"] == 0.0 and sv1["vy"] == 0.0 and sv1["firing"] is False
    room.join("u1", "P1", "#38bdf8")

    # Z4: Tesla stun cooldown riêng, không làm hỏng EMP
    z = room._spawn_one_zombie("brute")
    z["x"], z["y"] = sv1["x"] + 100.0, sv1["y"]
    sv1["weapons"].append("tesla")
    sv1["weapon"] = "tesla"
    sv1["mag"]["tesla"] = 16
    sv1["fireCd"] = 0.0
    room.handle("u1", "shoot", {"aim": 0.0})
    assert z["stunTimer"] > 0 and z["teslaStunCd"] > 1.0
    z["stunTimer"] = 0.0
    sv1["fireCd"] = 0.0
    room.handle("u1", "shoot", {"aim": 0.0})
    # Đang trong teslaStunCd -> không choáng khóa cứng 100%
    assert z["stunTimer"] == 0.0

    # Z7/Z16: Người ngồi vào ghế giữa trận được spawn ở _begin_wave kế tiếp
    room.join("u3", "LateJoiner", "#10b981")
    assert "3" not in room.survivors
    room._begin_wave(2)
    assert "3" in room.survivors
    assert room.survivors["3"]["money"] >= 320

    # Z8: Kẹp trần reserve khi nhặt hộp đạn
    sv1["weapon"] = "smg"
    sv1["reserve"]["smg"] = WEAPONS["smg"]["reserve"] * 2
    room.pickups.append({"id": 99999, "kind": "ammo", "x": sv1["x"], "y": sv1["y"], "ttl": 10.0})
    room.tick(dt_override=0.066)
    assert sv1["reserve"]["smg"] == WEAPONS["smg"]["reserve"] * 2

    # Shared view delta (full=False) lược bỏ catalog/arena/chat khi static không đổi & chỉ gửi event mới
    full_v = room.shared_view(full=True)
    assert "catalog" in full_v and "arena" in full_v and "chat" in full_v
    delta_v = room.shared_view(full=False)
    assert "catalog" not in delta_v and "arena" not in delta_v and "chat" not in delta_v
    assert delta_v["events"] == []
    room._emit("hit", x=10, y=10, dmg=20, crit=False)
    delta_v2 = room.shared_view(full=False)
    assert len(delta_v2["events"]) == 1
