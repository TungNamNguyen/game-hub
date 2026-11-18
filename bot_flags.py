"""Bot cho trò Đố Quốc Kỳ & Thủ Đô (cả Trắc nghiệm lẫn Tự gõ kết quả)."""
from __future__ import annotations

import random

from bots import Bot


class FlagsBot(Bot):
    CHANNEL = "flags"

    @property
    def think_delay(self) -> float:
        return {"easy": 2.4, "normal": 1.6, "hard": 1.0}.get(self.level, 1.6)

    def actions(self, room, mark: str):
        if room.phase != "question" or mark in room.answers:
            return []
        q = room._current_question()
        if q is None:
            return []

        rng = random.Random()
        acc = {"easy": 0.45, "normal": 0.72, "hard": 0.92}.get(self.level, 0.72)
        target = q["country"]
        correct = rng.random() < acc

        if room.config.get("answerMode", "choice") == "choice":
            options = q.get("options") or []
            if not options:
                return []
            if correct:
                return [("answer", {"choice": target["code"]})]
            wrongs = [o["code"] for o in options if o["code"] != target["code"]]
            pick = rng.choice(wrongs) if wrongs else target["code"]
            return [("answer", {"choice": pick})]

        # Chế độ tự gõ: đoán đúng thì gửi tên thật, sai thì bấm bỏ qua.
        if correct:
            ans = target["capitalEn"] if q["kind"] == "capital" else target["nameEn"]
            return [("answer", {"text": ans})]
        return [("skip", {})]
