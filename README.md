---
title: Game Hub
emoji: 🎮
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# 🎮 Game Hub — Real-Time Multiplayer Gaming & Chat Platform

A modern, lightweight, full-featured web platform for real-time multiplayer board & party games, featuring built-in AI bots, dynamic lobbies, global chat, custom avatars, and full bilingual support (English / Vietnamese).

Built with **FastAPI**, **WebSockets**, **PostgreSQL / SQLite**, and vanilla **Modern ES6 JavaScript** (zero heavy frontend build toolchains required).

---

## 🌟 Featured Games

### 🌍 1. GeoGuessr (Địa Đồ)
- **8 Map Regions**: **World**, **Vietnam**, **Asia**, **Europe**, **North America**, **South America**, **Africa**, and **Oceania**.
- **2 Focused Game Modes**:
  - **Global (100% Real-Time Street View)**: Unlimited worldwide locations powered by multi-threaded Google Street View RPC pre-warming (0ms round start).
  - **Landmarks**: Curated collection of 400+ authentic iconic landmarks, UNESCO sites, and regional monuments across all 63 provinces of Vietnam and 6 continents.
- **Multiple Formats & Rules**:
  - *Formats*: Classic 5-Round, Streak Mode (Country / Vietnam Province), and Team/Boss Survival Duels.
  - *Movement Rules*: **Moving**, **No Move (NM)** with 360° pan/zoom, and **NMPZ** (No Move, Pan, Zoom).
- **Detailed Round Analytics**: Accurate distance calculation (Haversine), cardinal direction offsets, keyboard shortcuts (`Space`, `R`, `M`), and one-click Google Maps links.

### 🃏 2. Liar's Deck (Sòng Bịp)
- Inspired by the intense bluffing card game for 2–4 players.
- **Devil Mode (Ma Vương)** & Custom Chambers: Tension-filled Colt Python .357 Russian roulette mechanics with realistic sound & recoil animations.
- **Sequential Dramatic Card Reveal**: Cards flip one by one when a bluff is called ("BỊP! / LIAR!").
- **Quick Taunt Bubbles**: Send in-game reaction taunts during opponents' turns.
- **Smart AI Bots**: Built-in bluffing bots with diverse risk profiles.

### ♠️ 3. Texas Hold'em Poker (Xì Tố)
- Standard No-Limit Texas Hold'em rules with Pot-Limit / No-Limit betting rounds.
- **AI Poker Bots**: Support single-player games with bots featuring distinct playing styles (Tight-Passive, Aggressive, Bluffer).
- **Daily Leaderboard**: Track daily champions and chips.

### ♟️ 4. Classic Strategy & Board Games
- **Gomoku / Caro (Cờ Caro)**: Support standard & large grids (15×15, 20×20, 35×35, 50×50) with optimized incremental DOM rendering and Minimax AI bot.
- **Chess (Cờ Vua)**: Full FIDE rules (castling, en passant, promotion), timer chess clocks, undo/draw offers, and multi-difficulty AI bot.
- **Xiangqi (Cờ Tướng)**: Complete Chinese Chess rules, board visualization, clocks, and Alpha-Beta pruning bot.
- **Battleship (Bắn Tàu)**: Classic 10×10 naval combat with radar feedback and smart targeting AI bot.

---

## 🚀 Key Platform Features

- **🌐 Full Bilingual Support (i18n)**: One-click instant switching between **English (EN)** and **Vietnamese (VI)** without refreshing or dropping active WebSocket rooms.
- **⚡ Real-Time WebSocket Infrastructure**: Instant state synchronization, automatic reconnection, sub-millisecond game state updates.
- **🤖 Dedicated AI Bot Engine**: Non-blocking bot evaluation offloaded to asynchronous background thread pools to prevent event loop starvation.
- **💬 Real-Time Chat & Social**:
  - Global lobby chat and dedicated per-room game chat with preserved input buffers during re-renders.
  - Image attachments, custom emoji pickers, and quick reactions.
- **🎭 Procedural Vector Avatar Generator**: Built-in interactive SVG avatar studio (gender, hairstyles, facial hair, skin tones, eyewear, clothing, accessories).
- **🔒 Secure Anonymous Sessions**: Frictionless instant play without mandatory account registration; protected via client-bound session tokens to prevent UID spoofing.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [WebSockets](https://websockets.readthedocs.io/), [Pillow](https://python-pillow.org/), [psycopg3](https://www.psycopg.org/)
- **Frontend**: Vanilla Modern JavaScript (ES Modules), CSS3 Variables / Flexbox / Grid, HTML5 Canvas / SVG, Leaflet.js (for map guesses)
- **Database**: PostgreSQL (Production / Render / Supabase) with automatic SQLite fallback for local development
- **Deployment**: Docker, Hugging Face Spaces, Render, or self-hosted VPS

---

## 📂 Repository Structure

```text
├── server.py              # Main ASGI application entrypoint & HTTP routes
├── hub.py                 # Core WebSocket Hub, client directory & state sync
├── games.py               # Game room orchestration and lobby handlers
├── db.py                  # Database abstraction (PostgreSQL / SQLite)
│
├── geoguessr.py           # GeoGuessr game logic & Street View coordinate service
├── bluff.py               # Liar's Deck logic & Russian roulette resolution
├── poker.py               # Texas Hold'em game state engine
├── poker_hand.py          # 7-card poker hand evaluation & ranking
├── chessgame.py           # Chess engine & move validation
├── xiangqi.py             # Xiangqi (Chinese Chess) rules & engine
├── caro.py                # Gomoku / Caro board logic
├── battleship.py          # Battleship grid & hit detection
│
├── bot_*.py               # AI Bots (bot_chess, bot_xiangqi, bot_poker, bot_bluff, bot_caro, bot_ship)
├── avatar.py              # Procedural SVG avatar rendering engine
├── chat.py                # Chat history, storage & broadcast manager
│
├── assets/                # Static datasets (e.g. geo_locations.json)
├── static/                # Frontend web application
│   ├── index.html         # Single Page Application container
│   ├── css/               # Modular stylesheet rules & responsive layouts
│   └── js/                # Client-side scripts
│       ├── i18n.js        # Bilingual dictionary & locale switcher (EN/VI)
│       └── views/         # Per-game client view controllers
├── tests/                 # Automated test suite (pytest)
├── docs/                  # Technical documentation & game specifications
└── requirements.txt       # Python dependencies
```

---

## 💻 Getting Started

### Prerequisites
- Python 3.11 or 3.12+
- Git

### 1. Clone the repository
```bash
git clone https://github.com/TungNamNguyen/game-hub.git
cd game-hub
```

### 2. Create a virtual environment & install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the development server
```bash
python server.py
# Or using uvicorn directly:
uvicorn server:app --host 0.0.0.0 --port 7860 --reload
```
Open [http://localhost:7860](http://localhost:7860) in your browser.

---

## 🧪 Running Tests

Run the comprehensive test suite covering game engines, AI bot decisions, and hand evaluators:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

Verify frontend syntax and internationalization parity:
```bash
for f in $(find static/js -name '*.js'); do node --check "$f"; done
```

---

## 🐳 Docker & Multi-Platform Free Deployment

You can build and run the application locally using Docker:

```bash
docker build -t game-hub .
docker run -p 7860:7860 game-hub
```

### Parallel Free Hosting Options (Bypass Corporate Firewalls)
This repository supports zero-config parallel deployment on multiple free platforms simultaneously:
- **Koyeb** *(Free Tier — `*.koyeb.app`)*: Connect this GitHub repo directly using the root `Dockerfile` with `PORT=7860` and HTTP health check `/healthz`.
- **Render** *(uses `render.yaml`)*: Connect this GitHub repo directly as a Docker Web Service.
- **Google Cloud Run** *(Free Tier — `*.run.app`)*: Deploy the `Dockerfile` directly with `PORT=7860`.
- **Shared State**: Point `DATABASE_URL` across all instances to a single free PostgreSQL database (Supabase / Neon) to sync profiles, chat, and leaderboards.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `7860` | Server listening port |
| `DATABASE_URL` | *None* | PostgreSQL connection string (falls back to local SQLite if omitted) |
| `BOT_CONCURRENCY` | `1` | Max concurrent AI bot calculations |
| `BOT_BUDGET_SCALE` | `0.5` | Bot search depth & time budget multiplier for constrained CPU environments |

---

## 📄 License

Distributed under the MIT License. Feel free to use, modify, and contribute!
