# Flip 7 rules conformance

This page lists every rule and edge case the score keeper is checked against, where each ruling comes from, and the test that proves it. The table is generated from `tests/scenarios.py`, which is the single source of truth.

## Sources, in order of authority

1. **Rulebook:** `FLIP_7_RULES.pdf`, Ruleset Edition 3.1 (cited by page).
2. **Official FAQ:** the publisher's FAQ at [theop.games](https://theop.games/pages/flip-7-faqs) and on [Dized](https://rules.dized.com/game/dPDRM857TU-BFRF7LzGE0g/faq).
3. **Community FAQ:** [Flip 7 FAQ / Edge Cases v1.4](https://boardgamegeek.com/filepage/292492/flip-7-faq-edge-cases) on BoardGameGeek ([PDF mirror](https://www.goblins.net/files/images/flip_7_faq_version_1.4.pdf)), cited by case number. Every case used here quotes a publisher representative on the BGG forums.

## How the checks work

```bash
.venv/bin/pytest -v tests/test_rules_conformance.py tests/test_simulated_games.py
```

- **Engine:** each scenario's entries are replayed through the rules engine, and the test checks statuses, scores, totals, Flip Three progress, set-aside cards, Second Chance hand-offs, deck, table and discard counts, notices, the suggested next player, and the winner.
- **Web:** the same entries are posted to the real Flask routes. The test checks that refusals are shown, that every notice and total appears on the summary page, that the stored entries match, and that Undo removes one entry.
- **Undo:** replaying the first *k* entries reproduces the live state after *k* entries, for every *k*.
- **Deck running out during a Flip Three:** two tests in `tests/test_engine.py` (`test_deck_runs_out_during_flip_three` and `test_set_aside_cards_stay_out_of_a_mid_flip_three_reshuffle`) check that the discard pile becomes the new deck, while the Flip Three being resolved, any set-aside cards and all cards in front of players stay out of it (Rulebook p.12; Community Cases 9, 11 and 12).
- **Simulation:** 500 random complete games (3–8 players) are dealt from a shuffled 94-card deck. After every entry the test checks that:
  - all 94 cards are accounted for, and every card on the table is visible in front of someone;
  - no active player holds a duplicate number;
  - Flip 7 always ends the round;
  - round scores match an independent reference scorer, and totals are the sum of round scores;
  - the game ends only when a single player leads with at least 200;
  - no legal entry is ever refused.

## Catalogue (48 scenarios)

| Test ID | Rule | Source | Ruling |
| --- | --- | --- | --- |
| `R01-duplicate-number-busts` | A second copy of a number busts the player, who scores 0 even with modifiers. | Rulebook p.1 | Rulebook |
| `R02-busted-player-is-inactive` | A busted player can't be dealt more cards or stay. | Rulebook pp.1, 6 | Rulebook |
| `R03-flip7-ends-round-with-bonus` | Seven unique numbers ends the round for everyone, scores +15, and still-active players bank their points. | Rulebook pp.1, 9, 11 | Rulebook |
| `R04-zero-counts-toward-flip7` | The 0 is worth nothing but counts as one of the seven unique numbers. | Rulebook p.2 | Rulebook |
| `R05-modifiers-never-bust-or-count` | Modifier cards can't bust and don't count toward Flip 7. | Rulebook pp.5, 8 | Rulebook |
| `R06-x2-before-plus-cards` | Multiply the number cards by 2 first, then add + cards: 36 x2 +10 = 82. | Rulebook pp.8, 10-11 | Rulebook |
| `R07-modifier-only-hand` | A hand of only modifiers scores its + cards; x2 alone adds nothing. | Rulebook p.8; Community Case 8 | Rulebook |
| `R08-stay-needs-a-card` | You may Stay only with at least one card in front of you. | Rulebook p.4 | Rulebook |
| `R09-freeze-banks-points` | Freeze: the target banks their points and is out of the round. | Rulebook p.6 | Rulebook |
| `R10-action-needs-active-target` | Action cards must be played on an active player. | Rulebook p.6 | Rulebook |
| `R11-only-active-player-must-self-target` | The only active player must play an action card on themselves. | Rulebook p.6; Official FAQ | Rulebook |
| `R12-flip-three-forces-three-cards` | The Flip Three target must take the next three cards; nobody else is dealt and the target can't Stay. The Flip Three card is then discarded. | Rulebook p.6; Community Case 9 | Rulebook |
| `R13-flip-three-stops-on-bust` | A bust during Flip Three ends it immediately. | Rulebook p.6; Community Case 17 | Rulebook |
| `R14-flip-three-stops-on-flip7` | Reaching Flip 7 part-way through a Flip Three ends the round at once. | Rulebook p.6; Community Case 18 | Rulebook |
| `R15-second-chance-cancels-duplicate` | Second Chance cancels a duplicate; both cards are discarded and the player's turn ends. | Rulebook p.7; Official FAQ; Community Cases 3-4 | Rulebook |
| `R16-extra-second-chance-must-be-given` | A player may hold one Second Chance; an extra goes to an active player without one. | Rulebook p.7 | Rulebook |
| `R17-extra-second-chance-discarded` | If nobody can take the extra Second Chance, it is discarded. | Rulebook p.7 | Rulebook |
| `R18-unused-second-chance-discarded` | Unused Second Chance cards are discarded at the end of the round. | Rulebook p.7; Community Case 5 | Rulebook |
| `R19-round-ends-with-no-active-players` | The round ends once everyone has busted or stayed; scores are added to totals. | Rulebook p.9 | Rulebook |
| `R20-deck-limits-copies` | There are only two 2s in the deck, so a third can't be logged. | Rulebook p.2 | Rulebook |
| `R21-used-cards-are-not-reshuffled` | Cards from finished rounds go to the discard pile, not back into the deck. | Rulebook p.12 | Rulebook |
| `R22-dealer-passes-left` | The deck passes left each round and that player becomes the dealer. | Rulebook p.12 | Rulebook |
| `R23-game-ends-at-200` | At the end of a round in which someone has 200+, the highest total wins. | Rulebook p.12 | Rulebook |
| `R24-several-players-pass-200` | When several players pass 200 in the same round, the one with the most points wins, and the notice names everyone who passed 200. | Rulebook p.12 | Rulebook |
| `O01-x2-excludes-plus-cards-and-bonus` | x2 doubles only the number cards, not + cards or the Flip 7 bonus. | Official FAQ | Official FAQ |
| `O02-last-active-player-flip-three-self` | The last active player must take their own Flip Three. | Official FAQ; Community Case 10 | Official FAQ |
| `O03-second-chance-does-not-block-freeze` | Second Chance only protects against duplicates; it is discarded at round end. | Official FAQ; Community Case 5 | Official FAQ |
| `O04-tie-at-200-plays-another-round` | A tie for the highest score at 200+ means everyone plays another round. | Official FAQ; Community Case 6 | Official FAQ |
| `O05-flip-three-in-initial-deal` | A Flip Three dealt in the initial deal is used at once, even on a player not yet dealt. Afterwards play resumes after the player originally dealt it, and the target may Stay instead of taking their initial card. | Official FAQ (Dized); Community Cases 14-16 | Official FAQ |
| `O06-freeze-player-not-yet-dealt` | A Freeze in the initial deal can knock out a player who has no cards yet. | Official FAQ (Dized); Community Case 2 | Official FAQ |
| `O07-freeze-yourself` | You may play a Freeze on yourself to bank your points. | Official FAQ (Dized); Community Case 2 | Official FAQ |
| `O08-turn-order-after-chained-flip-three` | A gives Flip Three to C; C draws another Flip Three and gives it to D. Afterwards the dealer continues with B, the player after A. | Official FAQ (Dized); Community Case 16 | Official FAQ |
| `C02-frozen-cards-stay-and-score` | A frozen player's cards, and the Freeze, stay in front of them and score. | Community Case 2 | Publisher-confirmed (community FAQ) |
| `C09-flip-three-card-discarded-after-use` | The Flip Three card is discarded as soon as it is resolved. | Community Case 9 | Publisher-confirmed (community FAQ) |
| `C11a-flip-three-drawn-during-flip-three-then-bust` | A second Flip Three drawn during a Flip Three is set aside and counts as one of the three cards; if the player then busts it is discarded. | Rulebook p.7; Community Case 11 | Publisher-confirmed (community FAQ) |
| `C11b-flip-three-drawn-during-flip-three-then-flip7` | If the player reaches Flip 7, the round ends and the set-aside card is discarded. | Community Case 11 | Publisher-confirmed (community FAQ) |
| `C11c-set-aside-flip-three-kept-by-player` | After three clean cards, the player may keep the set-aside Flip Three and resolve it straight away. | Community Case 11 | Publisher-confirmed (community FAQ) |
| `C11d-set-aside-flip-three-given-away` | Or the player may give the set-aside Flip Three to another active player. | Community Case 11 | Publisher-confirmed (community FAQ) |
| `C12a-freeze-drawn-during-flip-three` | A Freeze drawn during Flip Three is set aside and assigned afterwards. | Rulebook p.7; Community Case 12 | Publisher-confirmed (community FAQ) |
| `C12b-set-aside-freeze-discarded-on-bust` | If the Flip Three player busts, the set-aside Freeze is discarded. | Rulebook p.7; Community Case 12 | Publisher-confirmed (community FAQ) |
| `C13-set-aside-cards-assigned-before-any-resolve` | Several set-aside cards are assigned in the order drawn, and none takes effect until all are assigned. | Community Case 13 | Publisher-confirmed (community FAQ) |
| `C13a-freeze-then-flip-three-to-same-player` | If one player is assigned a Freeze then a Flip Three, they are frozen and the Flip Three is discarded. | Community Case 13(a) | Publisher-confirmed (community FAQ) |
| `C13b-two-flip-threes-to-same-player` | One player assigned two Flip Threes resolves them one after the other. | Community Case 13(b) | Publisher-confirmed (community FAQ) |
| `C13c-second-flip-three-discarded-after-bust` | If the first Flip Three busts the player, the second one is discarded. | Community Case 13(b) | Publisher-confirmed (community FAQ) |
| `C19-held-second-chance-used-during-flip-three` | A Second Chance held before the Flip Three can save a bust during it. | Rulebook p.7; Community Case 19 | Publisher-confirmed (community FAQ) |
| `C20a-extra-second-chance-during-flip-three-given` | A second Second Chance drawn during Flip Three counts as one of the three and must be given away at once. | Community Case 20 | Publisher-confirmed (community FAQ) |
| `C20b-extra-second-chance-discarded-when-alone` | If the Flip Three player is the only active player, the extra Second Chance is discarded. | Community Case 20 | Publisher-confirmed (community FAQ) |
| `C21-second-chance-drawn-during-flip-three-used` | A Second Chance drawn during Flip Three is kept and can save a later bust in the same Flip Three. | Rulebook p.7; Community Case 21 | Publisher-confirmed (community FAQ) |

## Where the app has to interpret the rules

- **Set-aside cards from a nested Flip Three:** when a Flip Three that came from a set-aside card produces its own set-aside cards, those new cards are assigned and resolved *before* any older set-aside cards still waiting. Case 13 covers only one level of set-aside cards; resolving the newest first finishes each Flip Three completely before moving on.
- **Free-form scorekeeping:** the app doesn't enforce whose turn it is, only which entries are legal. It suggests the next player, and after a Flip Three that suggestion follows Case 16.
- **Out of cards:** if the deck and discard pile are both empty, every card is in front of a player. The rules don't cover this, and the app refuses the draw with an explanation.

## Fixes made after these checks were introduced

Against the original engine, 14 of the 47 scenarios and the simulator failed, which exposed five deviations:

| Gap | Rule | Fix |
| --- | --- | --- |
| G1 | A tie at 200+ means everyone plays another round (Official FAQ; Case 6) | The game ends only with a single leader at 200+ |
| G2 | Set-aside cards are all assigned in the order drawn, then resolved in that order (Case 13) | An assignment queue; a card assigned to a player who is out by then is discarded |
| G3 | After a Flip Three, play resumes after the player originally dealt it (Case 16) | The engine remembers that player and suggests the next player after them |
| G4 | The Flip Three card is discarded once resolved; set-aside cards are discarded on a bust (Case 9) | Deck and discard counts updated immediately |
| G5 | Set-aside cards are discarded when a Flip 7 ends the round (Case 11) | A notice now says so |
