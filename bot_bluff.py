"""Máy chơi Sòng Bịp.

Không có cây tìm kiếm ở đây — game này không phải cờ. Cái khó là ước lượng "lời
khai kia thật hay bịp" rồi cân với rủi ro ổ đạn của chính mình.

MÁY KHÔNG ĐƯỢC NHÌN BÀI NGƯỜI KHÁC. Nó chạy trong cùng tiến trình với luật nên
về kỹ thuật thì chạm được vào ``room.state[seat].hand`` của mọi người, và cũng
chạm được mặt quân trong ``room.pile``. Toàn bộ file này chỉ đọc:

  * tay quân của CHÍNH nó, và những lượt do CHÍNH nó đặt;
  * quân chủ của vòng, và thành phần bộ quân của vòng (``room.deck_count``);
  * vòng này có Ma Vương hay không (``room.devil_rank`` — hiện trên bàn);
  * số quân còn trên tay từng người (công khai trên bàn);
  * ghế nào vừa đặt và đặt MẤY quân (công khai);
  * số ổ đạn từng người đã dùng (công khai — ai cũng đếm được từng phát súng).

Nếu sau này ai sửa file này, đừng đọc ``hand`` hay ``cards`` của ghế khác: máy
sẽ chơi hoàn hảo một cách vô lý và game mất hết ý nghĩa.

Cách ước lượng
--------------
Bản đầu của file này tính sai theo một kiểu rất dễ mắc: nó lấy "họ cần 3 quân
hợp mới khai thật được, mà có 3 quân hợp thì hiếm" rồi kết luận "đặt 3 quân
chắc là bịp". Đo lại thì ngược hẳn — người ta CHỈ đặt 3 khi thật có 3, nên cú
đặt 3 lại là cú thật nhất bàn. Sai ở chỗ bỏ mất điều kiện: phải hỏi "biết rằng
họ đã đặt N quân thì sao", không phải "có N quân hợp thì dễ hay khó".

Bản này làm theo Bayes. Trước hết rải xác suất tay họ có đúng k quân hợp (phân
phối siêu bội trên phần bộ mà máy chưa thấy), rồi cân với một mô hình hành vi:

    k ≥ N  ->  khai thật được. Phần lớn sẽ khai thật: trọng số TRUST.
    k < N  ->  buộc phải bịp, và bịp càng quá tay càng hiếm: trọng số BOLD^(N−k).

    p_bịp = w_bịp / (w_bịp + w_thật)

BOLD nhỏ chính là chỗ nắm được "đặt 3 quân là cú đáng tin": muốn đặt 3 mà chỉ
có 1 quân hợp thì phải gan, và ít ai gan thế.

Quyết định thì tính kỳ vọng, có phân biệt "ai chết":

    điểm_hô = p_bịp × rủi_ro_của_họ − (1 − p_bịp) × rủi_ro_của_mình × SELF_W

Cộng thêm phần "đặt tiếp cũng nguy": hết quân hợp trên tay thì đặt tiếp nghĩa
là phải bịp, nên hô ngay đôi khi lại an toàn hơn.

Hằng số lấy từ đâu
------------------
Không đoán. Mỗi hằng số dưới đây được chọn bằng cách cho các biến thể đấu giao
hữu 400 ván trên BÀN 4 NGƯỜI (2 con mức này + 2 con mức kia, xoay vị trí mỗi
ván, cân bằng là 50%). Hai điều đo được đáng ghi lại:

  * Đấu TAY ĐÔI gần như 50/50 với mọi bộ tham số. Mỗi vòng đúng một người bắn,
    nên may mắn của ổ đạn che lấp hết phần kỹ năng. Đừng dùng tay đôi để đánh
    giá bot — bản đo đầu tiên đã kết luận sai vì lấy tay đôi làm thước.
  * ``SELF_WEIGHT`` tốt nhất là 1.0, tức là coi "mình chết" và "đối thủ chết"
    nặng bằng nhau, trái với trực giác ban đầu (tưởng phải > 1). Lý do: trên
    bàn 4 người, loại được một đối thủ cũng đáng gần bằng việc tự sống, vì nó
    rút ngắn đường tới chức vô địch.

Thang mức khó đo được, mỗi số là trung bình của 5 lần × 400 ván độc lập trên bàn
4 người (cân bằng là 50%):

    hard  vs easy    74.9%   (lệch chuẩn 2.2)
    hard  vs normal  65.0%   (lệch chuẩn 1.7)
    normal vs easy   58.8%   (lệch chuẩn 3.3)
"""

from __future__ import annotations

import math

from bluff import DECK_COUNT, DECK_SIZE, DEMON, DEVIL, MAX_PLAY, is_truth
from bots import Bot

#: Mình chết nặng hơn đối thủ chết bao nhiêu lần. Quét ra 1.0 là tốt nhất.
SELF_WEIGHT = 1.0

#: P(khai thật | khai thật được). Thấp = nghi nhiều = hô bịp nhiều.
TRUST = {"easy": 0.88, "normal": 0.84, "hard": 0.82}

#: Độ gan khi bịp: trọng số của việc đặt quá số quân hợp đang có, mỗi quân
#: vượt thêm nhân thêm một lần. Nhỏ = "đặt 3 quân thì chắc là thật".
BOLD = {"easy": 0.34, "normal": 0.24, "hard": 0.20}

#: Ngưỡng điểm để quyết định hô. Cao = ngại hô.
CALL_GATE = {"easy": 0.06, "normal": 0.02, "hard": 0.0}

#: Nhiễu cộng vào p_bịp, mô phỏng "đọc bài kém". Mức Dễ lệch nhiều nhất.
NOISE = {"easy": 0.26, "normal": 0.08, "hard": 0.0}

#: Mức Dễ còn hô bừa: bấm BỊP mà không cần lý do gì.
WILD_CALL = {"easy": 0.14, "normal": 0.02, "hard": 0.0}

#: Xác suất chơi hớ: trộn một quân sai vào lượt đặt lẽ ra thật được.
BLUNDER = {"easy": 0.30, "normal": 0.05, "hard": 0.0}

#: Xác suất bớt một quân hợp so với mức đặt được, để dành cho lượt sau. Đây là
#: tham số ăn nhiều điểm nhất khi quét: luôn giữ sẵn một quân hợp trong tay
#: nghĩa là luôn còn một lượt khai thật để rút, đỡ phải bịp lúc bí.
HOLD_BACK = {"easy": 0.0, "normal": 0.18, "hard": 0.45}

#: Xác suất bịp TO (2-3 quân) thay vì bịp 1 quân.
#:
#: Tự đấu cho thấy 0.0 là tối ưu (73.8% so với 72.0% ở 0.18). Vẫn để 0.18 cho
#: mức Khó, chấp nhận mất ~1.8 điểm, vì tự đấu KHÔNG đo được thứ quan trọng
#: nhất ở đây: nếu máy chỉ bịp đúng 1 quân thì người chơi ngồi vài ván là đọc
#: được luật "nó đặt 1 quân tức là nó bí" và bàn hết vui. Đây là chỗ cố ý lệch
#: khỏi con số tối ưu, không phải chỗ quên tinh chỉnh.
BOLD_BLUFF = {"easy": 0.10, "normal": 0.20, "hard": 0.18}

# --------------------------------------------------------------------------- #
# chế độ Ma Vương
# --------------------------------------------------------------------------- #
# Ma Vương đổi hẳn bài toán. Đặt nó là nước KHÔNG BAO GIỜ bị phạt: bị hô thì
# người hô cùng cả bàn còn quân phải bắn, mình sạch. Nên với máy có hai việc
# mới: (1) cầm nó thì biết dùng, (2) định hô bịp thì phải nhớ rằng cú một quân
# kia có thể chính là nó.

#: Xác suất đặt Ma Vương DÙ vẫn còn quân hợp để khai thật.
#:
#: Không đặt 1.0: dốc Ma Vương ra ngay lượt đầu thì chẳng ai kịp hô, coi như
#: đốt mất quân mạnh nhất. Giữ nó tới lúc bàn đang căng mới đáng. Còn khi máy
#: hết quân hợp thì nó LUÔN đặt Ma Vương thay vì bịp — chỗ đó không cần xác
#: suất, vì bịp thật luôn tệ hơn.
DEVIL_LEAD = {"easy": 0.12, "normal": 0.30, "hard": 0.45}

#: Máy tính tới rủi ro "quân kia là Ma Vương" ở mức nào. 0 = phớt lờ hoàn toàn.
#: Mức Dễ phớt lờ, và đó chính là một trong những chỗ làm nó yếu.
DEVIL_FEAR = {"easy": 0.0, "normal": 0.7, "hard": 1.0}

#: Mô hình hành vi đối thủ: họ cầm Ma Vương và vừa đặt đúng 1 quân, thì xác
#: suất quân đó là Ma Vương. Không phải 1.0 vì người ta cũng đặt 1 quân thật
#: hoặc bịp 1 quân suốt.
DEVIL_TELL = 0.5

#: Giá của việc ĐỐI THỦ KHÁC cũng phải bắn khi Ma Vương bị lật, so với việc
#: chính mình phải bắn. Dưới 1 vì "mình không chết" vẫn đáng hơn "thêm một
#: người nữa cùng chịu rủi ro".
DEVIL_SPLASH = 0.5


def truth_spread(truths: int, pool: int, hand: int) -> list[float]:
    """q[k] = P(một tay ``hand`` quân rút từ ``pool`` chứa đúng k quân hợp).

    Phân phối siêu bội. ``pool`` là phần bộ mà máy chưa thấy mặt, nên nó bao
    gồm cả quân trên tay người khác, quân họ đã đặt úp, và quân không được chia
    (bàn 2-3 người luôn còn quân treo).
    """
    hand = max(0, min(hand, pool))
    truths = max(0, min(truths, pool))
    total = math.comb(pool, hand) if pool > 0 else 0
    if total == 0:
        return [1.0] + [0.0] * hand
    spread = []
    for got in range(hand + 1):
        rest = hand - got
        if got > truths or rest > pool - truths:
            spread.append(0.0)
        else:
            spread.append(math.comb(truths, got) * math.comb(pool - truths, rest) / total)
    return spread


class BluffBot(Bot):
    CHANNEL = "bluff"

    #: Chậm hơn các game khác một chút, có chủ ý: bàn bịp cần nhịp "đang cân
    #: nhắc", trả lời trong 200ms làm cả bàn giống một cái máy bán nước.
    THINK_DELAY = {"easy": 0.9, "normal": 1.2, "hard": 1.5}
    TIME_BUDGET = {"easy": 0.05, "normal": 0.05, "hard": 0.05}

    @property
    def think_delay(self) -> float:
        base = self.THINK_DELAY.get(self.level, 1.2)
        # Nhịp không đều làm bàn sống hơn, và quan trọng hơn: người chơi không
        # đọc được "nó nghĩ lâu tức là nó đang bí".
        return base * self.rng.uniform(0.75, 1.3)

    # ---- phần đọc bàn (chỉ thông tin công khai + tay của chính mình) -------- #
    @staticmethod
    def _deck_count(room) -> dict[str, int]:
        """Thành phần bộ quân của VÒNG NÀY. Công khai: ai cũng đếm được.

        Ở chế độ Ma Vương, quân chủ chỉ còn 5 con thay vì 6 — bỏ qua chỗ này
        thì mọi ước lượng Bayes bên dưới lệch đúng một quân, và lệch về phía
        "tin người ta có quân hợp" nên máy sẽ hô bịp ít hơn mức đáng.
        """
        return getattr(room, "deck_count", None) or DECK_COUNT

    def _unseen(self, room, mark: str) -> tuple[int, int]:
        """(số quân máy chưa thấy, trong đó bao nhiêu quân hợp).

        "Chưa thấy" = cả bộ 20 trừ tay mình và những quân CHÍNH MÌNH đã đặt.
        Quân người khác đặt vẫn tính là chưa thấy, vì úp thì máy không biết mặt.
        """
        table = room.table_rank
        counts = self._deck_count(room)
        hand = room.state[mark].hand
        own_played = [card for play in room.pile if play.seat == mark
                      for card in play.cards]

        seen = len(hand) + len(own_played)
        seen_truth = sum(1 for card in hand if is_truth(card.rank, table)) \
            + sum(1 for card in own_played if is_truth(card.rank, table))

        pool = max(1, DECK_SIZE - seen)
        # Ma Vương KHÔNG nằm trong số quân hợp: is_truth() trả False cho nó, và
        # counts[table] đã bị trừ đi một con vì nó chiếm chỗ.
        truths = max(0, counts.get(table, 0) + counts.get(DEMON, 0) - seen_truth)
        return pool, min(truths, pool)

    def _devil_odds(self, room, mark: str) -> float:
        """Xác suất lượt vừa rồi CHÍNH LÀ Ma Vương.

        Chỉ đọc thông tin công khai: vòng này có Ma Vương hay không, người kia
        còn mấy quân, họ vừa đặt mấy quân. Cộng với tay của chính máy — nếu Ma
        Vương đang nằm trong tay mình thì rủi ro này bằng 0.
        """
        play = room.last_play
        if play is None or not getattr(room, "devil_rank", ""):
            return 0.0
        # Ma Vương chỉ đặt được một mình, nên lượt 2-3 quân chắc chắn không phải.
        if play.count != 1:
            return 0.0
        if any(card.rank == DEVIL for card in room.state[mark].hand):
            return 0.0
        if any(card.rank == DEVIL for p in room.pile if p.seat == mark
               for card in p.cards):
            return 0.0

        pool, _ = self._unseen(room, mark)
        # Tay họ TRƯỚC khi đặt. Ma Vương là một quân cụ thể trong ``pool`` quân
        # máy chưa thấy, nên P(họ cầm nó) = số quân họ có / pool.
        their_hand = min(len(room.state[play.seat].hand) + play.count, pool)
        holds = their_hand / pool
        return min(1.0, max(0.0, holds * DEVIL_TELL))

    def _lie_odds(self, room, mark: str) -> float:
        """Xác suất lượt vừa rồi là bịp, theo Bayes (xem docstring đầu file)."""
        play = room.last_play
        if play is None:
            return 0.0
        count = play.count
        pool, truths = self._unseen(room, mark)
        # Tay họ TRƯỚC khi đặt = số quân còn lại + số quân vừa đặt.
        their_hand = min(len(room.state[play.seat].hand) + count, pool)
        spread = truth_spread(truths, pool, their_hand)

        trust = TRUST.get(self.level, 0.84)
        bold = BOLD.get(self.level, 0.24)

        # k < N: không đủ quân hợp -> chắc chắn đang bịp, nhưng bịp vượt càng
        # nhiều quân càng hiếm.
        weight_lie = sum(q * bold ** (count - k)
                         for k, q in enumerate(spread) if k < count)
        # k >= N: khai thật được. Phần lớn khai thật, phần nhỏ vẫn chọn bịp để
        # giữ quân hợp cho lượt sau.
        honest_mass = sum(q for k, q in enumerate(spread) if k >= count)
        weight_lie += honest_mass * (1.0 - trust)
        weight_true = honest_mass * trust

        if weight_lie + weight_true <= 0:
            return 0.5
        odds = weight_lie / (weight_lie + weight_true)

        noise = NOISE.get(self.level, 0.0)
        if noise:
            odds += self.rng.uniform(-noise, noise)
        return min(1.0, max(0.0, odds))

    # ---- quyết định -------------------------------------------------------- #
    def _should_call(self, room, mark: str) -> bool:
        play = room.last_play
        if play is None or play.seat == mark:
            return False

        # Mức Dễ hô bừa: đó chính là cái làm nó yếu, chứ không phải "hô ít".
        # Bản trước cho mức Dễ một ngưỡng cao tới mức nó gần như không bao giờ
        # hô — mà "không bao giờ hô" hoá ra là một chiến thuật khá tốt (không
        # bao giờ tự bắn vì hô sai), nên mức Dễ lại thắng mức Khó.
        if self.rng.random() < WILD_CALL.get(self.level, 0.0):
            return True

        table = room.table_rank
        hand = room.state[mark].hand
        own_risk = room.state[mark].death_odds()
        foe_risk = room.state[play.seat].death_odds()
        lie = self._lie_odds(room, mark)

        score = lie * foe_risk - (1.0 - lie) * own_risk * SELF_WEIGHT

        # Nhánh Ma Vương: lật ra nó thì người đặt sạch, MÌNH bắn chắc chắn, và
        # những người còn quân cũng bắn theo. Trộn hai nhánh theo xác suất thay
        # vì cộng một hình phạt phẳng — vì phần "kéo cả bàn xuống" đôi khi bù
        # lại được, nhất là khi ổ đạn của họ đã gần cạn.
        devil = self._devil_odds(room, mark) * DEVIL_FEAR.get(self.level, 0.0)
        if devil > 0:
            splash = sum(room.state[seat].death_odds() for seat in room.alive_seats()
                         if seat not in (mark, play.seat) and room.state[seat].hand)
            devil_score = splash * DEVIL_SPLASH - own_risk * SELF_WEIGHT
            score = (1.0 - devil) * score + devil * devil_score

        # Đặt tiếp cũng có giá: không còn quân hợp nào thì lượt sau buộc phải
        # bịp, và lúc đó chính mình là người dễ bị bắt.
        truths = sum(1 for card in hand if is_truth(card.rank, table))
        if not truths and hand:
            score += 0.30 * own_risk
        elif truths < 1 and not hand:
            score += 0.10

        # Ổ cuối của đối thủ: hô đúng là loại hẳn họ, rất đáng đánh cược.
        if room.state[play.seat].chambers_left() <= 1:
            score += 0.18 * lie
        # Ổ cuối của mình: hô sai là chết chắc, chỉ hô khi gần như cầm chắc. Và
        # ở ổ cuối thì rủi ro Ma Vương dù nhỏ cũng đủ để không hô: lật ra nó là
        # chết, không có "may ra" nào cả.
        if room.state[mark].chambers_left() <= 1 and (lie < 0.93 or devil > 0.02):
            return False

        return score > CALL_GATE.get(self.level, 0.02)

    def _choose_cards(self, room, mark: str) -> list[str]:
        """Chọn quân để đặt. Trả về danh sách id."""
        table = room.table_rank
        hand = list(room.state[mark].hand)
        self.rng.shuffle(hand)
        devil = next((card for card in hand if card.rank == DEVIL), None)
        truths = [card for card in hand if is_truth(card.rank, table)]
        # Ma Vương bị loại khỏi ``lies`` có chủ ý: nó không ghép được với quân
        # nào, nên mọi nhánh bên dưới phải không bao giờ nhặt được nó. Để nó lẫn
        # vào đây là cách chắc chắn nhất để máy sinh ra nước đi bị server từ chối.
        lies = [card for card in hand
                if not is_truth(card.rank, table) and card.rank != DEVIL]

        # Giữ Quỷ lại khi còn quân hợp thường: Quỷ dùng ở vòng nào cũng thật,
        # nên nó là quân cứu mạng ở lượt bí sau này.
        truths.sort(key=lambda card: 1 if card.rank == DEMON else 0)

        # Ma Vương: hễ lẽ ra phải BỊP thì đặt nó, không bao giờ tệ hơn. Bịp bị
        # bắt là mình bắn; Ma Vương bị bắt là người hô bắn. Còn khi vẫn khai
        # thật được thì chỉ thỉnh thoảng dùng, để dành cho lúc bàn căng.
        if devil is not None and (not truths
                                 or self.rng.random() < DEVIL_LEAD.get(self.level, 0.0)):
            return [devil.id]

        if truths:
            take = min(len(truths), MAX_PLAY)
            if self.level == "easy":
                # Dễ hay đặt ít hơn mức nên đặt, nên tay cứ dày mãi rồi cuối
                # vòng không còn quân hợp nào để khai thật.
                take = min(take, self.rng.choice([1, 1, 2, take]))
            elif take > 1 and self.rng.random() < HOLD_BACK.get(self.level, 0.0):
                # Giữ lại một quân hợp cho lượt sau. Đây cũng là cách để SỐ QUÂN
                # đặt không thành mật hiệu — xem BOLD_BLUFF bên dưới.
                take -= 1
            chosen = truths[:take]
            if lies and len(chosen) < MAX_PLAY \
                    and self.rng.random() < BLUNDER.get(self.level, 0.0):
                # Chơi hớ: nhét thêm một quân sai vào lượt lẽ ra hoàn toàn thật.
                chosen = chosen + [lies[0]]
            return [card.id for card in chosen]

        # Không còn quân hợp: buộc phải bịp. Đặt 1 quân là lời khai dễ tin nhất.
        #
        # Nhưng KHÔNG được lúc nào bịp cũng đặt đúng 1 quân: làm vậy thì số quân
        # đặt tố giác chính mình ("nó đặt 1 tức là nó bí"), và một đối thủ biết
        # đếm sẽ hô đúng gần như mọi lần. BOLD_BLUFF là phần bịp to cố ý để phá
        # cái mật hiệu đó.
        if not lies:
            # Chỉ còn đúng Ma Vương trong tay. Nhánh trên đã bắt trường hợp này
            # (không có quân hợp -> đặt Ma Vương), đây là lưới an toàn.
            return [devil.id] if devil is not None else []

        count = 1
        # Đếm theo ``lies`` chứ không theo ``hand``: bàn không có Ma Vương thì
        # hai cái bằng nhau, còn khi có thì đếm theo tay sẽ đòi đặt nhiều quân
        # hơn số quân thật sự đặt được.
        if len(lies) <= 2 and self.level != "easy":
            # Dồn hết: hết quân là được bỏ lượt tới hết vòng, tức là an toàn
            # tuyệt đối cho phần còn lại của vòng.
            count = len(lies)
        elif self.rng.random() < BOLD_BLUFF.get(self.level, 0.0):
            count = 2 if self.rng.random() < 0.75 else 3
        elif self.level == "easy" and self.rng.random() < 0.3:
            count = min(len(lies), self.rng.choice([2, 3]))
        return [card.id for card in lies[:max(1, min(count, MAX_PLAY, len(lies)))]]

    # ---- giao diện với hub ------------------------------------------------- #
    def actions(self, room, mark: str) -> list[tuple[str, dict]]:
        state = room.state.get(mark)
        if state is None or not state.alive:
            return []

        # Bị buộc hô bịp (chỉ còn mình có quân): không có lựa chọn nào khác.
        if room.forced_liar and room.turn == mark:
            return [("liar", {})]

        try:
            if self._should_call(room, mark):
                return [("liar", {})]
            cards = self._choose_cards(room, mark)
        except Exception:
            # Không bao giờ để lỗi tính toán làm treo phòng: đặt bừa 1 quân.
            cards = []

        if not cards:
            if not state.hand:
                return []
            cards = [self.rng.choice(state.hand).id]
        return [("play", {"cards": cards})]
