"""Runs every scenario in tests/scenarios.py at three levels:

1. engine - replay the entries through the rules engine and check every expectation;
2. web    - post the same entries to the real Flask routes and check the pages show the
            same refusals, notices and totals, and that the same entries were stored;
3. undo   - replaying all-but-the-last entry reproduces the earlier state exactly.

`pytest -v tests/test_rules_conformance.py` reads as the rules-conformance matrix.
"""
from collections import Counter

import pytest
from markupsafe import escape

from flip7.cards import RuleViolation
from flip7.engine import Event, replay

from conftest import player_ids, post
from scenarios import SCENARIOS, UNSET, Check

BY_ID = {s.id: s for s in SCENARIOS}
IDS = list(BY_ID)


def test_scenario_ids_are_unique():
    assert len(IDS) == len(SCENARIOS)


# ---- helpers -----------------------------------------------------------------------

def to_event(step, seq, ids):
    kind = {"draw": "draw", "stay": "stay", "give": "give_second_chance",
            "assign": "resolve_action", "next_round": "start_round"}[step.kind]
    return Event(seq, kind,
                 player_id=ids[step.who] if step.who else None,
                 target_id=ids[step.on] if step.on else None,
                 card=step.card)


def pending_view(state, names):
    view = []
    for item in state.pending_actions:
        if isinstance(item, tuple):          # tolerate older engine shapes
            owner, card, target = (*item, None)[:3]
        else:
            owner, card, target = item.owner, item.card, item.target
        view.append((names[owner], card, names.get(target)))
    return view


def snapshot(state):
    return {
        "rounds": [(r.number, r.dealer_id, r.ended, r.end_reason, dict(r.scores),
                    {pid: (list(h.numbers), list(h.modifiers), list(h.actions),
                           h.second_chance, h.status) for pid, h in r.hands.items()})
                   for r in state.rounds],
        "totals": dict(state.totals),
        "deck": [dict(+c) for c in (state.deck.remaining, state.deck.table, state.deck.discard)],
        "pending": repr(state.pending_actions),
        "flip_three": repr(state.flip_three),
        "gift": state.pending_gift,
        "game_over": state.game_over,
        "winners": list(state.winners),
        "suggested": state.suggested_player(),
        "log": [(e.seq, e.text, [n.text for n in e.notices]) for e in state.log],
    }


def verify(state, ids, chk, where):
    names = {pid: name for name, pid in ids.items()}
    r = state.round

    def hand(name):
        return r.hands[ids[name]]

    def each(mapping, getter, label):
        for name, want in (mapping or {}).items():
            got = getter(name)
            assert got == want, f"{where}: {label} for {name} is {got!r}, expected {want!r}"

    each(chk.status, lambda n: hand(n).status, "status")
    each(chk.hand_score, lambda n: hand(n).score, "live round score")
    each(chk.round_scores, lambda n: r.scores.get(ids[n]), "round score")
    each(chk.totals, lambda n: state.totals[ids[n]], "total")
    each(chk.numbers, lambda n: hand(n).numbers, "number cards")
    each(chk.second_chance, lambda n: hand(n).second_chance, "Second Chance")
    each(chk.table, lambda c: state.deck.table[c], "cards on table")
    each(chk.discard, lambda c: state.deck.discard[c], "cards in discard")
    if chk.round_number is not None:
        assert r.number == chk.round_number, where
    if chk.dealer is not None:
        assert names[r.dealer_id] == chk.dealer, where
    if chk.round_ended is not None:
        assert r.ended == chk.round_ended, f"{where}: round ended is {r.ended}"
    if chk.flip_three is not UNSET:
        ft = state.flip_three
        got = None if ft is None else (names[ft.target], ft.remaining)
        assert got == chk.flip_three, f"{where}: Flip Three is {got}, expected {chk.flip_three}"
    if chk.pending is not None:
        got = pending_view(state, names)
        assert got == chk.pending, f"{where}: set-aside cards are {got}, expected {chk.pending}"
    if chk.gift_from is not UNSET:
        got = names.get(state.pending_gift)
        assert got == chk.gift_from, f"{where}: Second Chance hand-off owed by {got}"
    if chk.suggested is not UNSET:
        got = names.get(state.suggested_player())
        assert got == chk.suggested, f"{where}: next player is {got}, expected {chk.suggested}"
    if chk.game_over is not None:
        assert state.game_over == chk.game_over, f"{where}: game over is {state.game_over}"
    if chk.winners is not None:
        assert [names[p] for p in state.winners] == chk.winners, where
    all_text = " | ".join(n.text for e in state.log for n in e.notices)
    for text in chk.notices:
        assert text in all_text, f"{where}: no notice containing {text!r}"
    last_text = " | ".join(n.text for n in state.log[-1].notices)
    for text in chk.last_notices:
        assert text in last_text, f"{where}: latest notices {last_text!r} lack {text!r}"


def run_engine(scenario):
    """Returns (final state, accepted events, ids, snapshot after each accepted event)."""
    ids = {name: i + 1 for i, name in enumerate(scenario.players)}
    players = [(pid, name) for name, pid in ids.items()]
    events = [Event(1, "start_round")]
    state = replay(players, events)
    snaps = [snapshot(state)]
    for n, step in enumerate(scenario.steps, 1):
        where = f"{scenario.id} step {n}"
        if isinstance(step, Check):
            verify(state, ids, step, where)
            continue
        event = to_event(step, len(events) + 1, ids)
        if step.error:
            with pytest.raises(RuleViolation, match=step.error):
                state.apply(event)
            state = replay(players, events)   # a refused entry is never stored
            continue
        try:
            state.apply(event)
        except RuleViolation as exc:
            pytest.fail(f"{where}: {step} was refused: {exc}")
        events.append(event)
        snaps.append(snapshot(state))
    return state, events, ids, snaps


# ---- level 1: engine -------------------------------------------------------------------

@pytest.mark.parametrize("scenario_id", IDS)
def test_engine(scenario_id):
    run_engine(BY_ID[scenario_id])


# ---- level 2: web ---------------------------------------------------------------------

def html(text):
    return str(escape(text))


@pytest.mark.parametrize("scenario_id", IDS)
def test_web(scenario_id, client):
    scenario = BY_ID[scenario_id]
    state, events, _, _ = run_engine(scenario)

    post(client, "/games", names="\n".join(scenario.players))
    ids = player_ids(client, 1)
    urls = {"draw": "draw", "stay": "stay", "give": "give-second-chance",
            "assign": "resolve-action", "next_round": "next-round"}
    for n, step in enumerate(scenario.steps, 1):
        if isinstance(step, Check):
            continue
        data = {}
        if step.who:
            data["player_id"] = ids[step.who]
        if step.on:
            data["target_id"] = ids[step.on]
        if step.card:
            data["card"] = step.card
        page = post(client, f"/games/1/{urls[step.kind]}", **data).get_data(as_text=True)
        if step.error:
            assert 'flash-error' in page and html(step.error) in page, \
                f"{scenario_id} step {n}: refusal {step.error!r} not shown"
        else:
            assert 'flash-error' not in page, f"{scenario_id} step {n}: unexpected refusal"

    from flip7 import db
    with client.application.app_context():
        stored = db.get_events(1)
    assert [(e.type, e.player_id, e.target_id, e.card) for e in stored] == \
           [(e.type, e.player_id, e.target_id, e.card) for e in events]

    summary = client.get("/games/1/summary").get_data(as_text=True)
    for entry in state.log:
        for notice in entry.notices:
            assert html(notice.text) in summary, f"notice missing from page: {notice.text}"
    for pid, total in state.totals.items():
        assert f"{html(state.names[pid])} <strong>{total}</strong>" in summary

    if len(stored) > 1:
        client.post("/games/1/undo")
        with client.application.app_context():
            assert len(db.get_events(1)) == len(stored) - 1


# ---- level 3: undo / replay --------------------------------------------------------------

@pytest.mark.parametrize("scenario_id", IDS)
def test_undo_replay(scenario_id):
    scenario = BY_ID[scenario_id]
    _, events, ids, snaps = run_engine(scenario)
    players = [(pid, name) for name, pid in ids.items()]
    for k in range(1, len(events) + 1):
        assert snapshot(replay(players, events[:k])) == snaps[k - 1], \
            f"replaying the first {k} entries differs from the live state"


def test_catalogue_covers_every_source():
    prefixes = Counter(s.id[0] for s in SCENARIOS)
    assert prefixes["R"] and prefixes["O"] and prefixes["C"]
