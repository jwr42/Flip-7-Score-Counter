"""Tracks where every card of the deck is: still in the deck, on the table, or discarded.

Rulebook p. 12: cards from finished rounds are set aside, not shuffled back in.
When the deck runs out, the discard pile is shuffled to form a new deck; cards in
front of players stay where they are, even if that player has busted.
"""
from collections import Counter

from .cards import DECK_COMPOSITION, RuleViolation, label


class Deck:
    def __init__(self):
        self.remaining = Counter(DECK_COMPOSITION)
        self.table = Counter()
        self.discard = Counter()

    @property
    def size(self):
        return sum(self.remaining.values())

    def can_draw(self, card):
        if self.remaining[card] > 0:
            return True
        return self.size == 0 and self.discard[card] > 0

    def draw(self, card):
        """Move a card from the deck to the table. Returns True if the deck was reshuffled first."""
        reshuffled = False
        if self.remaining[card] == 0:
            if self.size == 0 and self.discard[card] > 0:
                self.remaining, self.discard = self.discard, Counter()
                reshuffled = True
            else:
                raise RuleViolation(self._unavailable(card))
        self.remaining[card] -= 1
        self.table[card] += 1
        return reshuffled

    def discard_from_table(self, card):
        self.table[card] -= 1
        self.discard[card] += 1

    def end_round(self):
        self.discard.update(self.table)
        self.table = Counter()

    def _unavailable(self, card):
        name = label(card)
        if self.size == 0:
            return (f"The deck is empty and the discard pile has no {name} cards to "
                    f"reshuffle. Check the card and try again.")
        return (f"There are no {name} cards left in the deck. All {DECK_COMPOSITION[card]} "
                f"are accounted for ({self.table[card]} on the table, "
                f"{self.discard[card]} in the discard pile). Check the card and try again.")
