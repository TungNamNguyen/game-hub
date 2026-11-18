"""Test logic chấm điểm bài Poker (poker_hand.py). Chạy: pytest test_poker_hand.py -q"""

from __future__ import annotations

from poker_hand import (
    FLUSH, FULL_HOUSE, HIGH_CARD, ONE_PAIR, QUADS, STRAIGHT,
    STRAIGHT_FLUSH, TRIPS, TWO_PAIR, best_hand, fresh_deck, score_five,
)


def c(spec: str) -> tuple[int, str]:
    """'AS' -> (14, 'S'). Tiện viết test ngắn gọn."""
    rank_part, suit = spec[:-1], spec[-1]
    value = {"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}.get(rank_part)
    if value is None:
        value = int(rank_part)
    return (value, suit)


def cards(*specs: str):
    return [c(s) for s in specs]


def test_deck_size_and_unique():
    deck = fresh_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52


def test_high_card():
    score = score_five(cards("AS", "KH", "9D", "5C", "2S"))
    assert score.category == HIGH_CARD
    assert score.tiebreak == (14, 13, 9, 5, 2)


def test_one_pair():
    score = score_five(cards("AS", "AH", "9D", "5C", "2S"))
    assert score.category == ONE_PAIR
    assert score.tiebreak == (14, 9, 5, 2)


def test_two_pair():
    score = score_five(cards("AS", "AH", "9D", "9C", "2S"))
    assert score.category == TWO_PAIR
    assert score.tiebreak == (14, 9, 2)


def test_trips():
    score = score_five(cards("AS", "AH", "AD", "5C", "2S"))
    assert score.category == TRIPS
    assert score.tiebreak == (14, 5, 2)


def test_straight_normal():
    score = score_five(cards("9S", "8H", "7D", "6C", "5S"))
    assert score.category == STRAIGHT
    assert score.tiebreak == (9,)


def test_straight_wheel_A2345():
    score = score_five(cards("AS", "2H", "3D", "4C", "5S"))
    assert score.category == STRAIGHT
    assert score.tiebreak == (5,)   # bánh: A tính là 1, lá cao nhất là 5


def test_flush():
    score = score_five(cards("AS", "9S", "7S", "5S", "2S"))
    assert score.category == FLUSH
    assert score.tiebreak == (14, 9, 7, 5, 2)


def test_full_house():
    score = score_five(cards("AS", "AH", "AD", "5C", "5S"))
    assert score.category == FULL_HOUSE
    assert score.tiebreak == (14, 5)


def test_quads():
    score = score_five(cards("AS", "AH", "AD", "AC", "5S"))
    assert score.category == QUADS
    assert score.tiebreak == (14, 5)


def test_straight_flush():
    score = score_five(cards("9S", "8S", "7S", "6S", "5S"))
    assert score.category == STRAIGHT_FLUSH
    assert score.tiebreak == (9,)


def test_royal_flush_is_highest():
    royal = score_five(cards("AS", "KS", "QS", "JS", "TS"))
    sf = score_five(cards("9S", "8S", "7S", "6S", "5S"))
    assert royal.category == STRAIGHT_FLUSH
    assert royal.key() > sf.key()


def test_best_hand_from_seven_picks_best_five():
    # 2 bài riêng + 5 bài chung, có đủ để lên thùng phá sảnh nếu chọn đúng 5 lá.
    seven = cards("AS", "2H", "9S", "8S", "7S", "6S", "5S")
    score = best_hand(seven)
    assert score.category == STRAIGHT_FLUSH
    assert score.tiebreak == (9,)


def test_best_hand_ignores_worse_combo():
    # Có một đôi A trong 2 lá riêng, nhưng bàn chung lên sảnh thùng -> phải chọn sảnh thùng.
    seven = cards("AS", "AH", "9D", "8D", "7D", "6D", "5D")
    score = best_hand(seven)
    assert score.category == STRAIGHT_FLUSH


def test_hand_comparison_ordering():
    pair = score_five(cards("AS", "AH", "9D", "5C", "2S"))
    two_pair = score_five(cards("AS", "AH", "9D", "9C", "2S"))
    trips = score_five(cards("AS", "AH", "AD", "5C", "2S"))
    straight = score_five(cards("9S", "8H", "7D", "6C", "5S"))
    flush = score_five(cards("AS", "9S", "7S", "5S", "2S"))
    full_house = score_five(cards("AS", "AH", "AD", "5C", "5S"))
    quads = score_five(cards("AS", "AH", "AD", "AC", "5S"))
    sf = score_five(cards("9S", "8S", "7S", "6S", "5S"))
    ordered = [pair, two_pair, trips, straight, flush, full_house, quads, sf]
    for lower, higher in zip(ordered, ordered[1:]):
        assert lower.key() < higher.key()


def test_describe_names():
    from poker_hand import describe, describe_cards
    assert describe(score_five(cards("KS", "KH", "KD", "7C", "7S"))) == \
        "Full House, Kings full of Sevens"
    assert describe(score_five(cards("AS", "2H", "3D", "4C", "5S"))) == "Straight, Five high"
    assert describe(score_five(cards("AS", "KS", "QS", "JS", "TS"))) == "Royal Flush"
    assert describe(score_five(cards("6S", "6H", "9D", "9C", "2S"))) == "Two Pair, Nines and Sixes"
    assert describe(score_five(cards("AS", "9S", "7S", "5S", "2S"))) == "Flush, Ace high"
    assert describe_cards(cards("KS", "KH"), []) == "Pocket Kings"
    assert describe_cards(cards("AS", "KS"), []) == "A-K suited"
    assert describe_cards(cards("AS", "QD"), []) == "A-Q offsuit"
    assert describe_cards(cards("AS", "AH"), cards("AD", "7C", "2S")) == "Three of a Kind, Aces"


def test_tie_same_hand_equal():
    a = score_five(cards("AS", "KH", "9D", "5C", "2S"))
    b = score_five(cards("AH", "KD", "9S", "5H", "2D"))
    assert a.key() == b.key()
    assert a == b
