"""Đố Quốc Kỳ & Thủ Đô — Trò chơi đoán tên nước từ lá cờ và đoán thủ đô từ tên nước."""
from __future__ import annotations

import json
from pathlib import Path
import random
import re
import time
import unicodedata

from games import GameError, SeatedRoom

COUNTRIES_DATA_PATH = Path(__file__).resolve().parent / "assets" / "countries_quiz.json"

QUIZ_TYPES = ("flag", "capital", "mixed")
ANSWER_MODES = ("choice", "typing")
ALLOWED_QUESTION_COUNTS = (10, 15, 20)
ALLOWED_ROUND_TIMES = (10, 15, 20, 30)
REVEAL_SECONDS = 3.2
GRACE_SECONDS = 0.15
MAX_TYPING_TRIES = 5
TYPING_COOLDOWN = 0.35


def _load_countries() -> list[dict]:
    if not COUNTRIES_DATA_PATH.exists():
        return []
    raw = json.loads(COUNTRIES_DATA_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    for item in raw:
        code = str(item.get("code", "")).strip().lower()
        if not code:
            continue
        out.append({
            "code": code,
            "continent": str(item.get("continent", "")).strip().lower(),
            "nameVi": str(item.get("nameVi", "")).strip(),
            "nameEn": str(item.get("nameEn", "")).strip(),
            "aliases": [str(a).strip() for a in item.get("aliases", []) if a],
            "capitalVi": str(item.get("capitalVi", "")).strip(),
            "capitalEn": str(item.get("capitalEn", "")).strip(),
            "capitalAliases": [str(a).strip() for a in item.get("capitalAliases", []) if a],
        })
    return out


COUNTRIES: list[dict] = _load_countries()
COUNTRY_BY_CODE: dict[str, dict] = {c["code"]: c for c in COUNTRIES}


def normalize_answer(text: str) -> str:
    """Chuẩn hóa câu trả lời: bỏ dấu tiếng Việt, bỏ ký tự đặc biệt, gộp khoảng trắng."""
    s = str(text or "").strip().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def _edit_distance_le_one(a: str, b: str) -> bool:
    """Kiểm tra khoảng cách Damerau-Levenshtein <= 1 để châm chước lỗi gõ 1 phím."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            return a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]
        return False
    # Đảm bảo a ngắn hơn b đúng 1 ký tự
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = skips = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            skips += 1
            if skips > 1:
                return False
            j += 1
    return True


def _accepted_answers(item: dict, q_kind: str) -> list[str]:
    if q_kind == "capital":
        raw = [item["capitalVi"], item["capitalEn"], *item.get("capitalAliases", [])]
    else:
        raw = [item["nameVi"], item["nameEn"], *item.get("aliases", [])]
    seen: set[str] = set()
    out: list[str] = []
    for val in raw:
        norm = normalize_answer(val)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def match_answer(raw_guess: str, item: dict, q_kind: str) -> bool:
    """Kiểm tra đáp án tự gõ khớp với tên nước hoặc thủ đô (VI/EN/không dấu/chính tả gần)."""
    guess = normalize_answer(raw_guess)
    if not guess:
        return False
    targets = _accepted_answers(item, q_kind)
    for tgt in targets:
        if guess == tgt:
            return True
        if len(tgt) >= 7 and len(guess) >= 7 and _edit_distance_le_one(guess, tgt):
            return True
    return False


def build_choices(target: dict, pool: list[dict], q_kind: str) -> list[dict]:
    """Tạo 4 lựa chọn A/B/C/D (ưu tiên 3 đáp án nhiễu cùng châu lục với đáp án đúng)."""
    def _label(c: dict) -> tuple[str, str]:
        if q_kind == "capital":
            return c["capitalVi"], c["capitalEn"]
        return c["nameVi"], c["nameEn"]

    tgt_vi, tgt_en = _label(target)
    used_norms = {normalize_answer(tgt_vi), normalize_answer(tgt_en)}
    same_cont = [c for c in pool if c["code"] != target["code"] and c["continent"] == target["continent"]]
    others = [c for c in COUNTRIES if c["code"] != target["code"] and c["continent"] != target["continent"]]
    random.shuffle(same_cont)
    random.shuffle(others)

    distractors: list[dict] = []
    for cand in same_cont + others:
        l_vi, l_en = _label(cand)
        nv, ne = normalize_answer(l_vi), normalize_answer(l_en)
        if nv in used_norms or ne in used_norms:
            continue
        used_norms.add(nv)
        used_norms.add(ne)
        distractors.append(cand)
        if len(distractors) >= 3:
            break

    opts = [
        {"code": target["code"], "labelVi": tgt_vi, "labelEn": tgt_en},
        *[
            {"code": d["code"], "labelVi": _label(d)[0], "labelEn": _label(d)[1]}
            for d in distractors
        ],
    ]
    random.shuffle(opts)
    return opts


def flag_svg_url(code: str) -> str:
    return f"https://flagcdn.com/{code.lower()}.svg"


class FlagsRoom(SeatedRoom):
    CHANNEL = "flags"
    SEATS = ("1", "2", "3", "4", "5", "6")
    HAS_CLOCK = True
    START_STATUS = "playing"
    DEFAULT_MODE = "world"
    MODES = {
        "world": {"label": "Thế giới (197)"},
        "asia": {"label": "Châu Á (48)"},
        "europe": {"label": "Châu Âu (46)"},
        "americas": {"label": "Châu Mỹ (35)"},
        "africa": {"label": "Châu Phi (54)"},
        "oceania": {"label": "Châu Đại Dương (14)"},
    }

    def __init__(self, code: str, mode: str) -> None:
        super().__init__(code, mode)
        self.config: dict = {
            "quizType": "flag",      # flag | capital | mixed
            "answerMode": "choice",  # choice | typing
            "questionCount": 10,     # 10 | 15 | 20
            "roundTime": 15,         # 10 | 15 | 20 | 30
        }
        self.reset_match()

    def _seat_label(self, mark: str) -> str:
        return f"Ghế {mark}"

    def _seated_marks(self) -> list[str]:
        return [m for m in self.SEATS if self.seat(m) is not None]

    def _pool(self) -> list[dict]:
        if self.mode == "world":
            return list(COUNTRIES)
        filtered = [c for c in COUNTRIES if c["continent"] == self.mode]
        return filtered or list(COUNTRIES)

    def reset_match(self) -> None:
        self.phase: str = "waiting"  # waiting | question | reveal | finished
        self.q_idx: int = 0
        self.questions: list[dict] = []
        self.answers: dict[str, dict] = {}       # mark -> {"correct": bool, "choice": str, "text": str, "points": int, "ms": int}
        self.wrong_tries: dict[str, list[str]] = {}
        self.last_try_at: dict[str, float] = {}
        self.history: list[dict] = []
        self.points: dict[str, int] = {m: 0 for m in self.SEATS}
        self.streaks: dict[str, int] = {m: 0 for m in self.SEATS}
        self.best_streaks: dict[str, int] = {m: 0 for m in self.SEATS}
        self.correct_counts: dict[str, int] = {m: 0 for m in self.SEATS}
        self.started_at: float = 0.0
        self.deadline: float = 0.0

    def _try_start(self) -> None:
        # Cho phép 1-6 người tùy chỉnh chế độ trước khi bấm Bắt đầu.
        return

    def apply_initial_config(self, config: dict) -> None:
        self._apply_config(config)

    def _apply_config(self, msg: dict) -> None:
        new_mode = msg.get("mode")
        if new_mode in self.MODES:
            self.mode = new_mode
        qt = msg.get("quizType")
        if qt in QUIZ_TYPES:
            self.config["quizType"] = qt
        am = msg.get("answerMode")
        if am in ANSWER_MODES:
            self.config["answerMode"] = am
        qc = msg.get("questionCount")
        if qc in ALLOWED_QUESTION_COUNTS:
            self.config["questionCount"] = int(qc)
        rt = msg.get("roundTime")
        if rt in ALLOWED_ROUND_TIMES:
            self.config["roundTime"] = int(rt)
        self.touched = time.time()

    def _start_match(self) -> None:
        seated = self._seated_marks()
        if not seated:
            raise GameError("Cần ít nhất 1 người chơi ngồi vào ghế để bắt đầu.")

        pool = self._pool()
        random.shuffle(pool)
        count = min(int(self.config.get("questionCount", 10)), len(pool))
        chosen = pool[:count]
        q_type = self.config.get("quizType", "flag")
        a_mode = self.config.get("answerMode", "choice")

        deck: list[dict] = []
        for idx, item in enumerate(chosen):
            kind = q_type if q_type != "mixed" else ("flag" if idx % 2 == 0 else "capital")
            deck.append({
                "idx": idx,
                "kind": kind,
                "country": item,
                "options": build_choices(item, pool, kind) if a_mode == "choice" else [],
            })

        self.winner = ""
        self.reset_match()
        self.questions = deck
        self.status = self.START_STATUS
        self.rematch.clear()
        self._begin_question(0)

    def _begin_question(self, idx: int) -> None:
        self.q_idx = idx
        self.phase = "question"
        self.answers = {}
        self.wrong_tries = {}
        self.last_try_at = {}
        now = time.time()
        self.started_at = now
        self.deadline = now + float(self.config.get("roundTime", 15))
        self.touched = now

    def _current_question(self) -> dict | None:
        if 0 <= self.q_idx < len(self.questions):
            return self.questions[self.q_idx]
        return None

    def _score_hit(self, mark: str, elapsed: float) -> tuple[int, int]:
        rt = max(1.0, float(self.config.get("roundTime", 15)))
        ratio = max(0.0, min(1.0, (rt - elapsed) / rt))
        base = round(500 + 500 * ratio)
        new_streak = self.streaks.get(mark, 0) + 1
        self.streaks[mark] = new_streak
        self.best_streaks[mark] = max(self.best_streaks.get(mark, 0), new_streak)
        self.correct_counts[mark] = self.correct_counts.get(mark, 0) + 1
        bonus = min(300, (new_streak - 1) * 50)
        pts = base + bonus
        self.points[mark] = self.points.get(mark, 0) + pts
        return pts, new_streak

    def _resolve_question(self) -> None:
        q = self._current_question()
        if q is None or self.phase != "question":
            return
        for m in self._seated_marks():
            if m not in self.answers:
                self.streaks[m] = 0
                self.answers[m] = {
                    "correct": False,
                    "choice": "",
                    "text": "",
                    "points": 0,
                    "ms": None,
                    "skipped": False,
                }

        c = q["country"]
        self.history.append({
            "idx": self.q_idx + 1,
            "kind": q["kind"],
            "code": c["code"],
            "flagUrl": flag_svg_url(c["code"]),
            "nameVi": c["nameVi"],
            "nameEn": c["nameEn"],
            "capitalVi": c["capitalVi"],
            "capitalEn": c["capitalEn"],
            "continent": c["continent"],
            "results": [
                {
                    "mark": m,
                    "name": (self.seat(m).name if self.seat(m) else m),
                    "color": (self.seat(m).color if self.seat(m) else "#64748b"),
                    **self.answers[m],
                    "totalPoints": self.points.get(m, 0),
                }
                for m in self._seated_marks()
            ],
        })
        self.phase = "reveal"
        now = time.time()
        self.deadline = now + REVEAL_SECONDS
        self.touched = now

    def _finish_match(self) -> None:
        self.phase = "finished"
        self.deadline = 0.0
        seated = self._seated_marks()
        if not seated:
            self.status = "waiting"
            self.winner = ""
            return
        self.status = "finished"
        self.rematch.clear()
        best = max(self.points.get(m, 0) for m in seated)
        winners = [m for m in seated if self.points.get(m, 0) == best]
        if len(winners) > 1:
            self.winner = "draw"
            self.scores["draw"] = self.scores.get("draw", 0) + 1
            self.system(f"Hòa nhau với {best} điểm!")
        else:
            win_mark = winners[0]
            self.winner = win_mark
            self.scores[win_mark] = self.scores.get(win_mark, 0) + 1
            win_player = self.seat(win_mark)
            self.system(f"{win_player.name if win_player else win_mark} về nhất với {best} điểm!")
        self.touched = time.time()

    def _advance(self) -> None:
        if self.q_idx + 1 < len(self.questions):
            self._begin_question(self.q_idx + 1)
        else:
            self._finish_match()

    def bot_pending(self, mark: str) -> bool:
        return self.in_progress() and self.phase == "question" and mark not in self.answers

    def progress_token(self) -> tuple:
        return (self.status, self.phase, self.q_idx, len(self.answers), self.winner)

    def handle(self, uid: str, action: str, msg: dict) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn cần ngồi vào ghế để thao tác.")

        if action == "config":
            if self.in_progress():
                raise GameError("Không thể đổi cài đặt khi ván đang diễn ra.")
            self._apply_config(msg)
            return

        if action == "start":
            if self.in_progress():
                raise GameError("Ván đang diễn ra.")
            self._start_match()
            return

        if action == "answer":
            if not self.in_progress() or self.phase != "question":
                return
            mark = player.mark
            if mark in self.answers:
                return
            q = self._current_question()
            if q is None:
                return
            now = time.time()
            elapsed = max(0.0, now - self.started_at)
            a_mode = self.config.get("answerMode", "choice")

            if a_mode == "choice":
                raw_choice = msg.get("choice")
                choice_code = ""
                options = q.get("options") or []
                if isinstance(raw_choice, int) and not isinstance(raw_choice, bool):
                    if 0 <= raw_choice < len(options):
                        choice_code = options[raw_choice]["code"]
                else:
                    s_choice = str(raw_choice if raw_choice is not None else "").strip().lower()
                    if s_choice.isdigit():
                        idx = int(s_choice)
                        if 0 <= idx < len(options):
                            choice_code = options[idx]["code"]
                    else:
                        choice_code = s_choice
                if not choice_code:
                    raise GameError("Chưa chọn đáp án.")
                ok = choice_code == q["country"]["code"]
                if ok:
                    pts, _ = self._score_hit(mark, elapsed)
                else:
                    self.streaks[mark] = 0
                    pts = 0
                self.answers[mark] = {
                    "correct": ok,
                    "choice": choice_code,
                    "text": "",
                    "points": pts,
                    "ms": round(elapsed * 1000),
                    "skipped": False,
                }
            else:
                text = str(msg.get("text", "")).strip()[:80]
                if not text:
                    raise GameError("Hãy nhập câu trả lời.")
                if now - self.last_try_at.get(mark, 0.0) < TYPING_COOLDOWN:
                    raise GameError("Gửi đáp án chậm lại một chút.")
                self.last_try_at[mark] = now
                ok = match_answer(text, q["country"], q["kind"])
                if ok:
                    pts, _ = self._score_hit(mark, elapsed)
                    self.answers[mark] = {
                        "correct": True,
                        "choice": q["country"]["code"],
                        "text": text,
                        "points": pts,
                        "ms": round(elapsed * 1000),
                        "skipped": False,
                    }
                else:
                    tries = self.wrong_tries.setdefault(mark, [])
                    tries.append(text)
                    self.touched = now
                    if len(tries) >= MAX_TYPING_TRIES:
                        self.streaks[mark] = 0
                        self.answers[mark] = {
                            "correct": False,
                            "choice": "",
                            "text": text,
                            "points": 0,
                            "ms": round(elapsed * 1000),
                            "skipped": False,
                        }
                    else:
                        return

            self.touched = now
            if all(m in self.answers for m in self._seated_marks()):
                self._resolve_question()
            return

        if action == "skip":
            if not self.in_progress() or self.phase != "question":
                return
            mark = player.mark
            if mark not in self.answers:
                self.streaks[mark] = 0
                self.answers[mark] = {
                    "correct": False,
                    "choice": "",
                    "text": "",
                    "points": 0,
                    "ms": None,
                    "skipped": True,
                }
                self.touched = time.time()
                if all(m in self.answers for m in self._seated_marks()):
                    self._resolve_question()
            return

        if action == "next":
            if not self.in_progress() or self.phase != "reveal":
                return
            self._advance()
            return

        raise GameError("Hành động không hợp lệ.")

    def tick(self) -> bool:
        if not self.in_progress() or not self.deadline:
            return False
        now = time.time()
        if self.phase == "question" and now >= self.deadline + GRACE_SECONDS:
            self._resolve_question()
            return True
        if self.phase == "reveal" and now >= self.deadline:
            self._advance()
            return True
        return False

    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        mark, player.mark = player.mark, ""
        self.rematch.discard(mark)
        self.system(f"{player.name} rời ghế {self._seat_label(mark)}.")
        if self.in_progress():
            seated = self._seated_marks()
            if not seated:
                self.status = "waiting"
                self.winner = ""
                self.reset_match()
            elif self.phase == "question" and all(m in self.answers for m in seated):
                self._resolve_question()
        elif self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ người đang ngồi mới xin đánh lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        seated = set(self._seated_marks())
        if seated and self.rematch >= seated:
            self._start_match()
        else:
            self.system(f"{player.name} muốn chơi ván mới.")

    def _leaderboard(self) -> list[dict]:
        rows = []
        for m in self._seated_marks():
            p = self.seat(m)
            if p is None:
                continue
            rows.append({
                "mark": m,
                "name": p.name,
                "color": p.color,
                "bot": p.bot,
                "points": self.points.get(m, 0),
                "streak": self.streaks.get(m, 0),
                "bestStreak": self.best_streaks.get(m, 0),
                "correctCount": self.correct_counts.get(m, 0),
                "answered": m in self.answers,
            })
        rows.sort(key=lambda r: (-r["points"], -r["correctCount"]))
        return rows

    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        my_mark = player.mark if player else ""
        q = self._current_question()
        q_payload = None
        if q is not None and self.phase in ("question", "reveal"):
            c = q["country"]
            is_reveal = self.phase == "reveal"
            next_c = (
                self.questions[self.q_idx + 1]["country"]["code"]
                if is_reveal and self.q_idx + 1 < len(self.questions)
                else ""
            )
            safe_options = [
                {
                    "idx": idx,
                    "labelVi": opt["labelVi"],
                    "labelEn": opt["labelEn"],
                    **({"code": opt["code"]} if is_reveal else {}),
                }
                for idx, opt in enumerate(q["options"])
            ]
            q_payload = {
                "index": self.q_idx + 1,
                "total": len(self.questions),
                "kind": q["kind"],
                "flagUrl": flag_svg_url(c["code"]),
                "nextFlagUrl": flag_svg_url(next_c) if next_c else "",
                "preloadFlags": [],
                "promptCountryVi": c["nameVi"] if q["kind"] == "capital" else "",
                "promptCountryEn": c["nameEn"] if q["kind"] == "capital" else "",
                "continent": c["continent"],
                "options": safe_options,
            }

        reveal_payload = self.history[-1] if self.phase == "reveal" and self.history else None
        my_answer = self.answers.get(my_mark) if my_mark else None
        my_wrongs = self.wrong_tries.get(my_mark, []) if my_mark else []

        return {
            "phase": self.phase,
            "config": dict(self.config),
            "now": time.time(),
            "deadline": self.deadline,
            "question": q_payload,
            "reveal": reveal_payload,
            "myAnswer": my_answer,
            "myWrongTries": my_wrongs,
            "answeredCount": len(self.answers),
            "seatedCount": len(self._seated_marks()),
            "leaderboard": self._leaderboard(),
            "history": self.history if self.phase == "finished" else [],
            "countryCount": len(self._pool()),
        }
