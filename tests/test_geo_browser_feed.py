"""Kiểm thử tính năng trình duyệt nạp hộ Google Street View (sv_feed) và ẩn tọa độ pha guessing."""
from __future__ import annotations

import asyncio
import math

import geoguessr
from geoguessr import (
    _DYNAMIC_SV_CACHE,
    _DYNAMIC_SV_LOCK,
    _SV_CACHE_MAX,
    GeoRoom,
    _sanitize_client_sv,
    _sv_record_network_failure,
    ingest_client_streetview,
    is_sv_circuit_open,
    reset_sv_circuit,
    sv_client_config,
)
from server import api_geo_sv_config


def _trip_circuit() -> None:
    reset_sv_circuit()
    for _ in range(3):
        _sv_record_network_failure()
    assert is_sv_circuit_open() is True


def _sample_sv(idx: int = 0, *, lat: float = 48.8566, lng: float = 2.3522, cc: str = "FR", addr: str = "Paris") -> dict:
    pano = f"AbCdEfGhIjKlMnOpQr{idx:04d}"[:22]
    return {
        "lat": round(lat + idx * 0.01, 5),
        "lng": round(lng + idx * 0.01, 5),
        "heading": (idx * 37) % 360,
        "pano": pano,
        "address": addr,
        "country_code": cc,
    }


def test_sanitize_client_sv_rejects_invalid_and_cleans_valid():
    assert _sanitize_client_sv("not-a-dict") is None
    assert _sanitize_client_sv({"lat": math.nan, "lng": 0, "pano": "A" * 22}) is None
    assert _sanitize_client_sv({"lat": 91.0, "lng": 0, "pano": "A" * 22}) is None
    assert _sanitize_client_sv({"lat": 10.0, "lng": 200.0, "pano": "A" * 22}) is None
    assert _sanitize_client_sv({"lat": 10.0, "lng": 10.0, "pano": "short"}) is None
    assert _sanitize_client_sv({"lat": 10.0, "lng": 10.0, "pano": "CAoS" + "A" * 18}) is None

    clean = _sanitize_client_sv({
        "lat": 21.0285123,
        "lng": 105.8542123,
        "heading": 450,
        "pano": "ValidPanoId1234567890A",
        "country_code": "bad-cc-99",
        "address": "Hà Nội\x00\x07" + "x" * 250,
    })
    assert clean is not None
    assert clean["heading"] == 90
    assert clean["country_code"] == ""
    assert "\x00" not in clean["address"]
    assert len(clean["address"]) == 200


def test_ingest_dedup_cap_and_mode_filtering():
    with _DYNAMIC_SV_LOCK:
        _DYNAMIC_SV_CACHE["europe"].clear()
    try:
        # Điểm Việt Nam không thuộc europe -> bị lọc bỏ
        vn_item = _sample_sv(1, lat=21.0285, lng=105.8542, cc="VN", addr="Hanoi")
        fr_item = _sample_sv(2, lat=48.8566, lng=2.3522, cc="FR", addr="Paris")
        fr_dup_pano = {**fr_item, "lat": 48.9999}
        fr_dup_coord = {**fr_item, "pano": "UniquePanoId1234567890"}

        added = ingest_client_streetview("europe", [vn_item, fr_item, fr_dup_pano, fr_dup_coord], feeder_uid="u1")
        assert added == 1
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 1
            assert _DYNAMIC_SV_CACHE["europe"][0]["source"] == "browser"

        # Nạp vượt trần _SV_CACHE_MAX -> không vượt quá 40
        for batch in range(5):
            items = [_sample_sv(batch * 12 + i + 10, lat=48.0 + batch * 0.2, lng=2.0 + i * 0.05, cc="FR") for i in range(12)]
            ingest_client_streetview("europe", items, feeder_uid="u1")
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) <= _SV_CACHE_MAX
    finally:
        with _DYNAMIC_SV_LOCK:
            _DYNAMIC_SV_CACHE["europe"].clear()


def test_ingest_tags_hawaii_hi_in_oceania():
    with _DYNAMIC_SV_LOCK:
        _DYNAMIC_SV_CACHE["oceania"].clear()
    try:
        # Honolulu nằm trong khung Hawaii của STREETVIEW_BOX_META (trả US -> gắn HI)
        hi_item = _sample_sv(1, lat=21.3069, lng=-157.8583, cc="US", addr="Honolulu, Hawaii")
        added = ingest_client_streetview("oceania", [hi_item], feeder_uid="u1")
        assert added == 1
        with _DYNAMIC_SV_LOCK:
            assert _DYNAMIC_SV_CACHE["oceania"][0]["cc"] == "HI"
    finally:
        with _DYNAMIC_SV_LOCK:
            _DYNAMIC_SV_CACHE["oceania"].clear()


def test_sv_feed_request_only_for_feeder_when_circuit_open():
    with _DYNAMIC_SV_LOCK:
        _DYNAMIC_SV_CACHE["world"].clear()
    try:
        reset_sv_circuit()
        room = GeoRoom("FEED1", "world")
        room.join("u1", "Alice", "#6366f1")
        room.join("u2", "Bob", "#ec4899")

        # Circuit đóng -> không ai nhận svFeed
        assert room.match_view("u1")["svFeed"] is None
        assert room.match_view("u2")["svFeed"] is None

        # Circuit mở -> chỉ feeder (u1) nhận svFeed
        _trip_circuit()
        req1 = room.match_view("u1")["svFeed"]
        assert req1 is not None
        assert req1["mode"] == "world"
        assert 1 <= req1["need"] <= 12
        assert room.match_view("u2")["svFeed"] is None
    finally:
        reset_sv_circuit()


def test_sv_feed_handle_guards_circuit_feeder_rate_limit_and_mode():
    with _DYNAMIC_SV_LOCK:
        _DYNAMIC_SV_CACHE["europe"].clear()
    try:
        reset_sv_circuit()
        room = GeoRoom("FEED2", "europe")
        room.join("u1", "Alice", "#6366f1")
        room.join("u2", "Bob", "#ec4899")

        item1 = _sample_sv(1, lat=48.8566, lng=2.3522, cc="FR")
        item2 = _sample_sv(2, lat=52.52, lng=13.405, cc="DE")

        # Circuit đóng -> bỏ qua
        room.handle("u1", "sv_feed", {"mode": "europe", "items": [item1]})
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 0

        _trip_circuit()
        # Không phải feeder (u2) -> bỏ qua
        room.handle("u2", "sv_feed", {"mode": "europe", "items": [item1]})
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 0

        # Sai mode -> bỏ qua
        room.handle("u1", "sv_feed", {"mode": "world", "items": [item1]})
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 0

        # Hợp lệ -> nhận
        room.handle("u1", "sv_feed", {"mode": "europe", "items": [item1]})
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 1

        # Gửi tiếp ngay lập tức (< 1s) -> bị rate-limit bỏ qua
        room.handle("u1", "sv_feed", {"mode": "europe", "items": [item2]})
        with _DYNAMIC_SV_LOCK:
            assert len(_DYNAMIC_SV_CACHE["europe"]) == 1
    finally:
        reset_sv_circuit()
        with _DYNAMIC_SV_LOCK:
            _DYNAMIC_SV_CACHE["europe"].clear()


def test_round_2_draws_from_browser_feed_and_hides_coords_during_guessing():
    with _DYNAMIC_SV_LOCK:
        _DYNAMIC_SV_CACHE["europe"].clear()
    try:
        _trip_circuit()
        room = GeoRoom("FEED3", "europe")
        room.join("u1", "Alice", "#6366f1")
        room.handle("u1", "start", {}, allow_live_fetch=False)

        # Vòng 1 chỉ bốc trước 1 điểm tĩnh khi circuit mở
        assert len(room.deck) == 1
        # Pha guessing phải ẩn lat/lng khi đã có pano
        v_guess = room.match_view("u1")
        assert v_guess["streetView"]["pano"]
        assert "lat" not in v_guess["streetView"]
        assert "lng" not in v_guess["streetView"]
        assert "image" not in v_guess

        # Trình duyệt nạp hộ điểm Street View thật cho vòng 2
        browser_item = _sample_sv(5, lat=48.8566, lng=2.3522, cc="FR", addr="Rue de Rivoli, Paris")
        room.handle("u1", "sv_feed", {"mode": "europe", "items": [browser_item]})

        # Kết thúc vòng 1 -> sang vòng 2 phải lấy điểm từ trình duyệt nạp
        room.handle("u1", "guess", {"lat": 48.0, "lng": 2.0})
        assert room.phase == "round_result"
        v_reveal = room.match_view("u1")
        assert "lat" in v_reveal["streetView"] and "lng" in v_reveal["streetView"]

        room.handle("u1", "next", {}, allow_live_fetch=False)
        assert room.round_idx == 1
        assert room.deck[1]["pano"] == browser_item["pano"]
        assert room.deck[1].get("source") == "browser"
    finally:
        reset_sv_circuit()
        with _DYNAMIC_SV_LOCK:
            _DYNAMIC_SV_CACHE["europe"].clear()


def test_sv_client_config_format_and_endpoint():
    cfg = sv_client_config()
    assert cfg["rpcUrl"] == geoguessr._SV_RPC_URL
    assert "world" in cfg["modes"]
    assert "oceania" in cfg["modes"]
    for mode_cfg in cfg["modes"].values():
        boxes = mode_cfg["boxes"]
        assert isinstance(boxes, list) and len(boxes) > 0
        for row in boxes:
            assert len(row) == 6
            assert row[0] < row[1] and row[2] < row[3]
            assert row[4] > 0 and row[5] > 0

    ep = asyncio.run(api_geo_sv_config())
    assert ep["rpcUrl"] == cfg["rpcUrl"]
