"""Scoring examples taken directly from the Flip 7 rulebook (Ruleset Edition 3.1)."""
from flip7.scoring import score_hand


def test_page5_number_cards_plus_4():
    # p.5: 11+5+12 = 28, with the +4 bonus: 32 points
    assert score_hand([11, 5, 12], ["+4"]).total == 32


def test_page10_step1_add_number_cards():
    assert score_hand([3, 11, 5, 7, 10]).total == 36


def test_page10_step2_x2_doubles():
    assert score_hand([3, 11, 5, 7, 10], ["x2"]).total == 72


def test_page10_step3_add_bonus_points():
    assert score_hand([3, 11, 5, 7, 10], ["+10"]).total == 46


def test_page11_step4_flip7_bonus():
    assert score_hand([3, 11, 5, 7, 10, 9, 4], flip7=True).total == 64


def test_page8_multiply_before_adding_modifiers():
    # "First multiply the sum of your Number cards x2, then add the additional Modifier cards."
    result = score_hand([3, 11, 5, 7, 10], ["+10", "x2"])
    assert result.total == 82
    assert result.text == "3+11+5+7+10 = 36 ×2 = 72 +10 = 82"


def test_page8_modifier_only_scores_except_x2():
    assert score_hand([], ["+4"]).total == 4
    assert score_hand([], ["x2"]).total == 0
    assert score_hand([], ["x2", "+6"]).total == 6


def test_zero_is_worth_no_points():
    assert score_hand([0, 5]).total == 5


def test_bust_scores_zero_even_with_modifiers():
    assert score_hand([7, 7], ["+10", "x2"], busted=True).total == 0


def test_all_modifiers_and_flip7_combined():
    numbers = [12, 11, 10, 9, 8, 7, 6]  # 63
    mods = ["x2", "+2", "+4", "+6", "+8", "+10"]  # 126 + 30
    assert score_hand(numbers, mods, flip7=True).total == 63 * 2 + 30 + 15
