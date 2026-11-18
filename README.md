# 🎮 Game Hub — Real-Time Multiplayer Gaming & Social Platform

A modern, lightweight, full-stack web platform for **real-time multiplayer games, group chat, and custom avatars**, built with **FastAPI**, **WebSockets + SSE/Long-Polling fallback**, **PostgreSQL / JSON storage**, and **Vanilla ES6 Modules** (zero frontend build step required).

Supports instant play without account registration, **16 dark/light themes**, **full Vietnamese / English (VI/EN) localization**, **desktop & mobile responsive layouts**, and **AI bots** across 7 game modes.

---

## 🌟 Games & Apps

### 🌍 1. GeoGuessr (Địa Đồ)
- **8 Map Regions**: **World**, **Vietnam (63 provinces)**, **Asia**, **Europe**, **North America**, **South America**, **Africa**, and **Oceania**.
- **2 Modes**:
  - **Global (100% Street View)**: Real-time worldwide Google Street View with background RAM pre-warming (`0ms` round start) and strict ISO country-code boundary validation.
  - **Landmarks**: Curated & verified collection of **1,600+ official 22-character `pano` ID** locations across all regions (zero black screens).
- **3 Formats & 3 Rules**: Classic 5-Round, Country/Province Streak, and Team/Boss Survival Duels (`6,000` / `12,000` HP); **Moving**, **No Move (NM)**, and **NMPZ**.

### 🏳️ 2. Flags & Capitals (Đố Cờ & Thủ Đô)
- **197 Countries & Territories** filtered by **World**, **Asia**, **Europe**, **Americas**, **Africa**, or **Oceania**.
- **3 Quiz Types**: Flag → Country, Country → Capital, or Mixed.
- **2 Answer Modes**:
  - **Multiple Choice (A/B/C/D)**: Continent-aware distractors with keyboard hotkeys `1`–`4`.
  - **Type Answer**: Accent-insensitive VI/EN/alias matching (e.g. `viet nam` / `Việt Nam`, `ha noi` / `Hanoi`, `USA` / `Mỹ`), 1-typo tolerance, and quick autocomplete suggestions.
- **Multiplayer & AI Bots**: 1–6 players with speed + streak scoring and 3 AI bot difficulty levels.

### 🃏 3. Liar's Deck (Sòng Bịp)
- 2–4 player bluffing card game with **Devil Mode (Ma Vương)**, Colt Python .357 Russian roulette animations & sound effects, quick taunt bubbles, synced player avatars, and AI bots.

### ♠️ 4. Texas Hold'em Poker (Xì Tố)
- 2–6 players **Cash** & **Knockout Tournament** tables, **Run It Twice**, pre-actions, daily profit leaderboard, and AI bots with distinct playstyles.

### ♟️ 5. Classic Strategy & Board Games
- **Gomoku / Caro**: 3×3 XO up to 50×50 grids with incremental DOM updates and AI bot.
- **Chess (Cờ Vua)**: Full FIDE rules (castling, en passant, promotion, draws), chess clocks, and AI bot.
- **Xiangqi (Cờ Tướng)**: 9×10 Chinese Chess with full piece rules, clocks, and Alpha-Beta AI bot.
- **Battleship (Bắn Tàu)**: 10×10 naval combat with auto-place and smart targeting AI bot.

---

## 🚀 Platform Highlights

- **🛡️ 3-Tier Real-Time Transport (`WebSocket → SSE → HTTP Long-Polling`)**: Automatically falls back to Server-Sent Events or HTTP Long-Polling when corporate firewalls or proxies block WebSocket upgrades.
- **💬 Real-Time Group Chat**:
  - Multi-channel chat with unread badges, replies, typing indicators, and desktop notifications.
  - **Image uploads** (auto-resized client-side) & **file attachments up to 15 MB** (drag-and-drop, paste, safe `attachment` downloads).
  - **380+ Emojis**, **20 Kaomoji**, persistent **Recent** history, and **24 message reactions**.
- **🎨 16 Themes & Polished UI**: 10 Dark + 6 Light themes with `"Match system"`, `Alt + T` quick cycling, custom glassmorphism dropdowns, and collapsible desktop sidebar.
- **🎭 Avatar Studio**: Procedural SVG/PNG avatar generator (8 quick presets + 4 customizer tabs) synced across chat and all game rooms, plus distinct **Robot SVG avatars** for AI bots.
- **🌐 Bilingual (VI / EN) & Mobile-First**: Instant language switching without dropping rooms, plus responsive touch layouts for mobile browsers.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [WebSockets](https://websockets.readthedocs.io/), [Pillow](https://python-pillow.org/), [psycopg3](https://www.psycopg.org/)
- **Frontend**: Vanilla ES6 Modules, CSS Variables / Grid / Flexbox, SVG, [Leaflet](https://leafletjs.com/)
- **Storage**: PostgreSQL (optional via `DATABASE_URL`) or local JSON + filesystem (`data/`)
- **Edge Proxy (Optional)**: Cloudflare Pages `_worker.js` (`cf-pages/_worker.js`)

---

## 📂 Repository Structure

```text
├── server.py                  # FastAPI ASGI app, HTTP/WS/SSE/Long-Polling & upload routes
├── hub.py                     # Central WebSocket/RT Hub, presence & room orchestration
├── games.py                   # Base SeatedRoom / GameRoom & RoomManager
├── db.py                      # PostgreSQL schema & connection pool (optional)
│
├── geoguessr.py               # GeoGuessr engine & verified Street View RPC service
├── flags_quiz.py              # Flags & Capitals quiz engine + smart text matcher
├── bluff.py                   # Liar's Deck engine & revolver mechanics
├── poker.py / poker_hand.py   # Texas Hold'em engine & 7-card evaluator
├── chessgame.py / xiangqi.py  # Chess & Xiangqi rules engines
├── caro.py / battleship.py    # Caro & Battleship engines
├── bot_*.py / bots.py         # Non-blocking AI bot engines & registry
├── chat.py / avatar.py        # Chat history, file/image uploads & avatar store
│
├── assets/
│   ├── countries_quiz.json    # 197 countries & capitals bilingual dataset
│   └── geo_locations.json     # Verified 22-char Street View pano datasets
├── cf-pages/_worker.js        # Cloudflare Pages reverse proxy (reads env.BACKEND_HOST)
├── static/
│   ├── index.html             # SPA shell & anti-FOUC theme bootstrap
│   ├── css/                   # app.css, apps.css, poker.css, themes.css
│   └── js/                    # dom.js, net.js, ui.js, i18n.js, themes.js, emoji.js, views/
└── tests/                     # Automated test suite
```

---

## 💻 Getting Started

### 1. Clone & install dependencies
```bash
git clone https://github.com/TungNamNguyen/game-hub.git
cd game-hub
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run locally
```bash
python server.py
# Or with auto-reload:
uvicorn server:app --host 0.0.0.0 --port 8780 --reload
```
Open [http://127.0.0.1:8780](http://127.0.0.1:8780) in your browser.

---

## 🧪 Verification & Tests

```bash
# Python unit tests
python -m unittest discover -s tests -p "test_*.py"

# Python & JavaScript syntax checks
python -m py_compile *.py
for f in $(find static/js -name '*.js'); do node --check "$f" || exit 1; done
```

---

## 🐳 Docker & Deployment

```bash
docker build -t game-hub .
docker run -p 7860:7860 -e PORT=7860 game-hub
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8780` (`7860` in Docker) | HTTP/WebSocket listening port |
| `DATABASE_URL` | *None* | Optional PostgreSQL connection string (falls back to `data/` JSON if unset) |
| `BOT_CONCURRENCY` | `2` | Max concurrent AI bot evaluations |
| `BACKEND_HOST` | *Required on CF Pages* | Backend hostname configured in Cloudflare Pages **Variables & Secrets** for `cf-pages/_worker.js` |
| `RENDER_URL` | *Optional Secret* | GitHub Actions secret for `.github/workflows/keepalive.yml` |

---

## 📄 License

Distributed under the MIT License.
