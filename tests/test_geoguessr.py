"""Kiểm thử Địa Đồ (GeoGuessr) và HTTP healthcheck / keepalive."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from geoguessr import (
    CURATED_LOCATIONS,
    FALLBACK_STREET_POOLS,
    GEO_DATA_PATH,
    LANDMARK_POOLS,
    LOCATION_POOLS,
    GeoRoom,
    normalize_difficulty,
)
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
