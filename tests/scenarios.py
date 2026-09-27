"""Catalogue of Flip 7 rules and edge cases, each tied to its source.

Sources, in order of authority:
  R  = the rulebook, FLIP_7_RULES.pdf (Ruleset Edition 3.1), by page
  O  = the publisher's official FAQ (theop.games/pages/flip-7-faqs, Dized rules FAQ)
  C  = community "Flip 7 FAQ / Edge Cases" v1.4 (BoardGameGeek), by case number;
       each of these rulings cites a publisher representative on BGG

A scenario is a script of scorekeeper entries (the same entries the web app records)
interleaved with `check(...)` expectations. An entry with `error=` must be refused by
the app with a message containing that text. See tests/test_rules_conformance.py.
"""
from dataclasses import dataclass, field

from flip7.cards import FLIP_THREE as F3, FREEZE as FRZ, SECOND_CHANCE as SC
from flip7.engine import ACTIVE, BUSTED, FLIP7, FROZEN, STAYED

UNSET = object()


@dataclass
class Step:
    kind: str                 # draw | stay | give | assign | next_round
    who: str | None = None
    card: str | None = None
    on: str | None = None
    error: str | None = None


def draw(who, card, on=None, error=None):
    return Step("draw", who, str(card), on, error)


def stay(who, error=None):
    return Step("stay", who, error=error)


def give(to, error=None):
    return Step("give", on=to, error=error)


def assign(to, error=None):
    return Step("assign", on=to, error=error)


def next_round(error=None):
    return Step("next_round", error=error)


@dataclass
class Check:
    status: dict = None          # name -> status in the current round
    hand_score: dict = None      # name -> live score of the current round
    round_scores: dict = None    # name -> locked-in score of the (ended) current round
    totals: dict = None          # name -> game total
    numbers: dict = None         # name -> number cards in front of them
    second_chance: dict = None   # name -> holds a Second Chance
    round_number: int = None
    dealer: str = None
    round_ended: bool = None
    flip_three: object = UNSET   # None, or (target name, cards still to take)
    pending: list = None         # [(owner, card, assigned target or None)]
    gift_from: object = UNSET    # name who must hand on an extra Second Chance, or None
    table: dict = None           # card -> copies on the table
    discard: dict = None         # card -> copies in the discard pile
    notices: list = field(default_factory=list)       # text anywhere in the game's notices
    last_notices: list = field(default_factory=list)  # text in the latest entry's notices
    suggested: object = UNSET    # who the app expects to be dealt the next card
    game_over: bool = None
    winners: list = None


check = Check


@dataclass
class Scenario:
    id: str
    source: str
    rule: str
    steps: list
    players: list = field(default_factory=lambda: ["Ann", "Ben", "Cat"])


def flip7_round(who):
    """Seven unique high cards: 63 points + 15 bonus = 78."""
    return [draw(who, n) for n in (12, 11, 10, 9, 8, 7, 6)]


SCENARIOS = [
    # ---- Rulebook --------------------------------------------------------------
    Scenario("R01-duplicate-number-busts", "Rulebook p.1",
             "A second copy of a number busts the player, who scores 0 even with modifiers.",
             [draw("Ann", 7), draw("Ann", "+10"), draw("Ann", 7),
              check(status={"Ann": BUSTED}, hand_score={"Ann": 0},
                    last_notices=["BUST! Ann drew a second 7", "scores 0"])]),
    Scenario("R02-busted-player-is-inactive", "Rulebook pp.1, 6",
             "A busted player can't be dealt more cards or stay.",
             [draw("Ann", 7), draw("Ann", 7),
              draw("Ann", 5, error="out of this round"), stay("Ann", error="already out"),
              check(status={"Ann": BUSTED}, table={"7": 2})]),
    Scenario("R03-flip7-ends-round-with-bonus", "Rulebook pp.1, 9, 11",
             "Seven unique numbers ends the round for everyone, scores +15, and "
             "still-active players bank their points.",
             [draw("Ben", 9), draw("Cat", "+6"), stay("Cat"),
              *[draw("Ann", n) for n in (3, 11, 5, 7, 10, 9, 4)],
              check(round_ended=True, status={"Ann": FLIP7},
                    round_scores={"Ann": 64, "Ben": 9, "Cat": 6},
                    last_notices=["FLIP 7!", "Ben bank"]),
              draw("Ben", 5, error="No round is in progress")]),
    Scenario("R04-zero-counts-toward-flip7", "Rulebook p.2",
             "The 0 is worth nothing but counts as one of the seven unique numbers.",
             [*[draw("Ann", n) for n in range(6)],
              check(status={"Ann": ACTIVE}, notices=["0 is worth no points"]),
              draw("Ann", 6),
              check(status={"Ann": FLIP7}, round_scores={"Ann": 21 + 15})]),
    Scenario("R05-modifiers-never-bust-or-count", "Rulebook pp.5, 8",
             "Modifier cards can't bust and don't count toward Flip 7.",
             [*[draw("Ann", n) for n in range(6)],
              *[draw("Ann", m) for m in ("+2", "+4", "+6", "+8", "+10", "x2")],
              check(status={"Ann": ACTIVE}, hand_score={"Ann": 15 * 2 + 30})]),
    Scenario("R06-x2-before-plus-cards", "Rulebook pp.8, 10-11",
             "Multiply the number cards by 2 first, then add + cards: 36 x2 +10 = 82.",
             [*[draw("Ann", n) for n in (3, 11, 5, 7, 10)], draw("Ann", "+10"), draw("Ann", "x2"),
              check(hand_score={"Ann": 82})]),
    Scenario("R07-modifier-only-hand", "Rulebook p.8; Community Case 8",
             "A hand of only modifiers scores its + cards; x2 alone adds nothing.",
             [draw("Ann", "+2"), draw("Ann", "+6"), draw("Ann", "x2"), stay("Ann"),
              check(status={"Ann": STAYED}, hand_score={"Ann": 8})]),
    Scenario("R08-stay-needs-a-card", "Rulebook p.4",
             "You may Stay only with at least one card in front of you.",
             [stay("Ann", error="at least one card"), draw("Ann", "+4"), stay("Ann"),
              check(status={"Ann": STAYED}, last_notices=["banks 4 points"])]),
    Scenario("R09-freeze-banks-points", "Rulebook p.6",
             "Freeze: the target banks their points and is out of the round.",
             [draw("Ben", 10), draw("Ann", FRZ, on="Ben"),
              check(status={"Ben": FROZEN, "Ann": ACTIVE}, hand_score={"Ben": 10},
                    last_notices=["FREEZE! Ben banks 10 points"])]),
    Scenario("R10-action-needs-active-target", "Rulebook p.6",
             "Action cards must be played on an active player.",
             [draw("Ann", FRZ, error="Choose which active player"),
              draw("Ben", 4), stay("Ben"),
              draw("Ann", FRZ, on="Ben", error="only be played on an active player")]),
    Scenario("R11-only-active-player-must-self-target", "Rulebook p.6; Official FAQ",
             "The only active player must play an action card on themselves.",
             [draw("Ben", 4), stay("Ben"), draw("Cat", 3), stay("Cat"), draw("Ann", 9),
              draw("Ann", FRZ, on="Cat"),
              check(status={"Ann": FROZEN}, round_ended=True, round_scores={"Ann": 9},
                    last_notices=["only active player"])]),
    Scenario("R12-flip-three-forces-three-cards", "Rulebook p.6; Community Case 9",
             "The Flip Three target must take the next three cards; nobody else is dealt "
             "and the target can't Stay. The Flip Three card is then discarded.",
             [draw("Ann", F3, on="Ben"),
              check(flip_three=("Ben", 3), last_notices=["FLIP THREE!"]),
              draw("Cat", 5, error="Ben must take the next 3"),
              draw("Ben", 2), stay("Ben", error="can't stay during Flip Three"),
              draw("Ben", 3), draw("Ben", "+2"),
              check(flip_three=None, numbers={"Ben": [2, 3]}, table={F3: 0},
                    discard={F3: 1}, suggested="Ben")]),
    Scenario("R13-flip-three-stops-on-bust", "Rulebook p.6; Community Case 17",
             "A bust during Flip Three ends it immediately.",
             [draw("Ben", 9), draw("Ann", F3, on="Ben"), draw("Ben", 9),
              check(status={"Ben": BUSTED}, flip_three=None, discard={F3: 1},
                    suggested="Cat"),
              draw("Cat", 5)]),
    Scenario("R14-flip-three-stops-on-flip7", "Rulebook p.6; Community Case 18",
             "Reaching Flip 7 part-way through a Flip Three ends the round at once.",
             [*[draw("Ben", n) for n in (1, 2, 3, 4, 5)], draw("Ann", F3, on="Ben"),
              draw("Ben", 6), draw("Ben", 7),
              check(round_ended=True, status={"Ben": FLIP7}, round_scores={"Ben": 43},
                    flip_three=None)]),
    Scenario("R15-second-chance-cancels-duplicate", "Rulebook p.7; Official FAQ; Community "
             "Cases 3-4",
             "Second Chance cancels a duplicate; both cards are discarded and the player's "
             "turn ends.",
             [draw("Ann", 8), draw("Ann", SC), draw("Ann", 8),
              check(status={"Ann": ACTIVE}, numbers={"Ann": [8]}, second_chance={"Ann": False},
                    discard={"8": 1, SC: 1}, suggested="Ben",
                    last_notices=["used their Second Chance"])]),
    Scenario("R16-extra-second-chance-must-be-given", "Rulebook p.7",
             "A player may hold one Second Chance; an extra goes to an active player "
             "without one.",
             [draw("Ann", SC), draw("Ben", SC), draw("Ann", SC),
              check(gift_from="Ann"),
              draw("Cat", 5, error="must first give"),
              give("Ben", error="doesn't already have one"),
              give("Cat"),
              check(gift_from=None, second_chance={"Cat": True})]),
    Scenario("R17-extra-second-chance-discarded", "Rulebook p.7",
             "If nobody can take the extra Second Chance, it is discarded.",
             [draw("Ben", 5), stay("Ben"), draw("Cat", 6), stay("Cat"),
              draw("Ann", SC), draw("Ann", SC),
              check(gift_from=None, discard={SC: 1}, last_notices=["discarded"])]),
    Scenario("R18-unused-second-chance-discarded", "Rulebook p.7; Community Case 5",
             "Unused Second Chance cards are discarded at the end of the round.",
             [draw("Ann", SC), draw("Ann", 5), stay("Ann"),
              draw("Ben", 4), stay("Ben"), draw("Cat", 3), stay("Cat"),
              check(round_ended=True, discard={SC: 1}, last_notices=["Unused Second Chance"])]),
    Scenario("R19-round-ends-with-no-active-players", "Rulebook p.9",
             "The round ends once everyone has busted or stayed; scores are added to totals.",
             [draw("Ann", 11), draw("Ben", 5), draw("Cat", 12), draw("Ann", "+4"),
              stay("Ann"), draw("Ben", 5), stay("Cat"),
              check(round_ended=True, round_scores={"Ann": 15, "Ben": 0, "Cat": 12},
                    totals={"Ann": 15, "Ben": 0, "Cat": 12})]),
    Scenario("R20-deck-limits-copies", "Rulebook p.2",
             "There are only two 2s in the deck, so a third can't be logged.",
             [draw("Ann", 2), draw("Ben", 2), draw("Cat", 2, error="no 2 cards left")]),
    Scenario("R21-used-cards-are-not-reshuffled", "Rulebook p.12",
             "Cards from finished rounds go to the discard pile, not back into the deck.",
             [draw("Ann", 1), stay("Ann"), draw("Ben", 4), stay("Ben"), draw("Cat", 3),
              stay("Cat"), next_round(), draw("Ann", 1, error="no 1 cards left"),
              check(discard={"1": 1})]),
    Scenario("R22-dealer-passes-left", "Rulebook p.12",
             "The deck passes left each round and that player becomes the dealer.",
             [draw("Ann", "+2"), stay("Ann"), draw("Ben", "+4"), stay("Ben"),
              draw("Cat", "+6"), stay("Cat"),
              next_round(error=None),
              check(round_number=2, dealer="Ben", suggested="Cat")]),
    Scenario("R23-game-ends-at-200", "Rulebook p.12",
             "At the end of a round in which someone has 200+, the highest total wins.",
             [*flip7_round("Ann"), next_round(), *flip7_round("Ann"), next_round(),
              *flip7_round("Ann"),
              check(game_over=True, winners=["Ann"], totals={"Ann": 234}),
              next_round(error="game is over")]),

    # ---- Official FAQ ------------------------------------------------------------
    Scenario("O01-x2-excludes-plus-cards-and-bonus", "Official FAQ",
             "x2 doubles only the number cards, not + cards or the Flip 7 bonus.",
             [*[draw("Ann", n) for n in (12, 11, 10, 9, 8, 7)], draw("Ann", "+10"),
              draw("Ann", "x2"), draw("Ann", 6),
              check(round_scores={"Ann": 63 * 2 + 10 + 15})]),
    Scenario("O02-last-active-player-flip-three-self", "Official FAQ; Community Case 10",
             "The last active player must take their own Flip Three.",
             [draw("Ben", 4), stay("Ben"), draw("Cat", 3), stay("Cat"),
              draw("Ann", F3, on="Ben"),
              check(flip_three=("Ann", 3), last_notices=["only active player"])]),
    Scenario("O03-second-chance-does-not-block-freeze", "Official FAQ; Community Case 5",
             "Second Chance only protects against duplicates; it is discarded at round end.",
             [draw("Ben", SC), draw("Ann", FRZ, on="Ben"),
              check(status={"Ben": FROZEN}, second_chance={"Ben": True}),
              draw("Ann", 5), stay("Ann"), draw("Cat", 6), stay("Cat"),
              check(round_ended=True, discard={SC: 1}, last_notices=["Unused Second Chance"])]),
    Scenario("O04-tie-at-200-plays-another-round", "Official FAQ; Community Case 6",
             "A tie for the highest score at 200+ means everyone plays another round.",
             [*flip7_round("Ann"), next_round(), *flip7_round("Ben"), next_round(),
              *flip7_round("Ann"), next_round(), *flip7_round("Ben"), next_round(),
              *[draw("Ann", n) for n in (12, 11, 10, 9, 5)], stay("Ann"),
              *[draw("Ben", n) for n in (12, 11, 10, 9, 5)], stay("Ben"),
              draw("Cat", "+2"), stay("Cat"),
              check(round_ended=True, totals={"Ann": 203, "Ben": 203}, game_over=False,
                    last_notices=["tied on 203", "another round"]),
              next_round(),
              draw("Ann", "+4"), stay("Ann"), draw("Ben", 3), stay("Ben"),
              draw("Cat", "+6"), stay("Cat"),
              check(game_over=True, winners=["Ann"], totals={"Ann": 207, "Ben": 206})]),
    Scenario("O05-flip-three-in-initial-deal", "Official FAQ (Dized); Community Cases 14-16",
             "A Flip Three dealt in the initial deal is used at once, even on a player not "
             "yet dealt. Afterwards play resumes after the player originally dealt it, and "
             "the target may Stay instead of taking their initial card.",
             [draw("Ben", F3, on="Cat"),
              check(flip_three=("Cat", 3)),
              draw("Cat", 5), draw("Cat", 6), draw("Cat", 7),
              check(flip_three=None, suggested="Cat", discard={F3: 1}),
              stay("Cat"),
              check(status={"Cat": STAYED}, suggested="Ann")]),
    Scenario("O06-freeze-player-not-yet-dealt", "Official FAQ (Dized); Community Case 2",
             "A Freeze in the initial deal can knock out a player who has no cards yet.",
             [draw("Ben", FRZ, on="Cat"),
              check(status={"Cat": FROZEN}, hand_score={"Cat": 0}, suggested="Ann")]),
    Scenario("O07-freeze-yourself", "Official FAQ (Dized); Community Case 2",
             "You may play a Freeze on yourself to bank your points.",
             [draw("Ann", 10), draw("Ann", FRZ, on="Ann"),
              check(status={"Ann": FROZEN}, last_notices=["Ann banks 10 points"])]),
    Scenario("O08-turn-order-after-chained-flip-three", "Official FAQ (Dized); Community Case 16",
             "A gives Flip Three to C; C draws another Flip Three and gives it to D. "
             "Afterwards the dealer continues with B, the player after A.",
             [draw("Ann", F3, on="Cat"), draw("Cat", F3),
              check(flip_three=("Cat", 2), last_notices=["set aside"]),
              draw("Cat", 5), draw("Cat", 6),
              check(flip_three=None, pending=[("Cat", F3, None)]),
              draw("Ben", 4, error="set aside"),
              assign("Dan"),
              check(flip_three=("Dan", 3), pending=[]),
              draw("Dan", 7), draw("Dan", 8), draw("Dan", 9),
              check(flip_three=None, suggested="Ben", discard={F3: 2})],
             players=["Ann", "Ben", "Cat", "Dan"]),

    # ---- Community FAQ (publisher-confirmed rulings) ------------------------------------
    Scenario("C02-frozen-cards-stay-and-score", "Community Case 2",
             "A frozen player's cards, and the Freeze, stay in front of them and score.",
             [draw("Ben", 7), draw("Ben", "+4"), draw("Ann", FRZ, on="Ben"),
              check(hand_score={"Ben": 11}, table={"7": 1, "+4": 1, FRZ: 1})]),
    Scenario("C09-flip-three-card-discarded-after-use", "Community Case 9",
             "The Flip Three card is discarded as soon as it is resolved.",
             [draw("Ann", F3, on="Ben"), draw("Ben", 1), draw("Ben", 2), draw("Ben", 3),
              check(table={F3: 0}, discard={F3: 1})]),
    Scenario("C11a-flip-three-drawn-during-flip-three-then-bust",
             "Rulebook p.7; Community Case 11",
             "A second Flip Three drawn during a Flip Three is set aside and counts as one of "
             "the three cards; if the player then busts it is discarded.",
             [draw("Ben", 9), draw("Ann", F3, on="Ben"), draw("Ben", F3),
              check(flip_three=("Ben", 2), status={"Ben": ACTIVE}, last_notices=["set aside"]),
              draw("Ben", 9),
              check(status={"Ben": BUSTED}, flip_three=None, pending=[], discard={F3: 2},
                    table={"9": 2}, last_notices=["BUST!", "discarded"], suggested="Cat"),
              draw("Cat", 5)]),
    Scenario("C11b-flip-three-drawn-during-flip-three-then-flip7", "Community Case 11",
             "If the player reaches Flip 7, the round ends and the set-aside card is discarded.",
             [*[draw("Ben", n) for n in (1, 2, 3, 4, 5)], draw("Ann", F3, on="Ben"),
              draw("Ben", F3), draw("Ben", 6), draw("Ben", 7),
              check(round_ended=True, status={"Ben": FLIP7}, round_scores={"Ben": 43},
                    pending=[], last_notices=["FLIP 7!", "set-aside Flip Three is discarded"])]),
    Scenario("C11c-set-aside-flip-three-kept-by-player", "Community Case 11",
             "After three clean cards, the player may keep the set-aside Flip Three and "
             "resolve it straight away.",
             [draw("Ann", F3, on="Ben"), draw("Ben", F3), draw("Ben", 5), draw("Ben", 6),
              check(flip_three=None, pending=[("Ben", F3, None)],
                    last_notices=["must now assign"]),
              draw("Cat", 7, error="set aside"), stay("Ben", error="set aside"),
              assign("Ben"),
              check(flip_three=("Ben", 3), pending=[]),
              draw("Ben", 7), draw("Ben", 8), draw("Ben", 9),
              check(flip_three=None, pending=[], suggested="Ben", discard={F3: 2},
                    numbers={"Ben": [5, 6, 7, 8, 9]})]),
    Scenario("C11d-set-aside-flip-three-given-away", "Community Case 11",
             "Or the player may give the set-aside Flip Three to another active player.",
             [draw("Ann", F3, on="Ben"), draw("Ben", F3), draw("Ben", 5), draw("Ben", 6),
              assign("Cat"),
              check(flip_three=("Cat", 3), pending=[])]),
    Scenario("C12a-freeze-drawn-during-flip-three", "Rulebook p.7; Community Case 12",
             "A Freeze drawn during Flip Three is set aside and assigned afterwards.",
             [draw("Ann", F3, on="Ben"), draw("Ben", FRZ),
              check(status={"Ben": ACTIVE}, last_notices=["set aside"]),
              draw("Ben", 6), draw("Ben", 7),
              check(pending=[("Ben", FRZ, None)]),
              assign("Cat"),
              check(status={"Cat": FROZEN, "Ben": ACTIVE}, pending=[])]),
    Scenario("C12b-set-aside-freeze-discarded-on-bust", "Rulebook p.7; Community Case 12",
             "If the Flip Three player busts, the set-aside Freeze is discarded.",
             [draw("Ben", 6), draw("Ann", F3, on="Ben"), draw("Ben", FRZ), draw("Ben", 6),
              check(status={"Ben": BUSTED}, pending=[], discard={FRZ: 1, F3: 1},
                    last_notices=["discarded"])]),
    Scenario("C13-set-aside-cards-assigned-before-any-resolve", "Community Case 13",
             "Several set-aside cards are assigned in the order drawn, and none takes "
             "effect until all are assigned.",
             [draw("Ann", F3, on="Ben"), draw("Ben", FRZ), draw("Ben", F3), draw("Ben", 5),
              check(pending=[("Ben", FRZ, None), ("Ben", F3, None)]),
              assign("Cat"),
              check(pending=[("Ben", FRZ, "Cat"), ("Ben", F3, None)], status={"Cat": ACTIVE}),
              assign("Ann"),
              check(status={"Cat": FROZEN}, flip_three=("Ann", 3), pending=[])]),
    Scenario("C13a-freeze-then-flip-three-to-same-player", "Community Case 13(a)",
             "If one player is assigned a Freeze then a Flip Three, they are frozen and the "
             "Flip Three is discarded.",
             [draw("Ann", F3, on="Ben"), draw("Ben", FRZ), draw("Ben", F3), draw("Ben", 5),
              assign("Cat"), assign("Cat"),
              check(status={"Cat": FROZEN}, flip_three=None, pending=[], discard={F3: 2},
                    last_notices=["already out", "discarded"])]),
    Scenario("C13b-two-flip-threes-to-same-player", "Community Case 13(b)",
             "One player assigned two Flip Threes resolves them one after the other.",
             [draw("Ann", F3, on="Ben"), draw("Ben", F3), draw("Ben", F3), draw("Ben", 5),
              assign("Cat"), assign("Cat"),
              check(flip_three=("Cat", 3), pending=[("Ben", F3, "Cat")]),
              draw("Cat", 1), draw("Cat", 2), draw("Cat", 3),
              check(flip_three=("Cat", 3), pending=[]),
              draw("Cat", 4), draw("Cat", 6), draw("Cat", 7),
              check(flip_three=None, pending=[], discard={F3: 3}, suggested="Ben")]),
    Scenario("C13c-second-flip-three-discarded-after-bust", "Community Case 13(b)",
             "If the first Flip Three busts the player, the second one is discarded.",
             [draw("Ann", F3, on="Ben"), draw("Ben", F3), draw("Ben", F3), draw("Ben", 5),
              assign("Cat"), assign("Cat"), draw("Cat", 4), draw("Cat", 4),
              check(status={"Cat": BUSTED}, flip_three=None, pending=[], discard={F3: 3},
                    last_notices=["already out"])]),
    Scenario("C19-held-second-chance-used-during-flip-three", "Rulebook p.7; Community Case 19",
             "A Second Chance held before the Flip Three can save a bust during it.",
             [draw("Ben", 8), draw("Ben", SC), draw("Ann", F3, on="Ben"), draw("Ben", 8),
              check(status={"Ben": ACTIVE}, second_chance={"Ben": False},
                    flip_three=("Ben", 2), last_notices=["used their Second Chance"])]),
    Scenario("C20a-extra-second-chance-during-flip-three-given", "Community Case 20",
             "A second Second Chance drawn during Flip Three counts as one of the three and "
             "must be given away at once.",
             [draw("Ben", SC), draw("Ann", F3, on="Ben"), draw("Ben", SC),
              check(gift_from="Ben", flip_three=("Ben", 2)),
              draw("Ben", 5, error="must first give"),
              give("Cat"),
              check(second_chance={"Cat": True, "Ben": True}, gift_from=None),
              draw("Ben", 5), draw("Ben", 6),
              check(flip_three=None)]),
    Scenario("C20b-extra-second-chance-discarded-when-alone", "Community Case 20",
             "If the Flip Three player is the only active player, the extra Second Chance "
             "is discarded.",
             [draw("Ann", 4), stay("Ann"), draw("Cat", 3), stay("Cat"),
              draw("Ben", SC), draw("Ben", F3, on="Ann"),
              check(flip_three=("Ben", 3), last_notices=["only active player"]),
              draw("Ben", SC),
              check(gift_from=None, flip_three=("Ben", 2), discard={SC: 1},
                    last_notices=["discarded"])]),
    Scenario("C21-second-chance-drawn-during-flip-three-used", "Rulebook p.7; Community Case 21",
             "A Second Chance drawn during Flip Three is kept and can save a later bust in "
             "the same Flip Three.",
             [draw("Ben", 8), draw("Ann", F3, on="Ben"), draw("Ben", SC), draw("Ben", 8),
              check(status={"Ben": ACTIVE}, second_chance={"Ben": False},
                    flip_three=("Ben", 1))]),
]
