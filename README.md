# Flip 7 Score Keeper

A minimalist Flask web app (Python, HTML and CSS only) for keeping score in the card game **Flip 7**. The scorekeeper logs every card as it is dealt. The app applies the rules from the Flip 7 rulebook (Ruleset Edition 3.1) and explains each one as it happens: busts, Second Chance, Freeze, Flip Three, the Flip 7 bonus, modifiers, round end and the 200-point finish.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app app run --debug
```

Open http://127.0.0.1:5000. Games are stored in `instance/flip7.sqlite`.

## Test

```bash
.venv/bin/pytest -q
```

The tests in `tests/test_scoring.py` use the rulebook's worked examples (pp. 5, 8, 10–11). The tests in `tests/test_engine.py` cover every rule the engine enforces.

## Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Flask routes (Post/Redirect/Get forms) |
| `flip7/cards.py` | The 94-card deck and card labels |
| `flip7/scoring.py` | Score calculation: numbers, then ×2, then +N, then +15 for Flip 7 |
| `flip7/deck.py` | Deck, table and discard tracking; blocks impossible cards; reshuffles |
| `flip7/engine.py` | Rules engine that replays the stored entries; also provides Undo |
| `flip7/chart.py` | Server-rendered SVG chart of running totals |
| `flip7/db.py` | SQLite storage of scorekeeper entries |
