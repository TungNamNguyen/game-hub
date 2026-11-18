"""Test luật bàn Xì Tố (poker.py). Chạy: python -m pytest test_poker.py -q"""

from __future__ import annotations

import random

import pytest

from games import GameError
from poker import BIG_BLIND, CHIP_START, SMALL_BLIND, Card, PokerRoom


# --------------------------------------------------------------------------- #
# tiện ích
# --------------------------------------------------------------------------- #
def make_room(n=2, mode=None, seed=1):
    mode = mode or {2: "p2", 3: "p4", 4: "p4", 5: "p6", 6: "p6"}[n]
    room = PokerRoom("TEST", mode)
    room.rng = random.Random(seed)
    for i in range(n):
        room.join(f"u{i}", f"P{i}", "#111111")
    start(room)
    return room


def start(room):
    """Bỏ qua khoảng chờ đầu bàn, đúng như tick_loop của hub sẽ làm."""
    if room.phase == "starting":
        room.start_at = 0.0
        room.tick()


def uid_at(room, seat):
    return room.seat(seat).uid


def actor_uid(room):
    return uid_at(room, room.actor)


def total_chips(room):
    return sum(room.state[s].chips for s in room.SEATS) + room.pot_total()


def finish_hand(room):
    """Đẩy đồng hồ tới khi ván hiện tại kết thúc (showdown)."""
    for _ in range(20):
        if room.phase == "showdown":
            return
        room.deadline = 0.0
        room.tick()


# --------------------------------------------------------------------------- #
# lỗi người dùng báo: không thấy bài của mình, không có nút tố
# --------------------------------------------------------------------------- #
def test_view_contains_my_hole_cards_and_seat():
    room = make_room(2)
    for uid in ("u0", "u1"):
        view = room.view(uid)
        assert view["you"]["mark"] == room.players[uid].mark   # khung chung KHÔNG bị ghi đè
        assert view["me"]["seat"] == room.players[uid].mark
        assert len(view["me"]["hole"]) == 2
        assert view["me"]["handLabel"]


def test_view_hides_other_players_cards():
    room = make_room(3)
    view = room.view("u0")
    assert view["shown"] == {}
    mine = {(c["v"], c["s"]) for c in view["me"]["hole"]}
    for seat in room.SEATS:
        if seat != room.players["u0"].mark and room.state[seat].dealt:
            theirs = {c.as_tuple() for c in room.state[seat].hole}
            assert not (theirs & mine)
    spectator = room.view("nobody")
    assert spectator["me"]["seat"] == ""
    assert "hole" not in spectator["me"]


def test_actor_gets_raise_options():
    room = make_room(3)
    view = room.view(actor_uid(room))
    act = view["act"]
    assert act is not None
    assert act["canRaise"] is True
    assert act["toCall"] == BIG_BLIND
    assert act["minTo"] == 2 * BIG_BLIND
    assert act["maxTo"] == CHIP_START
    # Người không tới lượt thì không có bảng hành động.
    other = next(u for u in ("u0", "u1", "u2") if u != actor_uid(room))
    assert room.view(other)["act"] is None


# --------------------------------------------------------------------------- #
# vị trí & mù
# --------------------------------------------------------------------------- #
def test_heads_up_button_is_small_blind_and_acts_first_preflop():
    room = make_room(2)
    assert room.sb_seat == room.button
    assert room.actor == room.button
    assert room.state[room.sb_seat].bet == SMALL_BLIND
    assert room.state[room.bb_seat].bet == BIG_BLIND
    # Theo + qua -> flop, mù lớn (không phải nút) đi trước.
    room.call(actor_uid(room))
    room.check(actor_uid(room))
    assert room.street == "flop"
    assert len(room.board) == 3
    assert room.actor == room.bb_seat


def test_three_handed_utg_acts_first_and_bb_gets_option():
    room = make_room(3)
    assert room.actor not in (room.sb_seat, room.bb_seat)
    room.call(actor_uid(room))      # UTG theo
    room.call(actor_uid(room))      # SB bù thành 1 mù lớn
    assert room.actor == room.bb_seat   # quyền chọn của mù lớn
    room.check(actor_uid(room))
    assert room.street == "flop"


def test_button_moves_each_hand():
    room = make_room(3)
    first = room.button
    room.fold(actor_uid(room))
    room.fold(actor_uid(room))
    assert room.phase == "showdown"
    room.deadline = 0.0
    room.tick()
    assert room.hand_no == 2
    assert room.button != first


# --------------------------------------------------------------------------- #
# luật cược
# --------------------------------------------------------------------------- #
def test_min_raise_is_last_raise_size():
    room = make_room(3)
    room.raise_to(actor_uid(room), 3000)        # tố thêm 2.000
    with pytest.raises(GameError):
        room.raise_to(actor_uid(room), 4000)    # cần tối thiểu 5.000
    room.raise_to(actor_uid(room), 5000)
    assert room.current_bet == 5000


def test_check_not_allowed_when_facing_bet():
    room = make_room(2)
    with pytest.raises(GameError):
        room.check(actor_uid(room))


def test_cannot_act_out_of_turn():
    room = make_room(3)
    wrong = next(u for u in ("u0", "u1", "u2") if u != actor_uid(room))
    with pytest.raises(GameError):
        room.fold(wrong)


def test_short_all_in_does_not_reopen_raising():
    room = make_room(3)
    utg, sb, bb = room.actor, room.sb_seat, room.bb_seat
    room.raise_to(uid_at(room, utg), 3000)          # UTG tố lên 3.000
    room.state[sb].chips = 3500 - room.state[sb].bet  # SB chỉ còn đủ lên 3.500
    room.all_in(uid_at(room, sb))                   # all-in thiếu (+500 < 2.000)
    assert room.current_bet == 3500
    room.call(uid_at(room, bb))                     # BB theo
    assert room.actor == utg
    act = room.view(uid_at(room, utg))["act"]
    assert act["canRaise"] is False                 # UTG chỉ được theo/bỏ
    assert act["toCall"] == 500
    with pytest.raises(GameError):
        room.raise_to(uid_at(room, utg), 10_000)
    room.call(uid_at(room, utg))
    assert room.street == "flop"


def test_full_raise_reopens_action():
    room = make_room(3)
    utg = room.actor
    room.raise_to(actor_uid(room), 3000)
    room.raise_to(actor_uid(room), 9000)            # SB tố lại đầy đủ
    room.call(actor_uid(room))                      # BB theo
    assert room.actor == utg
    assert room.view(uid_at(room, utg))["act"]["canRaise"] is True


def test_fold_win_returns_uncalled_and_conserves_chips():
    room = make_room(2)
    before = total_chips(room)
    room.raise_to(actor_uid(room), 10_000)
    room.fold(actor_uid(room))
    assert room.phase == "showdown"
    assert room.result["showdown"] is False
    winner = room.result["winners"][0]
    assert room.state[winner].chips == CHIP_START + BIG_BLIND
    assert total_chips(room) == before


def test_all_in_runs_out_board_and_shows_cards():
    room = make_room(2)
    room.all_in(actor_uid(room))
    room.call(actor_uid(room))
    assert room.phase == "ritvote"              # hỏi chia 2 lần trước
    assert set(room.view("u0")["shown"]) == set(room._live())
    finish_hand(room)
    assert len(room.board) == 5
    assert room.result["showdown"] is True
    assert sum(room.state[s].chips for s in room.SEATS) == 2 * CHIP_START


# --------------------------------------------------------------------------- #
# chia 2 lần
# --------------------------------------------------------------------------- #
def C(spec):
    """'AS' -> Card(14, 'S'); '10H' -> Card(10, 'H')."""
    rank, suit = spec[:-1], spec[-1]
    value = {"J": 11, "Q": 12, "K": 13, "A": 14}.get(rank) or int(rank)
    return Card(value, suit)


def rigged_heads_up(run1, run2):
    """Tay đôi, cả hai tất tay preflop. Ghế nút cầm AA, ghế kia KK.

    ``run1``/``run2`` là 5 lá bàn chung của từng lần chia. Bộ bài được xếp đúng
    thứ tự rút (pop từ cuối), có lá đốt trước mỗi vòng như sòng thật."""
    room = make_room(2)
    aa, kk = room.button, room.bb_seat
    room.state[aa].hole = [C("AS"), C("AH")]
    room.state[kk].hole = [C("KS"), C("KH")]
    burns = iter([C("6C"), C("6D"), C("6H"), C("6S"), C("4D"), C("4H")])

    def street_order(board):
        return [next(burns), *board[:3], next(burns), board[3], next(burns), board[4]]

    pops = street_order([C(x) for x in run1]) + street_order([C(x) for x in run2])
    room.deck = list(reversed(pops))
    room.all_in(actor_uid(room))
    room.call(actor_uid(room))
    assert room.phase == "ritvote"
    return room, aa, kk


RUN_AA = ["2C", "7D", "9S", "JC", "3D"]          # AA thắng (đôi A > đôi K)
RUN_KK = ["KD", "4C", "8S", "10C", "5H"]         # KK thắng (sám cô K)


def test_run_it_twice_split_when_each_wins_one():
    room, aa, kk = rigged_heads_up(RUN_AA, RUN_KK)
    room.vote_rit(uid_at(room, aa), True)
    assert room.phase == "ritvote"              # còn chờ người kia
    room.vote_rit(uid_at(room, kk), True)
    assert room.phase == "runout" and room.rit
    finish_hand(room)
    assert [c.as_tuple() for c in room.board1] == [C(x).as_tuple() for x in RUN_AA]
    assert [c.as_tuple() for c in room.board] == [C(x).as_tuple() for x in RUN_KK]
    assert room.result["rit"] is True
    assert room.result["payouts"] == {aa: CHIP_START, kk: CHIP_START}
    assert room.state[aa].chips == room.state[kk].chips == CHIP_START


def test_run_it_twice_one_player_wins_both():
    room, aa, kk = rigged_heads_up(RUN_AA, ["2D", "7C", "9H", "JD", "3S"])
    room.vote_rit(uid_at(room, aa), True)
    room.vote_rit(uid_at(room, kk), True)
    finish_hand(room)
    assert room.result["payouts"] == {aa: 2 * CHIP_START}
    assert room.state[kk].chips == 0


def test_one_no_vote_means_run_once():
    room, aa, kk = rigged_heads_up(RUN_AA, RUN_KK)
    room.vote_rit(uid_at(room, aa), True)
    room.vote_rit(uid_at(room, kk), False)
    assert room.phase == "runout" and not room.rit
    finish_hand(room)
    assert room.board1 == []
    assert room.result["payouts"] == {aa: 2 * CHIP_START}   # chỉ bàn 1 (AA thắng)


def test_vote_timeout_means_run_once():
    room, aa, kk = rigged_heads_up(RUN_AA, RUN_KK)
    room.vote_rit(uid_at(room, aa), True)
    room.deadline = 0.0
    room.tick()                                  # người kia không bấm
    assert room.phase == "runout" and not room.rit


def test_run_it_twice_from_flop_only_reruns_missing_cards():
    room = make_room(2)
    room.call(actor_uid(room))
    room.check(actor_uid(room))
    assert room.street == "flop"
    flop = [c.as_tuple() for c in room.board]
    room.all_in(actor_uid(room))
    room.call(actor_uid(room))
    for seat in room._live():
        room.vote_rit(uid_at(room, seat), True)
    finish_hand(room)
    assert [c.as_tuple() for c in room.board1[:3]] == flop
    assert [c.as_tuple() for c in room.board[:3]] == flop
    extra1 = {c.as_tuple() for c in room.board1[3:]}
    extra2 = {c.as_tuple() for c in room.board[3:]}
    assert len(extra1) == len(extra2) == 2 and not (extra1 & extra2)
    assert sum(room.state[s].chips for s in room.SEATS) == 2 * CHIP_START


def test_spectator_cannot_vote():
    room, aa, kk = rigged_heads_up(RUN_AA, RUN_KK)
    room.join("watch", "W", "#1")
    with pytest.raises(GameError):
        room.vote_rit("watch", True)


# --------------------------------------------------------------------------- #
# khoe bài khi hết ván
# --------------------------------------------------------------------------- #
def test_folded_player_can_show_cards_after_hand():
    room = make_room(3)
    folder = room.actor
    room.fold(uid_at(room, folder))
    with pytest.raises(GameError):
        room.show_cards(uid_at(room, folder))   # chưa hết ván
    room.fold(actor_uid(room))
    assert room.phase == "showdown"
    assert room.view(uid_at(room, folder))["me"]["canShow"] is True
    room.show_cards(uid_at(room, folder))
    assert folder in room.view("u0")["shown"]
    assert room.view(uid_at(room, folder))["me"]["canShow"] is False


def test_side_pots_with_fixed_cards():
    room = make_room(3)
    seats = list(room.SEATS[:3])
    # Ép bài: S-đầu cầm AA (mạnh nhất) nhưng chip ít nhất.
    a, b, c = seats
    room.state[a].hole = [Card(14, "S"), Card(14, "H")]
    room.state[b].hole = [Card(13, "S"), Card(13, "H")]
    room.state[c].hole = [Card(2, "D"), Card(7, "C")]
    room.deck = [card for card in room.deck if card.as_tuple() not in
                 {(14, "S"), (14, "H"), (13, "S"), (13, "H"), (2, "D"), (7, "C")}]
    # Bàn chung không giúp ai: lá rời.
    room.deck += [Card(4, "C"), Card(9, "D"), Card(5, "S"), Card(8, "H"),
                  Card(11, "C"), Card(3, "H"), Card(12, "D"), Card(6, "C")]
    room.state[a].chips = 5000 - room.state[a].bet
    room.state[b].chips = 20_000 - room.state[b].bet
    while room.phase == "betting":
        uid = actor_uid(room)
        st = room.state[room.actor]
        if room.view(uid)["act"]["canRaise"]:
            room.all_in(uid)
        else:
            room.call(uid) if st.bet < room.current_bet else room.check(uid)
    before = total_chips(room)
    finish_hand(room)
    res = room.result
    assert res["showdown"]
    main = res["pots"][0]
    assert main["winners"] == [a]               # AA ăn pot chính
    assert main["amount"] == 15_000
    assert res["pots"][1]["winners"] == [b]     # KK ăn pot phụ
    assert sum(room.state[s].chips for s in room.SEATS) == before


# --------------------------------------------------------------------------- #
# ghế, hàng chờ, chip
# --------------------------------------------------------------------------- #
def test_join_mid_hand_waits_for_next_hand():
    room = make_room(2, mode="p6")
    room.join("late", "Late", "#333")
    seat = room.players["late"].mark
    assert seat
    assert not room.state[seat].dealt
    assert room.view("late")["me"]["hole"] == []
    room.fold(actor_uid(room))
    room.deadline = 0.0
    room.tick()                                 # ván 2
    assert room.state[seat].dealt
    assert len(room.view("late")["me"]["hole"]) == 2


def test_queue_when_table_full_and_promote_after_hand():
    room = make_room(2)
    room.join("w", "Waiter", "#333")
    assert room.players["w"].mark == ""
    target = room.players["u1"].mark
    room.request_seat("w", target)
    assert room.view("w")["me"]["queuedFor"] == [target]
    room.stand("u1")                            # đứng dậy giữa ván
    assert room.players["u1"].mark == target    # ghế giữ tới hết ván
    assert room.phase == "showdown"             # bỏ bài -> người kia thắng
    room.deadline = 0.0
    room.tick()
    assert room.players["w"].mark == target
    assert room.players["u1"].mark == ""


def test_stand_mid_hand_keeps_chips_in_pot():
    room = make_room(3)
    before = total_chips(room)
    room.raise_to(actor_uid(room), 5000)
    room.stand(uid_at(room, room.bb_seat))      # mù lớn rời bàn giữa ván
    while room.phase == "betting":
        uid = actor_uid(room)
        st = room.state[room.actor]
        room.call(uid) if st.bet < room.current_bet else room.check(uid)
    finish_hand(room)
    banked = sum(room.bank.values())
    assert sum(room.state[s].chips for s in room.SEATS) + banked == before


def test_chips_kept_when_standing_and_sitting_again():
    room = make_room(2, mode="p6")
    seat = room.players["u0"].mark
    room.fold(uid_at(room, room.actor))
    chips = room.state[seat].chips
    room.deadline = 0.0
    room.stand("u0")                            # chưa phải giữa ván của u0? vẫn an toàn
    room.tick()
    room.sit("u0")
    assert room.state[room.players["u0"].mark].chips == chips


def test_rebuy_only_when_broke():
    room = make_room(2)
    with pytest.raises(GameError):
        room.rebuy("u0")
    room.all_in(actor_uid(room))
    room.call(actor_uid(room))
    finish_hand(room)
    loser = next((s for s in room.SEATS[:2] if room.state[s].chips == 0), None)
    if loser is None:                           # hòa, không ai hết chip
        return
    room.rebuy(uid_at(room, loser))
    assert room.state[loser].chips == CHIP_START


def test_timeout_auto_folds_then_sits_out():
    room = make_room(2)
    seat = room.actor
    room.deadline = 0.0
    room.tick()
    assert room.state[seat].folded
    assert room.state[seat].timeouts == 1


def test_taunt_goes_to_chat():
    room = make_room(2)
    room.taunt("u0", 0)
    assert room.chat[-1]["kind"] == "taunt"
    with pytest.raises(GameError):
        room.taunt("u0", 999)


def test_needs_two_ready_players_to_start():
    room = PokerRoom("T", "p6")
    room.join("a", "A", "#1")
    assert room.phase == "idle"
    room.view("a")                              # không được crash trước ván đầu
    room.join("b", "B", "#2")
    assert room.phase == "starting"
    room.view("a")
    start(room)
    assert room.status == "playing"


def test_leaderboard_callback_is_zero_sum():
    room = make_room(3)
    seen = []
    room.on_hand_end = seen.append
    room.raise_to(actor_uid(room), 4000)
    room.fold(actor_uid(room))
    room.fold(actor_uid(room))
    assert seen and sum(seen[0].values()) == 0


# --------------------------------------------------------------------------- #
# giải đấu loại trực tiếp
# --------------------------------------------------------------------------- #
def make_tourney(n=3, mode="t6", seed=3, auto_start=True):
    """Phòng giải đấu đã đăng ký ``n`` người. ``auto_start`` thì chủ phòng bấm
    Bắt đầu và ván đầu đã chia xong."""
    room = PokerRoom("TOUR", mode)
    room.rng = random.Random(seed)
    for i in range(n):
        room.join(f"u{i}", f"P{i}", "#111111")
    if auto_start and room.tstage == "lobby":
        room.start_tournament(room.host_uid)
    start(room)
    return room


def alive_uids(room):
    return [room.seat(s).uid for s in room._alive_seats()]


def bust_seat(room, seat):
    """Rút sạch chip của một ghế bằng cách chuyển sang ghế khác, rồi chốt loại
    ở ván kế tiếp — mô phỏng người thua hết chip mà không cần dàn bài."""
    other = next(s for s in room._alive_seats() if s != seat)
    room.state[other].chips += room.state[seat].chips
    room.state[seat].chips = 0


def test_tournament_waits_for_host_and_equal_stacks():
    room = make_tourney(3, auto_start=False)
    assert room.tournament and room.tstage == "lobby"
    assert room.phase == "idle" and room.status == "waiting"       # KHÔNG tự chia
    assert room.host_uid == "u0"
    seats = [room.players[f"u{i}"].mark for i in range(3)]
    assert all(room.state[s].chips == CHIP_START for s in seats)   # chip bằng nhau
    with pytest.raises(GameError):
        room.start_tournament("u1")                                # không phải chủ phòng
    room.start_tournament("u0")
    assert room.tstage == "running" and room.phase == "starting"
    start(room)
    assert room.status == "playing" and room.hand_no == 1


def test_tournament_needs_two_and_autostarts_when_table_is_full():
    room = PokerRoom("T1", "t4")
    room.join("u0", "P0", "#1")
    with pytest.raises(GameError):
        room.start_tournament("u0")                 # một mình thì chưa bắt đầu được
    for i in range(1, 4):
        room.join(f"u{i}", f"P{i}", "#1")
    assert room.tstage == "running"                 # kín 4 ghế: tự khởi tranh
    assert room.phase == "starting"


def test_joining_after_start_is_spectator_only():
    room = make_tourney(3)
    room.join("late", "Muộn", "#1")
    assert room.players["late"].mark == ""
    assert room.view("late")["tournament"]["locked"] is True
    with pytest.raises(GameError):
        room.sit("late")
    with pytest.raises(GameError):
        room.request_seat("late", room.SEATS[-1])   # ghế trống vẫn không được ngồi
    assert room.free_marks() == []
    assert room.summary()["openSeats"] == 0


def test_leaving_mid_tournament_eliminates_and_locks_out():
    room = make_tourney(3)
    quitter = next(u for u in ("u0", "u1", "u2") if u != actor_uid(room))
    seat = room.players[quitter].mark
    room.stand(quitter)
    assert room.state[seat].eliminated is True
    assert room.state[seat].place == 3               # rụng đầu = hạng cuối
    assert quitter in room.out_uids
    assert room.placements[0]["reason"] == "tự rời giải"
    # Vào lại chỉ được xem, không có đường nào ngồi lại.
    room.disconnect(quitter)
    room.join(quitter, "P?", "#1")
    with pytest.raises(GameError):
        room.sit(quitter)
    assert room.view(quitter)["me"]["eliminated"] is True


def test_quitting_while_all_in_keeps_the_pot_claim():
    room = make_tourney(2, mode="t4")
    seat = room.actor
    room.all_in(actor_uid(room))
    room.call(actor_uid(room))                       # cả hai tất tay
    room.stand(uid_at(room, seat))                   # rời giải giữa lúc tất tay
    assert room.state[seat].eliminated is False      # chưa chốt, còn tranh pot
    assert room.state[seat].quitting is True
    for _ in range(40):
        if room.tstage == "done":
            break
        room.deadline = 0.0
        room.tick()
    assert room.tstage == "done"
    assert room.state[seat].eliminated is True


def test_no_rebuy_no_sitout_no_queue_in_tournament():
    room = make_tourney(3)
    uid = "u0"
    with pytest.raises(GameError):
        room.rebuy(uid)
    with pytest.raises(GameError):
        room.toggle_sitout(uid)
    room.join("fan", "Fan", "#1")
    with pytest.raises(GameError):
        room.request_seat("fan", room.players[uid].mark)
    assert all(not q for q in room.queue.values())


def test_busting_eliminates_and_last_standing_wins():
    room = make_tourney(3)
    loser = room._alive_seats()[0]
    bust_seat(room, loser)
    finish_hand(room)
    room.deadline = 0.0
    room.tick()                                      # ván mới -> chốt loại
    assert room.state[loser].eliminated is True
    assert room.state[loser].place == 3
    assert len(room._alive_seats()) == 2

    second = room._alive_seats()[0]
    bust_seat(room, second)
    for _ in range(40):
        if room.tstage == "done":
            break
        room.deadline = 0.0
        room.tick()
    assert room.tstage == "done"
    assert room.state[second].place == 2
    champion = room.winner
    assert champion and room.state[champion].place == 1
    assert room.status == "finished"
    assert [row["place"] for row in room.placements] == [1, 2, 3]
    assert room.view(uid_at(room, champion))["tournament"]["champion"] == champion


def test_tournament_does_not_deal_after_it_is_over():
    room = make_tourney(2, mode="t4")
    bust_seat(room, room._alive_seats()[0])
    for _ in range(40):
        if room.tstage == "done":
            break
        room.deadline = 0.0
        room.tick()
    hand_no = room.hand_no
    for _ in range(5):
        room.deadline = 0.0
        assert room.tick() is False
    assert room.hand_no == hand_no and room.status == "finished"


def test_disconnect_has_a_grace_period_then_eliminates():
    room = make_tourney(3)
    victim = next(u for u in ("u0", "u1", "u2") if u != actor_uid(room))
    seat = room.players[victim].mark
    room.disconnect(victim)
    assert seat in room.out_deadline
    assert room.state[seat].eliminated is False          # chưa loại ngay
    room.join(victim, "P?", "#1")                        # quay lại kịp
    assert seat not in room.out_deadline
    assert room.players[victim].mark == seat

    room.disconnect(victim)
    room.out_deadline[seat] = 0.0                        # hết hạn quay lại
    finish_hand(room)
    room.deadline = 0.0
    room.tick()
    assert room.state[seat].eliminated is True
    assert room.placements[0]["reason"] == "mất kết nối"


def test_tournament_pauses_instead_of_ending_when_everyone_drops():
    """Hai người còn lại mà một người rớt mạng: bàn CHỜ, không vội phong vô địch."""
    room = make_tourney(2, mode="t4")
    victim = uid_at(room, room._alive_seats()[1])
    seat = room.players[victim].mark
    room.disconnect(victim)
    finish_hand(room)
    room.deadline = 0.0
    room.tick()
    assert room.tstage == "running"
    assert room.status == "waiting" and room.phase == "idle"
    # Hết hạn quay lại thì tick tự chốt loại và phong vô địch.
    room.out_deadline[seat] = 0.0
    assert room.tick() is True
    assert room.tstage == "done" and room.winner != seat


def test_blinds_go_up_by_level():
    from poker import TOURNEY_BLINDS, TOURNEY_LEVEL_HANDS

    room = make_tourney(3)
    assert (room.sb, room.bb) == TOURNEY_BLINDS[0]
    room.hand_no = TOURNEY_LEVEL_HANDS + 1
    room._apply_level()
    assert (room.sb, room.bb) == TOURNEY_BLINDS[1]
    assert room.view("u0")["blinds"] == {"sb": room.sb, "bb": room.bb}
    room.hand_no = 10_000
    room._apply_level()
    assert (room.sb, room.bb) == TOURNEY_BLINDS[-1]     # mức cuối giữ nguyên


def test_cash_table_is_untouched_by_tournament_code():
    room = make_room(3)
    assert room.tournament is False
    assert room.view("u0")["tournament"] is None
    assert (room.sb, room.bb) == (SMALL_BLIND, BIG_BLIND)
    with pytest.raises(GameError):
        room.start_tournament("u0")
    # Hết chip ở bàn tiền lẻ thì vẫn mua lại được, không bị loại.
    seat = room.players["u0"].mark
    finish_hand(room)
    room.state[seat].chips = 0
    room.rebuy("u0")
    assert room.state[seat].chips == CHIP_START
    assert room.state[seat].eliminated is False


def test_host_moves_on_and_new_tournament_can_be_opened():
    room = make_tourney(3, auto_start=False)
    assert room.host_uid == "u0"
    room.stand("u0")                                    # chủ phòng rút tên
    assert room.host_uid in ("u1", "u2")
    host = room.host_uid
    room.start_tournament(host)
    start(room)
    bust_seat(room, room._alive_seats()[0])
    for _ in range(60):
        if room.tstage == "done":
            break
        room.deadline = 0.0
        room.tick()
    assert room.tstage == "done"
    room.start_tournament(room.host_uid)                # "Giải mới"
    assert room.tstage == "lobby"
    assert room.placements == [] and room.out_uids == set()
    assert room.hand_no == 0 and room.winner == ""
    for seat in room._alive_seats():
        assert room.state[seat].chips == CHIP_START
        assert room.state[seat].eliminated is False


def test_tournament_chips_stay_in_play_until_someone_quits():
    room = make_tourney(4, mode="t6", seed=9)
    rng = random.Random(11)
    total = 4 * CHIP_START
    for _ in range(1500):
        if room.tstage != "running":
            break
        if room.phase == "betting":
            uid = actor_uid(room)
            act = room.view(uid)["act"]
            roll = rng.random()
            if roll < 0.12:
                room.fold(uid)
            elif roll < 0.25 and act["canRaise"]:
                room.raise_to(uid, rng.randint(act["minTo"], act["maxTo"]))
            elif roll < 0.30:
                room.all_in(uid)
            elif act["canCheck"]:
                room.check(uid)
            else:
                room.call(uid)
        elif room.phase == "ritvote":
            for seat, vote in list(room.rit_votes.items()):
                if vote is None and room.phase == "ritvote":
                    room.vote_rit(uid_at(room, seat), rng.random() < 0.5)
        else:
            room.deadline = 0.0
            room.tick()
        chips = sum(room.state[s].chips for s in room.SEATS) + room.pot_total()
        assert chips == total, f"lệch chip ở ván {room.hand_no}, pha {room.phase}"
    # Giải PHẢI kết thúc: mù tăng dần nên không thể đánh mãi.
    assert room.tstage == "done"
    assert len(room.placements) == 4
    assert [row["place"] for row in room.placements] == [1, 2, 3, 4]
    assert room.state[room.winner].chips == total


# --------------------------------------------------------------------------- #
# fuzz: hàng trăm ván ngẫu nhiên, chip luôn bảo toàn và luật không kẹt
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("players", [2, 3, 6])
def test_random_play_conserves_chips(players):
    rng = random.Random(players * 7)
    room = make_room(players, seed=players)
    total = players * CHIP_START
    for _ in range(3000):
        if room.status != "playing":
            break
        if room.phase == "betting":
            uid = actor_uid(room)
            act = room.view(uid)["act"]
            roll = rng.random()
            if roll < 0.15:
                room.fold(uid)
            elif roll < 0.30 and act["canRaise"]:
                room.raise_to(uid, rng.randint(act["minTo"], act["maxTo"]))
            elif roll < 0.34:
                room.all_in(uid)
            elif act["canCheck"]:
                room.check(uid)
            else:
                room.call(uid)
        elif room.phase == "ritvote":
            for seat, vote in list(room.rit_votes.items()):
                if vote is None and room.phase == "ritvote":
                    room.vote_rit(uid_at(room, seat), rng.random() < 0.8)
        else:
            if room.phase == "showdown":
                # Người hết chip mua lại để bàn chạy được lâu.
                for seat in room.SEATS:
                    player = room.seat(seat)
                    if player and room.state[seat].chips == 0:
                        room.rebuy(player.uid)
                        total += CHIP_START
            room.deadline = 0.0
            room.tick()
        chips = sum(room.state[s].chips for s in room.SEATS) + room.pot_total()
        assert chips == total, f"lệch chip ở ván {room.hand_no}, pha {room.phase}"
        for seat in room.SEATS:
            assert room.state[seat].chips >= 0
    assert room.hand_no > 20
