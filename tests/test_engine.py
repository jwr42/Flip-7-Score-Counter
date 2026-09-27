"""Rules engine tests, each tied to a rule in the Flip 7 rulebook (Ruleset Edition 3.1)."""
from collections import Counter

import pytest

from flip7.cards import DECK_COMPOSITION, FLIP_THREE, FREEZE, SECOND_CHANCE, RuleViolation
from flip7.engine import ACTIVE, BUSTED, FLIP7, FROZEN, STAYED, Event, replay

from conftest import Game, notice_text


# ---- busting (p.1) -------------------------------------------------------

def test_duplicate_number_busts_and_notifies(game):
    game.draw("Ann", 7)
    game.draw("Ann", "+10")
    entry = game.draw("Ann", 7)
    assert game.hand("Ann").status == BUSTED
    assert "BUST" in notice_text(entry) and "inactive" in notice_text(entry)
    assert game.hand("Ann").score == 0


def test_busted_player_cannot_draw_or_stay(game):
    game.draw("Ann", 7)
    game.draw("Ann", 7)
    with pytest.raises(RuleViolation, match="out of"):
        game.draw("Ann", 5)
    with pytest.raises(RuleViolation, match="already out"):
        game.stay("Ann")


# ---- stay (p.4) ------------------------------------------------------------

def test_stay_requires_a_card(game):
    with pytest.raises(RuleViolation, match="at least one card"):
        game.stay("Ann")
    game.draw("Ann", "+4")
    entry = game.stay("Ann")
    assert game.hand("Ann").status == STAYED
    assert "banks 4 points" in notice_text(entry)


# ---- round end & scoring flow (p.9) ----------------------------------------

def test_round_ends_when_no_active_players_and_totals_add(game):
    game.draw("Ann", 11)
    game.draw("Ben", 5)
    game.draw("Cat", 12)
    game.draw("Ann", "+4")
    game.stay("Ann")
    game.draw("Ben", 5)          # Ben busts
    entry = game.stay("Cat")
    r = game.state.round
    assert r.ended and r.end_reason == "no_active"
    assert (game.score("Ann"), game.score("Ben"), game.score("Cat")) == (15, 0, 12)
    assert "Round 1 is over" in notice_text(entry)
    game.start()
    assert game.state.round.number == 2
    assert game.total("Ann") == 15


def test_cannot_start_round_while_one_is_in_progress(game):
    with pytest.raises(RuleViolation, match="still in progress"):
        game.start()


def test_dealer_passes_left_each_round(game):
    assert game.state.round.dealer_id == game.ids["Ann"]
    for p in ("Ann", "Ben", "Cat"):
        game.draw(p, "+2" if p == "Ann" else ("+4" if p == "Ben" else "+6"))
        game.stay(p)
    game.start()
    assert game.state.round.dealer_id == game.ids["Ben"]


# ---- Flip 7 (pp. 1, 5, 9, 11) ------------------------------------------

def test_flip7_ends_round_immediately_with_bonus_and_others_bank():
    g = Game("Ann", "Ben", "Cat")
    g.draw("Ben", 9)
    g.draw("Cat", "+6")
    g.stay("Cat")
    for n in (3, 11, 5, 7, 10, 9):
        g.draw("Ann", n)
    entry = g.draw("Ann", 4)
    r = g.state.round
    assert r.ended and r.end_reason == "flip7"
    assert g.hand("Ann").status == FLIP7
    assert g.score("Ann") == 64            # the rulebook's own example
    assert g.score("Ben") == 9             # still active: banks current points
    assert g.score("Cat") == 6
    assert "FLIP 7" in notice_text(entry) and "Ben bank" in notice_text(entry)


def test_zero_counts_toward_flip7_but_modifiers_do_not():
    g = Game("Ann", "Ben", "Cat")
    for c in (0, 1, 2, 3, "+4", "x2", 4, 5):
        g.draw("Ann", c)
    assert g.hand("Ann").status == ACTIVE   # 7 number cards needed; has 6
    g.draw("Ann", 6)
    assert g.hand("Ann").status == FLIP7
    # (0+1+2+3+4+5+6) = 21, ×2 = 42, +4 = 46, +15 = 61
    assert g.score("Ann") == 61


# ---- Second Chance (p.7) ---------------------------------------------------

def test_second_chance_cancels_duplicate_and_both_are_discarded(game):
    game.draw("Ann", 8)
    game.draw("Ann", SECOND_CHANCE)
    entry = game.draw("Ann", 8)
    hand = game.hand("Ann")
    assert hand.status == ACTIVE and hand.numbers == [8] and not hand.second_chance
    assert "Second Chance" in notice_text(entry)
    deck = game.state.deck
    assert deck.discard["8"] == 1 and deck.discard[SECOND_CHANCE] == 1


def test_extra_second_chance_must_be_given_to_eligible_player(game):
    game.draw("Ann", SECOND_CHANCE)
    game.draw("Ben", SECOND_CHANCE)
    game.draw("Ann", SECOND_CHANCE)
    assert game.state.pending_gift == game.ids["Ann"]
    assert game.state.gift_candidates() == [game.ids["Cat"]]
    with pytest.raises(RuleViolation, match="must first give"):
        game.draw("Cat", 5)
    with pytest.raises(RuleViolation):
        game.give("Ben")               # already has one
    game.give("Cat")
    assert game.hand("Cat").second_chance and game.state.pending_gift is None


def test_extra_second_chance_discarded_when_nobody_eligible():
    g = Game("Ann", "Ben", "Cat")
    g.draw("Ben", 5)
    g.stay("Ben")
    g.draw("Cat", 6)
    g.stay("Cat")
    g.draw("Ann", SECOND_CHANCE)
    entry = g.draw("Ann", SECOND_CHANCE)
    assert g.state.pending_gift is None
    assert "discarded" in notice_text(entry)
    assert g.state.deck.discard[SECOND_CHANCE] == 1


def test_unused_second_chance_discarded_at_round_end(game):
    game.draw("Ann", SECOND_CHANCE)
    game.draw("Ann", 5)
    game.stay("Ann")
    game.draw("Ben", 4)
    game.stay("Ben")
    game.draw("Cat", 3)
    entry = game.stay("Cat")
    assert "Unused Second Chance" in notice_text(entry)
    assert game.state.deck.discard[SECOND_CHANCE] == 1


# ---- Freeze (p.6) ----------------------------------------------------------

def test_freeze_banks_target_points(game):
    game.draw("Ben", 10)
    entry = game.draw("Ann", FREEZE, on="Ben")
    assert game.hand("Ben").status == FROZEN
    assert "banks 10 points" in notice_text(entry)
    assert game.hand("Ann").status == ACTIVE


def test_action_card_needs_an_active_target(game):
    with pytest.raises(RuleViolation, match="Choose which active player"):
        game.draw("Ann", FREEZE)
    game.draw("Ben", 4)
    game.stay("Ben")
    with pytest.raises(RuleViolation, match="only be played on an active player"):
        game.draw("Ann", FREEZE, on="Ben")


def test_only_active_player_must_play_action_on_self(game):
    game.draw("Ben", 4)
    game.stay("Ben")
    game.draw("Cat", 3)
    game.stay("Cat")
    game.draw("Ann", 9)
    entry = game.draw("Ann", FREEZE, on="Cat")
    assert game.hand("Ann").status == FROZEN
    assert "only active player" in notice_text(entry)
    assert game.state.round.ended


# ---- Flip Three (pp. 6-7) --------------------------------------------------

def test_flip_three_forces_next_three_cards(game):
    game.draw("Ann", FLIP_THREE, on="Ben")
    assert game.state.flip_three.target == game.ids["Ben"]
    with pytest.raises(RuleViolation, match="Ben must take the next 3"):
        game.draw("Cat", 5)
    game.draw("Ben", 2)
    with pytest.raises(RuleViolation, match="can't stay during Flip Three"):
        game.stay("Ben")
    game.draw("Ben", 3)
    game.draw("Ben", "+2")
    assert game.state.flip_three is None
    assert game.hand("Ben").numbers == [2, 3]


def test_flip_three_stops_early_on_bust(game):
    game.draw("Ben", 9)
    game.draw("Ann", FLIP_THREE, on="Ben")
    game.draw("Ben", FREEZE)          # set aside
    entry = game.draw("Ben", 9)       # bust
    assert game.hand("Ben").status == BUSTED
    assert game.state.flip_three is None and game.state.pending_actions == []
    assert "discarded" in notice_text(entry)
    game.draw("Cat", 5)               # play continues normally


def test_freeze_drawn_during_flip_three_resolves_after(game):
    game.draw("Ann", FLIP_THREE, on="Ben")
    entry = game.draw("Ben", FREEZE)
    assert "set aside" in notice_text(entry)
    assert game.hand("Ben").status == ACTIVE
    game.draw("Ben", 6)
    entry = game.draw("Ben", 7)
    assert [(p.owner, p.card, p.target) for p in game.state.pending_actions] == \
        [(game.ids["Ben"], FREEZE, None)]
    with pytest.raises(RuleViolation, match="First assign"):
        game.draw("Cat", 5)
    game.assign("Cat")
    assert game.hand("Cat").status == FROZEN
    assert game.state.pending_actions == []


def test_second_chance_during_flip_three_can_be_used(game):
    game.draw("Ann", FLIP_THREE, on="Ben")
    game.draw("Ben", 4)
    game.draw("Ben", SECOND_CHANCE)
    game.draw("Ben", 4)
    assert game.hand("Ben").status == ACTIVE
    assert game.state.flip_three is None


def test_flip7_during_flip_three_ends_round():
    g = Game("Ann", "Ben", "Cat")
    for n in (1, 2, 3, 4):
        g.draw("Ben", n)
    g.draw("Ann", FLIP_THREE, on="Ben")
    g.draw("Ben", 5)
    g.draw("Ben", 6)
    g.draw("Ben", 7)
    assert g.state.round.ended and g.hand("Ben").status == FLIP7
    assert g.score("Ben") == 28 + 15


# ---- deck running out mid-Flip Three (p.12; Community Cases 9, 11, 12) --------------

def _deck_down_to(game, *cards):
    """Leave only `cards` in the deck; everything else is in the discard pile."""
    game.state.deck.remaining = Counter(cards)
    game.state.deck.discard = Counter(DECK_COMPOSITION) - Counter(cards)


def _assert_all_cards_accounted_for(deck):
    for card, copies in DECK_COMPOSITION.items():
        assert deck.remaining[card] + deck.table[card] + deck.discard[card] == copies, card


def test_deck_runs_out_during_flip_three(game):
    _deck_down_to(game, FLIP_THREE, "5")
    game.draw("Ann", FLIP_THREE, on="Ben")
    game.draw("Ben", 5)
    deck = game.state.deck
    assert deck.size == 0 and game.state.flip_three.remaining == 2

    old_discard = Counter(deck.discard)
    entry = game.draw("Ben", 7)
    assert "The deck ran out" in notice_text(entry)
    assert +deck.remaining == old_discard - Counter({"7": 1})
    assert deck.table[FLIP_THREE] == 1 and deck.remaining[FLIP_THREE] == 2   # stays in front of Ben
    assert deck.table["5"] == 1 and deck.remaining["5"] == 4
    assert game.state.flip_three.remaining == 1
    _assert_all_cards_accounted_for(deck)

    game.draw("Ben", "+4")
    assert game.state.flip_three is None
    assert deck.table[FLIP_THREE] == 0 and deck.discard[FLIP_THREE] == 1   # discarded once resolved
    assert game.hand("Ben").numbers == [5, 7]
    _assert_all_cards_accounted_for(deck)


def test_set_aside_cards_stay_out_of_a_mid_flip_three_reshuffle(game):
    _deck_down_to(game, FLIP_THREE, FREEZE)
    game.draw("Ann", FLIP_THREE, on="Ben")
    game.draw("Ben", FREEZE)                      # set aside; deck now empty
    deck = game.state.deck
    assert deck.size == 0

    game.draw("Ben", 7)                           # reshuffle
    assert deck.table[FREEZE] == 1 and deck.remaining[FREEZE] == 2
    _assert_all_cards_accounted_for(deck)

    game.draw("Ben", 8)
    assert [(p.card, p.target) for p in game.state.pending_actions] == [(FREEZE, None)]
    game.assign("Cat")
    assert game.hand("Cat").status == FROZEN
    _assert_all_cards_accounted_for(deck)


# ---- deck validation -------------------------------------------------------

def test_third_two_is_rejected(game):
    game.draw("Ann", 2)
    game.draw("Ben", 2)
    with pytest.raises(RuleViolation, match="no 2 cards left"):
        game.draw("Cat", 2)


def test_round_cards_are_discarded_not_returned(game):
    game.draw("Ann", 1)
    game.stay("Ann")
    game.draw("Ben", 4)
    game.stay("Ben")
    game.draw("Cat", 3)
    game.stay("Cat")
    game.start()
    with pytest.raises(RuleViolation, match="no 1 cards left"):
        game.draw("Ann", 1)
    assert game.state.deck.discard["1"] == 1


# ---- game end (p.12) ---------------------------------------------------------

def test_game_ends_after_round_when_someone_reaches_200():
    g = Game("Ann", "Ben", "Cat")
    for rnd in range(3):
        for n in (12, 11, 10, 9, 8, 7, 6):   # 63 + 15 = 78 per round
            g.draw("Ann", n)
        if rnd < 2:
            assert not g.state.game_over
            g.start()
    assert g.total("Ann") == 234
    assert g.state.game_over and g.state.winners == [g.ids["Ann"]]
    with pytest.raises(RuleViolation, match="game is over"):
        g.start()


def test_game_continues_below_200_and_highest_total_wins():
    g = Game("Ann", "Ben", "Cat")
    # Ann and Ben alternate Flip 7s worth 78 each, reaching 156 apiece after 4 rounds.
    plan = ["Ann", "Ben", "Ann", "Ben"]
    for i, who in enumerate(plan):
        for n in (12, 11, 10, 9, 8, 7, 6):
            g.draw(who, n)
        if i < len(plan) - 1:
            g.start()
    assert g.total("Ann") == g.total("Ben") == 156
    assert not g.state.game_over
    g.start()
    # Round 5: Ann stays one point short of 200, Ben busts.
    g.draw("Ann", 12); g.draw("Ann", 11); g.draw("Ann", 10); g.draw("Ann", "+10")
    g.stay("Ann")                       # 43 -> 199
    g.draw("Ben", 12); g.draw("Ben", 11); g.draw("Ben", 9); g.draw("Ben", "+2")
    g.draw("Ben", 9)                    # Ben busts
    g.draw("Cat", 5)
    g.stay("Cat")
    assert not g.state.game_over       # 199 < 200: the game continues
    g.start()
    g.draw("Ann", 5); g.stay("Ann")    # 204
    g.draw("Ben", 12); g.draw("Ben", 11); g.draw("Ben", 8); g.draw("Ben", "+8")
    g.draw("Ben", 7); g.draw("Ben", 6); g.stay("Ben")   # 12+11+8+7+6+8 = 52 -> 208
    g.draw("Cat", 4); g.stay("Cat")
    assert g.state.game_over and g.state.winners == [g.ids["Ben"]]


def test_exact_tie_at_200_plays_another_round():
    # Official FAQ: a tie for the highest score at 200+ means everyone plays on.
    g = Game("Ann", "Ben")
    g.state.totals = {g.ids["Ann"]: 190, g.ids["Ben"]: 195}
    g.draw("Ann", 10)
    g.stay("Ann")
    g.draw("Ben", 5)
    g.stay("Ben")
    assert not g.state.game_over
    assert "another round" in notice_text(g.state.log[-1])
    g.start()
    g.draw("Ann", 3)
    g.stay("Ann")
    g.draw("Ben", 4)
    g.stay("Ben")
    assert g.state.game_over and g.state.winners == [g.ids["Ben"]]


# ---- undo / replay -----------------------------------------------------------

def test_replay_without_last_event_restores_state():
    players = [(1, "Ann"), (2, "Ben"), (3, "Cat")]
    events = [Event(1, "start_round"), Event(2, "draw", 1, None, "7"),
              Event(3, "draw", 2, None, "9"), Event(4, "draw", 1, None, "7")]
    busted = replay(players, events)
    assert busted.round.hands[1].status == BUSTED
    undone = replay(players, events[:-1])
    assert undone.round.hands[1].status == ACTIVE
    assert undone.round.hands[1].numbers == [7]
    assert undone.deck.remaining["7"] == 6
