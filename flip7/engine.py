"""The Flip 7 rules engine.

The game is stored as an ordered list of scorekeeper entries (events). The full game
state is rebuilt by replaying them through GameState.apply(), which enforces the
rulebook and records a plain-language notice for every rule it applies. Undo is
just "drop the last event and replay".

Event types:
    start_round                         begin the next round (the dealer passes left)
    draw     player_id, card, target_id a player is dealt a card; target_id is who an
                                        action card (Freeze / Flip Three) is played on
    stay     player_id                  a player stays and banks their points
    give_second_chance  target_id       hand an extra Second Chance to another player
    resolve_action      target_id       assign the next action card that was set aside
                                        during a Flip Three; once all are assigned they
                                        take effect in order

Where the rulebook is silent, rulings come from the publisher's FAQ and the
publisher-confirmed community FAQ; see RULES_CONFORMANCE.md.
"""
from dataclasses import dataclass, field

from .cards import (FLIP_THREE, FREEZE, SECOND_CHANCE, WIN_SCORE, RuleViolation,
                    is_action, is_modifier, is_number, label)
from .deck import Deck
from .scoring import score_hand

ACTIVE = "active"
STAYED = "stayed"
FROZEN = "frozen"
BUSTED = "busted"
FLIP7 = "flip7"

STATUS_LABELS = {ACTIVE: "Active", STAYED: "Stayed", FROZEN: "Frozen",
                 BUSTED: "Busted", FLIP7: "Flip 7"}


@dataclass
class Event:
    seq: int
    type: str
    player_id: int | None = None
    target_id: int | None = None
    card: str | None = None


@dataclass
class Notice:
    level: str  # info | warn | bust | good
    text: str


@dataclass
class LogEntry:
    seq: int
    round: int
    type: str
    text: str
    notices: list = field(default_factory=list)


@dataclass
class PlayerRound:
    numbers: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    second_chance: bool = False
    status: str = ACTIVE
    bust_card: int | None = None

    @property
    def is_active(self):
        return self.status == ACTIVE

    @property
    def has_cards(self):
        return bool(self.numbers or self.modifiers or self.actions or self.second_chance)

    @property
    def breakdown(self):
        return score_hand(self.numbers, self.modifiers,
                          flip7=self.status == FLIP7, busted=self.status == BUSTED)

    @property
    def score(self):
        return self.breakdown.total


@dataclass
class RoundState:
    number: int
    dealer_id: int
    hands: dict
    ended: bool = False
    end_reason: str | None = None
    scores: dict = field(default_factory=dict)


@dataclass
class FlipThree:
    target: int
    remaining: int = 3
    deferred: list = field(default_factory=list)


@dataclass
class PendingAction:
    """A Freeze or Flip Three set aside during a Flip Three, waiting to be assigned
    (target is None) or to take effect."""
    owner: int
    card: str
    target: int | None = None


class GameState:
    def __init__(self, players):
        """players: list of (player_id, name) in seating order."""
        self.order = [pid for pid, _ in players]
        self.names = dict(players)
        self.rounds = []
        self.totals = {pid: 0 for pid in self.order}
        self.deck = Deck()
        self.log = []
        self.pending_gift = None     # player who must hand an extra Second Chance on
        self.flip_three = None       # FlipThree in progress, if any
        self.pending_actions = []    # [PendingAction] set aside during a Flip Three
        self.turn_anchor = None      # player originally dealt the Flip Three being resolved
        self.game_over = False
        self.winners = []
        self.last_actor = None
        self.last_seq = 0
        self._entry = None

    # ---- queries -------------------------------------------------------

    @property
    def round(self):
        return self.rounds[-1] if self.rounds else None

    def active_players(self):
        r = self.round
        if r is None or r.ended:
            return []
        return [pid for pid in self.order if r.hands[pid].is_active]

    def gift_candidates(self):
        if self.pending_gift is None:
            return []
        hands = self.round.hands
        return [pid for pid in self.active_players()
                if pid != self.pending_gift and not hands[pid].second_chance]

    def suggested_player(self):
        """Best guess at who is dealt the next card, to preselect in the UI."""
        active = self.active_players()
        if not active:
            return None
        if self.flip_three:
            return self.flip_three.target
        start = self.last_actor if self.last_actor is not None else self.round.dealer_id
        i = self.order.index(start)
        for step in range(1, len(self.order) + 1):
            pid = self.order[(i + step) % len(self.order)]
            if pid in active:
                return pid
        return None

    def next_to_assign(self):
        """The first set-aside card still needing a target, once no Flip Three is running."""
        if self.flip_three is not None:
            return None
        return next((p for p in self.pending_actions if p.target is None), None)

    @property
    def notices(self):
        return [(entry, n) for entry in self.log for n in entry.notices]

    def cumulative_totals(self):
        """{player_id: [0, total after round 1, total after round 2, ...]} for finished rounds."""
        series = {pid: [0] for pid in self.order}
        for r in self.rounds:
            if r.ended:
                for pid in self.order:
                    series[pid].append(series[pid][-1] + r.scores[pid])
        return series

    # ---- applying events ----------------------------------------------

    def apply(self, event):
        for pid in (event.player_id, event.target_id):
            if pid is not None and pid not in self.names:
                raise RuleViolation("That player is not in this game.")
        handler = {
            "start_round": self._start_round,
            "draw": self._draw,
            "stay": self._stay,
            "give_second_chance": self._give_second_chance,
            "resolve_action": self._resolve_action,
        }.get(event.type)
        if handler is None:
            raise RuleViolation(f"Unknown entry type {event.type!r}.")
        if self.game_over:
            raise RuleViolation("The game is over. Undo the last entry to change it.")

        self._entry = LogEntry(event.seq, self.round.number if self.round else 0,
                               event.type, "")
        handler(event)
        self.log.append(self._entry)
        self.last_seq = event.seq

    def _notice(self, level, text):
        self._entry.notices.append(Notice(level, text))

    def _name(self, pid):
        return self.names[pid]

    def _require_open_round(self):
        r = self.round
        if r is None or r.ended:
            raise RuleViolation("No round is in progress. Start the next round first.")
        return r

    def _require_nothing_to_assign(self):
        item = self.next_to_assign()
        if item is not None:
            raise RuleViolation(f"First assign the {label(item.card)} that "
                                f"{self._name(item.owner)} set aside during Flip Three.")

    def _require_no_gift(self):
        if self.pending_gift is not None:
            raise RuleViolation(f"{self._name(self.pending_gift)} must first give their extra "
                                f"Second Chance to another active player.")

    # start_round ---------------------------------------------------------

    def _start_round(self, event):
        if self.round and not self.round.ended:
            raise RuleViolation(f"Round {self.round.number} is still in progress.")
        number = len(self.rounds) + 1
        dealer = self.order[(number - 1) % len(self.order)]
        self.rounds.append(RoundState(number, dealer, {pid: PlayerRound() for pid in self.order}))
        self.last_actor = None
        self._entry.round = number
        self._entry.text = f"Round {number} begins: {self._name(dealer)} deals"
        self._notice("info", f"Round {number}: {self._name(dealer)} is the dealer and deals "
                             f"one card face up to each player.")

    # draw ----------------------------------------------------------------

    def _draw(self, event):
        r = self._require_open_round()
        self._require_no_gift()
        pid, card = event.player_id, event.card
        if pid is None:
            raise RuleViolation("Choose which player drew the card.")
        if card is None or not (is_number(card) or is_modifier(card) or is_action(card)):
            raise RuleViolation("Choose a card.")
        hand = r.hands[pid]
        name = self._name(pid)
        if not hand.is_active:
            raise RuleViolation(f"{name} is {STATUS_LABELS[hand.status].lower()} and is out of "
                                f"this round, so they can't be dealt a card.")
        ft = self.flip_three
        if ft and ft.target != pid:
            raise RuleViolation(f"Flip Three: {self._name(ft.target)} must take the next "
                                f"{ft.remaining} card(s) first.")
        self._require_nothing_to_assign()
        target = None
        if card in (FREEZE, FLIP_THREE) and not ft:
            target = self._action_target(card, event.target_id)

        if self.deck.draw(card):
            self._notice("info", "The deck ran out: the discard pile was shuffled to form a "
                                 "new deck. Cards in front of players stay where they are.")
        self.last_actor = pid
        self._entry.text = f"{name} drew {label(card)}"

        if is_number(card):
            self._draw_number(pid, hand, int(card))
        elif is_modifier(card):
            hand.modifiers.append(card)
            if card == "x2":
                self._notice("info", f"{name} gets ×2: the sum of their Number cards is doubled "
                                     f"before other modifiers are added. Modifiers can't bust.")
            else:
                self._notice("info", f"{name} gets {card} points. Modifiers can't bust and don't "
                                     f"count toward Flip 7.")
        elif card == SECOND_CHANCE:
            self._receive_second_chance(pid)
        elif ft:
            ft.deferred.append(card)
            self._notice("warn", f"{label(card)} drawn during Flip Three is set aside. {name} "
                                 f"plays it after all three cards are drawn, unless they bust.")
        else:
            self._entry.text += f", played on {self._name(target)}"
            if card == FLIP_THREE:
                # Afterwards play resumes after the player who was dealt this card.
                self.turn_anchor = pid
            self._play_action(card, target)

        if ft and self.flip_three is ft:
            ft.remaining -= 1
            if hand.status == BUSTED:
                self._finish_flip_three(ft, busted=True)
            elif ft.remaining == 0:
                self._finish_flip_three(ft)
            else:
                self._notice("info", f"Flip Three: {name} must take {ft.remaining} more card(s).")

    def _finish_flip_three(self, ft, busted=False):
        """End a Flip Three sequence that stopped without ending the round."""
        self.flip_three = None
        name = self._name(ft.target)
        self.round.hands[ft.target].actions.remove(FLIP_THREE)
        self.deck.discard_from_table(FLIP_THREE)
        if busted:
            for card in ft.deferred:
                self.deck.discard_from_table(card)
            if ft.deferred:
                self._notice("warn", f"{name} busted, so the set-aside "
                                     f"{_card_list(ft.deferred)} {_is_are(ft.deferred)} "
                                     f"discarded.")
        else:
            self._notice("info", f"{name} has taken all three Flip Three cards.")
            if ft.deferred:
                self.pending_actions[0:0] = [PendingAction(ft.target, c) for c in ft.deferred]
                self._notice("warn", f"{name} must now assign the set-aside "
                                     f"{_card_list(ft.deferred)}, in the order drawn, to active "
                                     f"players (themselves included). Nothing takes effect "
                                     f"until every card is assigned.")
        self._continue_queue()

    def _continue_queue(self):
        """Resolve assigned set-aside cards in order until one needs a target or starts a
        new Flip Three. When everything is resolved, turn order resumes after the player
        who was originally dealt the Flip Three."""
        hands = self.round.hands
        while self.pending_actions and self.flip_three is None and not self.round.ended:
            if any(p.target is None for p in self.pending_actions):
                return
            item = self.pending_actions.pop(0)
            if not hands[item.target].is_active:
                self.deck.discard_from_table(item.card)
                self._notice("warn", f"{self._name(item.target)} is already out of the round, "
                                     f"so the {label(item.card)} assigned to them is discarded.")
                continue
            self._play_action(item.card, item.target)
        if (self.flip_three is None and not self.pending_actions
                and self.turn_anchor is not None):
            self.last_actor = self.turn_anchor
            self.turn_anchor = None

    def _draw_number(self, pid, hand, n):
        name = self._name(pid)
        if n in hand.numbers:
            if hand.second_chance:
                hand.second_chance = False
                self.deck.discard_from_table(SECOND_CHANCE)
                self.deck.discard_from_table(str(n))
                self._notice("good", f"{name} drew a second {n} but used their Second Chance: "
                                     f"both cards are discarded and {name} stays in the round.")
            else:
                hand.numbers.append(n)
                hand.bust_card = n
                hand.status = BUSTED
                self._notice("bust", f"BUST! {name} drew a second {n}. {name} is now inactive "
                                     f"and scores 0 points this round.")
                self._check_round_end()
            return

        hand.numbers.append(n)
        if n == 0:
            self._notice("info", "The 0 is worth no points, but it counts toward Flip 7.")
        if len(hand.numbers) == 7:
            hand.status = FLIP7
            self._notice("good", f"FLIP 7! {name} has seven unique Number cards and scores a "
                                 f"15 point bonus. The round ends immediately for everyone.")
            self._end_round()

    def _receive_second_chance(self, pid):
        name = self._name(pid)
        hand = self.round.hands[pid]
        if not hand.second_chance:
            hand.second_chance = True
            self._notice("info", f"{name} keeps the Second Chance. It will cancel one duplicate "
                                 f"Number card this round.")
            return
        self.pending_gift = pid
        if self.gift_candidates():
            self._notice("warn", f"{name} already has a Second Chance and may only hold one. "
                                 f"They must give this one to another active player.")
        else:
            self.pending_gift = None
            self.deck.discard_from_table(SECOND_CHANCE)
            self._notice("info", f"{name} already has a Second Chance and no other active player "
                                 f"can take one, so it is discarded.")

    def _action_target(self, card, target_id):
        active = self.active_players()
        if len(active) == 1:
            if target_id is not None and target_id != active[0]:
                self._notice("warn", f"{self._name(active[0])} is the only active player, so "
                                     f"the {label(card)} must be played on them.")
            return active[0]
        if target_id is None:
            raise RuleViolation(f"Choose which active player the {label(card)} is played on.")
        if target_id not in active:
            raise RuleViolation(f"{label(card)} can only be played on an active player; "
                                f"{self._name(target_id)} is out of this round.")
        return target_id

    def _play_action(self, card, target):
        hand = self.round.hands[target]
        name = self._name(target)
        hand.actions.append(card)
        if card == FREEZE:
            hand.status = FROZEN
            self._notice("warn", f"FREEZE! {name} banks {hand.score} points and is out of "
                                 f"the round.")
            self._check_round_end()
        else:
            self.flip_three = FlipThree(target)
            self._notice("warn", f"FLIP THREE! {name} must accept the next three cards, one at "
                                 f"a time, stopping early on a bust or Flip 7.")

    # stay ----------------------------------------------------------------

    def _stay(self, event):
        r = self._require_open_round()
        self._require_no_gift()
        pid = event.player_id
        if pid is None:
            raise RuleViolation("Choose which player stays.")
        hand = r.hands[pid]
        name = self._name(pid)
        if not hand.is_active:
            raise RuleViolation(f"{name} is already out of this round.")
        if self.flip_three and self.flip_three.target == pid:
            raise RuleViolation(f"{name} can't stay during Flip Three and must take "
                                f"{self.flip_three.remaining} more card(s).")
        self._require_nothing_to_assign()
        if not hand.has_cards:
            raise RuleViolation(f"{name} can't stay yet: a player needs at least one card "
                                f"in front of them to stay.")
        hand.status = STAYED
        self.last_actor = pid
        self._entry.text = f"{name} stayed"
        self._notice("info", f"{name} stays and banks {hand.score} points.")
        self._check_round_end()

    # give_second_chance ------------------------------------------------------

    def _give_second_chance(self, event):
        self._require_open_round()
        giver = self.pending_gift
        if giver is None:
            raise RuleViolation("There is no extra Second Chance to give away.")
        target = event.target_id
        if target not in self.gift_candidates():
            raise RuleViolation("The Second Chance must go to another active player who "
                                "doesn't already have one.")
        self.round.hands[target].second_chance = True
        self.pending_gift = None
        self._entry.text = f"{self._name(giver)} gave Second Chance to {self._name(target)}"
        self._notice("info", f"{self._name(target)} receives the extra Second Chance.")

    # resolve_action --------------------------------------------------------

    def _resolve_action(self, event):
        self._require_open_round()
        self._require_no_gift()
        if self.flip_three:
            raise RuleViolation("Finish the current Flip Three first.")
        item = self.next_to_assign()
        if item is None:
            raise RuleViolation("There is no set-aside action card to assign.")
        item.target = self._action_target(item.card, event.target_id)
        self._entry.text = (f"{self._name(item.owner)} assigned the set-aside "
                            f"{label(item.card)} to {self._name(item.target)}")
        left = sum(p.target is None for p in self.pending_actions)
        if left:
            self._notice("info", f"{self._name(item.target)} will receive the "
                                 f"{label(item.card)} once all set-aside cards are assigned "
                                 f"({left} still to assign).")
        elif len(self.pending_actions) > 1:
            self._notice("info", "All set-aside cards are assigned; they now take effect in "
                                 "the order they were handed out.")
        self._continue_queue()

    # round end -------------------------------------------------------------

    def _check_round_end(self):
        if not self.active_players():
            self._end_round()

    def _end_round(self):
        r = self.round
        flip7 = [pid for pid in self.order if r.hands[pid].status == FLIP7]
        r.ended = True
        r.end_reason = "flip7" if flip7 else "no_active"

        if flip7:
            banking = [self._name(pid) for pid in self.order if r.hands[pid].is_active]
            if banking:
                self._notice("info", f"{', '.join(banking)} bank their current points.")

        unused = [pid for pid in self.order if r.hands[pid].second_chance]
        if unused:
            self._notice("info", "Unused Second Chance cards are discarded at the end of the "
                                 f"round ({', '.join(self._name(p) for p in unused)}).")

        set_aside = (self.flip_three.deferred if self.flip_three else []) + \
            [p.card for p in self.pending_actions]
        if set_aside:
            self._notice("info", f"The set-aside {_card_list(set_aside)} {_is_are(set_aside)} "
                                 f"discarded because the round ended.")

        self.pending_gift = None
        self.flip_three = None
        self.pending_actions = []
        self.turn_anchor = None
        self.deck.end_round()

        for pid in self.order:
            r.scores[pid] = r.hands[pid].score
            self.totals[pid] += r.scores[pid]
        summary = ", ".join(f"{self._name(pid)} {r.scores[pid]}" for pid in self.order)
        self._notice("info", f"Round {r.number} is over. Round scores: {summary}.")

        best = max(self.totals.values())
        leaders = [pid for pid in self.order if self.totals[pid] == best]
        passed = [pid for pid in self.order if self.totals[pid] >= WIN_SCORE]
        if not passed:
            return
        passed_text = (_name_list([f"{self._name(pid)} ({self.totals[pid]})" for pid in passed])
                       + (" both" if len(passed) == 2 else " all") + f" passed {WIN_SCORE}")
        if len(leaders) == 1:
            self.game_over = True
            self.winners = leaders
            winner = self._name(leaders[0])
            if len(passed) == 1:
                self._notice("good", f"Game over! A player reached {WIN_SCORE}. "
                                     f"{winner} wins with {best} points.")
            else:
                self._notice("good", f"Game over! {passed_text}. {winner} has the most points "
                                     f"and wins.")
        else:
            tied = _name_list([self._name(pid) for pid in leaders])
            self._notice("warn", f"{passed_text}, but {tied} are tied on {best}. Under the rules "
                                 f"of Flip 7, everyone plays another round until one player has "
                                 f"the highest score.")


def _card_list(cards):
    return ", ".join(label(c) for c in cards)


def _name_list(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _is_are(cards):
    return "is" if len(cards) == 1 else "are"


def replay(players, events):
    state = GameState(players)
    for event in events:
        state.apply(event)
    return state
