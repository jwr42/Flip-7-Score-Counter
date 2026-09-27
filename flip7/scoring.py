"""Round scoring, in the order given on pp. 8 and 10-11 of the rulebook:

1. Add the value of Number cards.
2. If you have the x2 multiplier, double that sum.
3. Add any +N modifier cards.
4. If you Flip 7 Number cards, add 15 bonus points.

A busted player scores 0 for the round regardless of modifiers.
"""
from dataclasses import dataclass

from .cards import FLIP_7_BONUS


@dataclass(frozen=True)
class ScoreBreakdown:
    total: int
    text: str


def score_hand(numbers, modifiers=(), flip7=False, busted=False):
    if busted:
        return ScoreBreakdown(0, "Busted = 0")

    total = sum(numbers)
    if len(numbers) > 1:
        text = "+".join(str(n) for n in numbers) + f" = {total}"
    else:
        text = str(total)

    if "x2" in modifiers:
        total *= 2
        text += f" ×2 = {total}"

    bonuses = [int(m) for m in modifiers if m.startswith("+")]
    for bonus in bonuses:
        total += bonus
        text += f" +{bonus}"
    if bonuses:
        text += f" = {total}"

    if flip7:
        total += FLIP_7_BONUS
        text += f" +{FLIP_7_BONUS} Flip 7 = {total}"

    return ScoreBreakdown(total, text)
