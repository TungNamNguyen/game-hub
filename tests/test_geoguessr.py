"""Kiểm thử Địa Đồ (GeoGuessr) và HTTP healthcheck / keepalive."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest import mock

import bots
from geoguessr import (
    ALLOWED_ROUND_COUNTS,
    CURATED_LOCATIONS,
    FALLBACK_STREET_POOLS,
    GEO_DATA_PATH,
    LANDMARK_POOLS,
    LOCATION_POOLS,
    STREETVIEW_BOX_META,
    STREETVIEW_LAND_BOXES,
    GeoRoom,
    _DYNAMIC_SV_CACHE,
    _DYNAMIC_SV_LOCK,
    _pick_land_box,
    enrich_location_metadata,
    is_sv_circuit_open,
    normalize_difficulty,
    probe_google_streetview,
    reset_sv_circuit,
)
from hub import Hub
from server import api_create_room, app, CreateRoom, hub


def test_geo_locations_loaded_outside_data_and_not_dockerignored():
    assert GEO_DATA_PATH.exists(), f"Missing {GEO_DATA_PATH}"
    assert GEO_DATA_PATH.parent.name == "assets"

    dockerignore = (Path(__file__).resolve().parent.parent / ".dockerignore").read_text(encoding="utf-8")
    ignored_lines = [line.strip() for line in dockerignore.splitlines() if line.strip() and not line.startswith("#")]
    assert "assets/" not in ignored_lines and "assets" not in ignored_lines

    for reg in ("world", "vietnam", "asia", "europe", "north_america", "south_america", "africa", "oceania"):
        assert reg in GeoRoom.MODES
        assert len(LANDMARK_POOLS[reg]) >= 15, f"Too few landmarks for {reg}"
        assert "landmark" in LOCATION_POOLS[reg]

    assert len(FALLBACK_STREET_POOLS["world"]) >= 1000
    assert len(FALLBACK_STREET_POOLS["vietnam"]) >= 500


def test_global_and_landmark_modes_and_backcompat():
    assert normalize_difficulty("easy") == "landmark"
    assert normalize_difficulty("hard") == "global"
    assert normalize_difficulty("global") == "global"
    assert normalize_difficulty("landmark") == "landmark"

    room = GeoRoom("TEST", "europe")
    room.join("u1", "Player1", "#ff0000")
    room.handle("u1", "config", {"difficulty": "landmark"})

    assert room.config["difficulty"] == "landmark"
    assert room.mode == "europe"

    room.handle("u1", "start", {})
    assert len(room.deck) == 5
    landmark_coords = {(x["lat"], x["lng"]) for x in LANDMARK_POOLS["europe"]}
    for loc in room.deck:
        assert (loc["lat"], loc["lng"]) in landmark_coords
        assert loc.get("difficulty") == "landmark"


def test_full_5_round_match_transition_no_auto_timeout():
    room = GeoRoom("FLOW", "world")
    room.join("u1", "Player1", "#ff0000")
    room.handle("u1", "config", {"difficulty": "global", "roundTime": 45})
    room.handle("u1", "start", {})

    assert room.phase == "guessing"
    assert room.deadline > time.time() + 40.0

    for round_num in range(1, 6):
        assert room.phase == "guessing"
        assert room.round_idx == round_num - 1
        assert room.deadline > time.time() + 40.0
        # Calling tick() immediately after round start must NOT resolve prematurely
        assert room.tick() is False
        assert room.phase == "guessing"

        # Guess a valid point
        room.handle("u1", "guess", {"lat": 21.0285, "lng": 105.8542})
        assert room.phase == "round_result"
        assert room.round_results[0]["guessed"] is True

        # Clicking "next" twice (double click) or with stale round number must not skip rounds
        room.handle("u1", "next", {"round": round_num})
        room.handle("u1", "next", {"round": round_num})

    assert room.phase == "finished"
    assert room.status == "finished"
    assert len(room.round_history) == 5


def test_continent_mode_max_error_scaling():
    world_room = GeoRoom("WRLD", "world")
    vn_room = GeoRoom("VNM1", "vietnam")
    eu_room = GeoRoom("EUR1", "europe")
    assert vn_room._max_error_km() < eu_room._max_error_km() < world_room._max_error_km()


def test_healthz_get_head_and_create_room_with_difficulty():
    async def call_asgi(method: str, path: str):
        status_code = 0
        body_chunks = []
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
        }
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(event):
            nonlocal status_code
            if event["type"] == "http.response.start":
                status_code = event["status"]
            elif event["type"] == "http.response.body":
                body_chunks.append(event.get("body", b""))

        await app(scope, receive, send)
        return status_code, b"".join(body_chunks)

    st_get, body_get = asyncio.run(call_asgi("GET", "/healthz"))
    assert st_get == 200
    assert json.loads(body_get)["ok"] is True

    st_head, _ = asyncio.run(call_asgi("HEAD", "/healthz"))
    assert st_head == 200

    res = api_create_room(CreateRoom(channel="geo", mode="europe", config={"difficulty": "landmark"}))
    code = res["code"]
    created = hub.managers["geo"].get(code)
    assert created is not None
    assert created.mode == "europe"
    assert created.config["difficulty"] == "landmark"


def test_circuit_breaker_trips_after_3_failures_and_skips_network():
    reset_sv_circuit()
    call_count = 0

    def fake_urlopen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise OSError("network down")

    try:
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            assert probe_google_streetview(21.0, 105.8, timeout=0.5) is None
            assert is_sv_circuit_open() is False
            assert probe_google_streetview(21.0, 105.8, timeout=0.5) is None
            assert is_sv_circuit_open() is False
            assert probe_google_streetview(21.0, 105.8, timeout=0.5) is None
            assert is_sv_circuit_open() is True
            assert call_count == 3

            # Lần thứ 4 phải thoát ngay 0ms, không gọi urlopen nữa
            t0 = time.perf_counter()
            assert probe_google_streetview(21.0, 105.8, timeout=0.5) is None
            elapsed = time.perf_counter() - t0
            assert call_count == 3
            assert elapsed < 0.05
    finally:
        reset_sv_circuit()


def test_oceania_expanded_islands_have_valid_panos_and_box_meta():
    oc_lm = LANDMARK_POOLS["oceania"]
    oc_fb = FALLBACK_STREET_POOLS["oceania"]
    lm_countries = {x.get("country") for x in oc_lm}
    fb_countries = {x.get("country") for x in oc_fb}

    # Phải có thêm nhiều quốc đảo ngoài Úc và New Zealand
    assert len(lm_countries) >= 6, f"Expected diverse Oceania landmarks, got {lm_countries}"
    assert len(fb_countries) >= 6, f"Expected diverse Oceania fallback streets, got {fb_countries}"
    assert "Guam" in lm_countries or "Guam" in fb_countries
    assert "American Samoa" in lm_countries or "American Samoa" in fb_countries

    for item in oc_lm + oc_fb:
        pano = item.get("pano", "")
        assert len(pano) == 22 and not pano.startswith("CAoS"), f"Invalid pano: {item}"

    # Kiểm tra _pick_land_box("oceania") trả về default_cc và bán kính hợp lệ
    seen_ccs = set()
    for _ in range(120):
        _box, cc, rad = _pick_land_box("oceania")
        assert cc in GeoRoom.MODES or cc != ""
        assert 5000 <= rad <= 45000
        seen_ccs.add(cc)
    assert "AU" in seen_ccs and "NZ" in seen_ccs and len(seen_ccs) >= 4


def test_configurable_rounds_for_classic_and_solo():
    assert set(ALLOWED_ROUND_COUNTS) >= {5, 10, 15, 20}
    room = GeoRoom("RNDS", "oceania")
    room.join("u1", "SoloPlayer", "#38bdf8")
    room.handle("u1", "config", {"format": "classic", "difficulty": "landmark", "rounds": 10})
    assert room.config["rounds"] == 10
    assert room.total_rounds == 10

    room.handle("u1", "start", {})
    assert room.total_rounds == 10
    assert len(room.deck) == 10

    for r in range(1, 11):
        assert room.phase == "guessing"
        room.handle("u1", "guess", {"lat": -33.86, "lng": 151.21})
        assert room.phase == "round_result"
        room.handle("u1", "next", {"round": r})

    assert room.phase == "finished"
    assert len(room.round_history) == 10


def test_geo_bot_registered_and_works_in_all_modes():
    assert bots.supports("geo")
    assert "geo" in bots.bot_channels()

    for fmt in ("classic", "streak", "duel"):
        for level in ("easy", "normal", "hard"):
            room = GeoRoom(f"B{fmt[:2].upper()}{level[0].upper()}", "oceania")
            room.add_bot(level)  # Bot vào ghế 2 (Đội B), chừa ghế 1 (Đội A) cho người
            room.join("u1", "Human", "#6366f1")
            room.handle("u1", "config", {"format": fmt, "difficulty": "landmark", "rounds": 5, "roundTime": 60})
            room.handle("u1", "start", {})

            bot = room.bot_to_act()
            assert bot is not None and bot.bot is True
            engine = bots.make_bot("geo", bot.level)
            moves = engine.actions(room, bot.mark)
            assert len(moves) == 1 and moves[0][0] == "guess"
            lat = moves[0][1]["lat"]
            lng = moves[0][1]["lng"]
            assert -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0

            # Bot chốt sớm KHÔNG kích hoạt đồng hồ Panic 15s ép người chơi thật
            room.handle(bot.uid, moves[0][0], moves[0][1])
            assert room.phase == "guessing"
            assert room.panic_triggered is False

            # Ngay khi người chơi thật chốt, vòng kết thúc tức thì
            room.handle("u1", "guess", {"lat": -33.86, "lng": 151.21})
            assert room.phase == "round_result"

    # Kiểm tra thêm / đổi đội / gỡ nhiều Bot trong phòng chờ
    room = GeoRoom("MBOT", "world")
    room.join("u1", "Host", "#6366f1")
    room.handle("u1", "config", {"format": "duel"})
    room.handle("u1", "add_bot", {"mark": "2", "level": "hard"})
    room.handle("u1", "add_bot", {"mark": "3", "level": "easy"})
    assert len(room.bot_players()) == 2
    assert room.teams["2"] == "B"
    room.handle("u1", "switch_team", {"mark": "2"})
    assert room.teams["2"] == "A"
    room.handle("u1", "remove_bot", {"mark": "3"})
    assert len(room.bot_players()) == 1


def test_hub_geo_prefetch_offloads_to_thread_and_guards_loading_round():
    class DummySock:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    async def scenario():
        test_hub = Hub(Path(__file__).resolve().parent.parent / "data")
        room = test_hub.managers["geo"].create("world", config={"difficulty": "global", "rounds": 5})
        sock = DummySock()
        session = await test_hub.register(sock, "u_async_geo", "Tester")
        await test_hub.handle_game(session, "geo", "join", {"room": room.code})

        with _DYNAMIC_SV_LOCK:
            _DYNAMIC_SV_CACHE["world"].clear()

        # Giả lập prefetch mất 0.08s ở worker thread; trong lúc đó event loop vẫn phải chạy tick khác mượt mà
        heartbeat_ticks = 0

        async def heartbeat():
            nonlocal heartbeat_ticks
            for _ in range(4):
                await asyncio.sleep(0.015)
                heartbeat_ticks += 1

        def slow_prefetch(count: int):
            time.sleep(0.08)

        with mock.patch.object(room, "prefetch_dynamic_locations", side_effect=slow_prefetch):
            reset_sv_circuit()
            hb_task = asyncio.create_task(heartbeat())
            start_task = asyncio.create_task(test_hub.handle_game(session, "geo", "start", {}))
            await asyncio.sleep(0.02)
            # Trong lúc đang tải, loading_round phải là True và tick() không được can thiệp
            assert room.loading_round is True
            assert room.tick() is False
            await asyncio.gather(hb_task, start_task)

        assert room.loading_round is False
        assert room.phase == "guessing"
        assert heartbeat_ticks >= 3

    asyncio.run(scenario())


def test_rich_metadata_enrichment_no_bare_global_tag():
    samples = [
        {"lat": 28.2078, "lng": -177.3724, "name": "Midway Atoll (Toàn cầu 360°)", "country": "Midway Atoll"},
        {"lat": 13.5122, "lng": 144.8035, "name": "", "country": "Guam"},
        {"lat": -14.2738, "lng": -170.7021, "name": "Rte 001, Auto, Eastern District", "country": "American Samoa"},
        {"lat": -16.2498, "lng": 168.1355, "name": "", "country": "Vanuatu"},
        {"lat": -25.0667, "lng": -130.1000, "name": "", "country": "Quần đảo Pitcairn"},
        {"lat": 21.2766, "lng": -157.8278, "name": "", "country": "Hawaii"},
        {"lat": 21.0285, "lng": 105.8542, "name": "49 P. Lý Thái Tổ, Hà Nội", "country": "Việt Nam"},
    ]
    for loc in samples:
        mode = "vietnam" if loc["country"] == "Việt Nam" else "oceania"
        enriched = enrich_location_metadata(loc, mode)
        assert "(Toàn cầu 360°)" not in enriched["name"], f"Bare suffix still present: {enriched}"
        meta = enriched["meta"]
        assert meta["country"]
        assert meta["sovereign"]
        assert meta["subregion"]
        assert meta["coordsText"]
        if loc["country"] == "Midway Atoll":
            assert "Sand" in enriched["name"]
            assert "Hoa Kỳ" in meta["sovereign"]
            assert "Polynesia" in meta["subregion"]
        if loc["country"] == "American Samoa":
            assert "American Samoa" in enriched["name"]
            assert "Tutuila" in meta["island"]

    # Xác nhận match_view và round_history đều chứa target.meta
    room = GeoRoom("META", "oceania")
    room.join("u1", "GeoExplorer", "#38bdf8")
    room.handle("u1", "config", {"difficulty": "landmark", "rounds": 5})
    room.handle("u1", "start", {})
    room.handle("u1", "guess", {"lat": -33.86, "lng": 151.21})
    view = room.view("u1")
    assert view["target"] is not None
    assert "meta" in view["target"]
    assert view["target"]["meta"]["coordsText"]
    assert "meta" in room.round_history[0]["target"]


def test_oceania_balanced_weights_landmarks_and_natural_random():
    boxes = STREETVIEW_LAND_BOXES["oceania"]
    total_w = sum(STREETVIEW_BOX_META[b][2] for b in boxes)
    au_nz_w = sum(STREETVIEW_BOX_META[b][2] for b in boxes if STREETVIEW_BOX_META[b][0] in ("AU", "NZ"))
    island_w = total_w - au_nz_w

    au_nz_pct = au_nz_w / total_w
    island_pct = island_w / total_w
    assert 0.55 <= au_nz_pct <= 0.65, f"Expected AU+NZ ~60%, got {au_nz_pct:.2%}"
    assert 0.35 <= island_pct <= 0.45, f"Expected Islands ~40%, got {island_pct:.2%}"

    # Kho địa danh Oceania phải được mở rộng >= 140 điểm đã xác thực Pano 22 ký tự
    oc_lms = LANDMARK_POOLS["oceania"]
    assert len(oc_lms) >= 140, f"Expected >= 140 Oceania landmarks, got {len(oc_lms)}"
    lm_countries = {x.get("country") for x in oc_lms}
    assert "Hawaii" in lm_countries and "Guam" in lm_countries and "American Samoa" in lm_countries
    for item in oc_lms:
        assert len(item.get("pano", "")) == 22

    # Kiểm tra lấy mẫu ngẫu nhiên với Soft Cooldown vẫn đa dạng quốc đảo và tự nhiên
    recent: list[str] = []
    seen_ccs: set[str] = set()
    for _ in range(120):
        _box, cc, _rad = _pick_land_box("oceania", recent_regions=recent)
        seen_ccs.add(cc)
        recent.append(cc)
        if len(recent) > 6:
            recent.pop(0)
    assert len(seen_ccs) >= 8, f"Expected at least 8 Oceania territories sampled, got {seen_ccs}"
