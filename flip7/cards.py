"""Card definitions for the 94-card Flip 7 deck (Ruleset Edition 3.1, pp. 2-3)."""


class RuleViolation(Exception):
    """An entry the rulebook does not allow. The message is shown to the scorekeeper."""


NUMBERS = [str(n) for n in range(13)]
MODIFIERS = ["+2", "+4", "+6", "+8", "+10", "x2"]
FREEZE = "freeze"
FLIP_THREE = "flip_three"
SECOND_CHANCE = "second_chance"
ACTIONS = [FREEZE, FLIP_THREE, SECOND_CHANCE]
ALL_CARDS = NUMBERS + MODIFIERS + ACTIONS

# Twelve 12s, eleven 11s ... one 1, plus a single 0; one of each modifier;
# three of each action card. 79 + 6 + 9 = 94.
DECK_COMPOSITION = {
    **{str(n): max(n, 1) for n in range(13)},
    **{m: 1 for m in MODIFIERS},
    **{a: 3 for a in ACTIONS},
}

WIN_SCORE = 200
FLIP_7_BONUS = 15

_LABELS = {
    "x2": "×2",
    FREEZE: "Freeze",
    FLIP_THREE: "Flip Three",
    SECOND_CHANCE: "Second Chance",
}


def label(card):
    return _LABELS.get(card, card)


def is_number(card):
    return card in NUMBERS


def is_modifier(card):
    return card in MODIFIERS


def is_action(card):
    return card in ACTIONS
