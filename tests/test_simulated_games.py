"""Plays hundreds of complete random games the way they happen at the table, and checks
the engine's invariants after every entry. This finds rule combinations that nobody
thought to write a scenario for.

The simulator shuffles a real 94-card deck and deals from it in order. It follows the
physical flow of play: the Flip Three target takes the next cards, set-aside action
cards are assigned before anything else, an extra Second Chance is handed on, and each
player hits until their round score passes a random threshold. When the deck runs out
it reshuffles the engine's own discard pile, as the rulebook says.
"""
import random
from collections import Counter

import pytest

from flip7.cards import (DECK_COMPOSITION, FLIP_THREE, FREEZE, SECOND_CHANCE, WIN_SCORE,
                         RuleViolation)
from flip7.engine import BUSTED, FLIP7, Event, GameState

GAMES = 500


def reference_score(hand):
    """Independent re-implementation of rulebook pp.8, 10-11 (not flip7.scoring)."""
    if hand.status == BUSTED:
        return 0
    total = sum(hand.numbers)
    if "x2" in hand.modifiers:
        total *= 2
    total += sum(int(m[1:]) for m in hand.modifiers if m.startswith("+"))
    if len(set(hand.numbers)) >= 7:
        total += 15
    return total


def pending_cards(state):
    for item in state.pending_actions:
        yield item[1] if isinstance(item, tuple) else item.card


def check_invariants(state, deck_order, where):
    deck = state.deck
    for card, copies in DECK_COMPOSITION.items():
        seen = deck.remaining[card] + deck.table[card] + deck.discard[card]
        assert seen == copies, f"{where}: {card} accounted {seen} times, deck has {copies}"
        assert min(deck.remaining[card], deck.table[card], deck.discard[card]) >= 0, where
    assert Counter(deck_order) == +deck.remaining, f"{where}: deck contents drifted"

    r = state.round
    if not r.ended:
        # Every card on the table is visible in front of someone or waiting to be used.
        visible = Counter()
        for hand in r.hands.values():
            visible.update(str(n) for n in hand.numbers)
            visible.update(hand.modifiers)
            visible.update(hand.actions)
            visible[SECOND_CHANCE] += hand.second_chance
        if state.flip_three:
            visible.update(state.flip_three.deferred)
        visible.update(pending_cards(state))
        visible[SECOND_CHANCE] += state.pending_gift is not None
        assert +visible == +deck.table, f"{where}: table {+deck.table} vs visible {+visible}"

    for pid, hand in r.hands.items():
        if hand.status == BUSTED:
            assert len(hand.numbers) == len(set(hand.numbers)) + 1, where
        else:
            assert len(hand.numbers) == len(set(hand.numbers)), f"{where}: duplicate kept"
        if hand.status == FLIP7:
            assert len(hand.numbers) == 7 and r.ended, f"{where}: Flip 7 didn't end the round"

    running = {pid: 0 for pid in state.order}
    for rnd in state.rounds:
        if rnd.ended:
            for pid, hand in rnd.hands.items():
                assert rnd.scores[pid] == reference_score(hand), \
                    f"{where}: round {rnd.number} score {rnd.scores[pid]} for {pid}, " \
                    f"reference says {reference_score(hand)} ({hand})"
                running[pid] += rnd.scores[pid]
    assert running == state.totals, f"{where}: totals don't match the round scores"

    best = max(state.totals.values())
    leaders = [pid for pid, t in state.totals.items() if t == best]
    should_end = r.ended and best >= WIN_SCORE and len(leaders) == 1
    assert state.game_over == should_end, \
        f"{where}: game over is {state.game_over} with totals {state.totals}"
    if state.game_over:
        assert state.winners == leaders


def simulate(seed):
    rng = random.Random(seed)
    names = ["Ann", "Ben", "Cat", "Dan", "Eve", "Fay", "Gus", "Hal"][:rng.randint(3, 8)]
    players = [(i + 1, n) for i, n in enumerate(names)]
    state = GameState(players)
    history = []
    deck_order = [c for c, n in DECK_COMPOSITION.items() for _ in range(n)]
    rng.shuffle(deck_order)
    thresholds = {}

    def apply(type_, **fields):
        event = Event(len(history) + 1, type_, **fields)
        history.append(event)
        try:
            state.apply(event)
        except RuleViolation as exc:
            pytest.fail(f"seed {seed}: legal entry refused: {event}: {exc}\n"
                        f"history: {history}")
        check_invariants(state, deck_order, f"seed {seed} entry {event.seq} {event}")

    def deal(pid):
        nonlocal deck_order
        if not deck_order:
            deck_order = [c for c, n in state.deck.discard.items() for _ in range(n)]
            if not deck_order:
                return False          # every card is in front of a player
            rng.shuffle(deck_order)
        card = deck_order.pop()
        target = rng.choice(state.active_players()) if card in (FREEZE, FLIP_THREE) else None
        apply("draw", player_id=pid, card=card, target_id=target)
        return True

    apply("start_round")
    for _ in range(20000):
        if state.game_over:
            return state
        r = state.round
        if r.ended:
            apply("start_round")
            thresholds = {pid: rng.randint(8, 45) for pid in state.order}
            continue
        if not thresholds:
            thresholds = {pid: rng.randint(8, 45) for pid in state.order}
        if state.pending_gift is not None:
            apply("give_second_chance", target_id=rng.choice(state.gift_candidates()))
        elif state.pending_actions and state.flip_three is None:
            apply("resolve_action", target_id=rng.choice(state.active_players()))
        elif state.flip_three is not None:
            if not deal(state.flip_three.target):
                return state
        else:
            pid = state.suggested_player()
            hand = r.hands[pid]
            if hand.has_cards and hand.score >= thresholds[pid]:
                apply("stay", player_id=pid)
            elif not deal(pid):
                return state
    pytest.fail(f"seed {seed}: game did not finish")


@pytest.mark.parametrize("block", range(10))
def test_simulated_games(block):
    per_block = GAMES // 10
    finished = 0
    for seed in range(block * per_block, (block + 1) * per_block):
        finished += simulate(seed).game_over
    assert finished >= per_block * 0.95
