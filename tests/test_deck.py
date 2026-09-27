from collections import Counter

import pytest

from flip7.cards import DECK_COMPOSITION, RuleViolation
from flip7.deck import Deck


def test_deck_has_94_cards_per_rulebook():
    assert sum(DECK_COMPOSITION.values()) == 94
    assert DECK_COMPOSITION["12"] == 12 and DECK_COMPOSITION["1"] == 1 and DECK_COMPOSITION["0"] == 1
    assert sum(DECK_COMPOSITION[str(n)] for n in range(13)) == 79
    assert all(DECK_COMPOSITION[m] == 1 for m in ["+2", "+4", "+6", "+8", "+10", "x2"])
    assert all(DECK_COMPOSITION[a] == 3 for a in ["freeze", "flip_three", "second_chance"])


def test_cannot_draw_more_copies_than_exist():
    deck = Deck()
    deck.draw("2")
    deck.draw("2")
    assert not deck.can_draw("2")
    with pytest.raises(RuleViolation, match="no 2 cards left"):
        deck.draw("2")


def test_reshuffle_only_when_deck_is_empty_and_table_cards_stay_out():
    deck = Deck()
    deck.remaining = Counter()
    deck.discard = Counter({"5": 2})
    deck.table = Counter({"7": 1})
    assert deck.can_draw("5") and not deck.can_draw("7")
    assert deck.draw("5") is True
    assert deck.remaining["5"] == 1 and deck.discard == Counter()
    assert deck.table["7"] == 1 and deck.remaining["7"] == 0
    with pytest.raises(RuleViolation):
        deck.draw("7")


def test_no_reshuffle_while_cards_remain():
    deck = Deck()
    deck.remaining = Counter({"9": 1})
    deck.discard = Counter({"5": 3})
    with pytest.raises(RuleViolation):
        deck.draw("5")


def test_round_end_moves_table_to_discard():
    deck = Deck()
    deck.draw("12")
    deck.draw("freeze")
    deck.end_round()
    assert deck.table == Counter() or sum(deck.table.values()) == 0
    assert deck.discard["12"] == 1 and deck.discard["freeze"] == 1
    assert deck.size == 92
