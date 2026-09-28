# Flip 7 Score Keeper

A minimalist Flask web app (Python, HTML and CSS only) for keeping score in the card game **Flip 7**. The scorekeeper logs every card as it is dealt. The app applies the rules from the Flip 7 rulebook (Ruleset Edition 3.1) and explains each one as it happens: busts, Second Chance, Freeze, Flip Three, the Flip 7 bonus, modifiers, round end and the 200-point finish.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/flask --app app run --debug
```

Open http://127.0.0.1:5000 and create an account. Games are stored in `instance/flip7.sqlite`. Set `FLIP7_DATABASE` to use a different file.

## Accounts and watch links

Each scorekeeper registers with a username and password. A game belongs to the account that created it; other accounts cannot see or change it. Games are numbered per account, so everyone's first game is Game 1.

Every game has a **watch link** (at the bottom of the game page). Anyone with the link can follow the board and summary live, without logging in. The page refreshes every 10 seconds, and it has no controls. **New link** makes a fresh link and stops the old one working.

Games created before accounts existed have no owner. Give them to an account with:

```bash
.venv/bin/flask --app app claim-games <username>
```

To stop new sign-ups, set `ALLOW_REGISTRATION = False` in `instance/config.py`.

## Configuration

Settings are read from `instance/config.py` if it exists. The `instance/` folder is not in git. Environment variables cover the local defaults.

| Setting | Env var | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | `FLIP7_SECRET_KEY` | `flip7-dev` | Signs the login cookie. **Always set a random value when deployed.** |
| `TIMEZONE` | `FLIP7_TIMEZONE` | the machine's zone | IANA zone for displayed times, e.g. `Europe/London` |
| `DATABASE` | `FLIP7_DATABASE` | `instance/flip7.sqlite` | SQLite file |
| `SESSION_COOKIE_SECURE` | | `False` | Set `True` when served over HTTPS |
| `ALLOW_REGISTRATION` | | `True` | Whether `/register` is open |

## Deploy to PythonAnywhere

1. In a PythonAnywhere Bash console, clone the repo and make a virtualenv:
   ```bash
   git clone <repo-url> ~/flip7
   mkvirtualenv --python=python3.13 flip7
   pip install -r ~/flip7/requirements.txt
   ```
2. Create `~/flip7/instance/config.py`. PythonAnywhere servers run in UTC, so set your time zone:
   ```python
   SECRET_KEY = "..."   # python -c "import secrets; print(secrets.token_hex(32))"
   TIMEZONE = "Europe/London"
   SESSION_COOKIE_SECURE = True
   ```
3. On the **Web** tab, choose **Add a new web app → Manual configuration**. Pick the same Python version and set **Virtualenv** to `/home/<you>/.virtualenvs/flip7`.
4. Replace the contents of the WSGI configuration file with:
   ```python
   import sys
   sys.path.insert(0, "/home/<you>/flip7")
   from wsgi import application  # noqa
   ```
5. Under **Static files**, map URL `/static/` to directory `/home/<you>/flip7/static`.
6. Turn on **Force HTTPS**. Leave **Password protection** off, because the app has its own logins and watch links must work without a password.
7. Click **Reload**. To update later, run `git pull` in `~/flip7` and click **Reload** again.

The database is created in `~/flip7/instance/` on first start. `git pull` leaves it alone.

## Test

```bash
.venv/bin/pytest -q
```

The tests in `tests/test_scoring.py` use the rulebook's worked examples (pp. 5, 8, 10–11). The tests in `tests/test_engine.py` cover every rule the engine enforces. The tests in `tests/test_auth.py` cover logins, game ownership, watch links and upgrading an older database.

## Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Flask routes (Post/Redirect/Get forms), accounts and watch links |
| `wsgi.py` | WSGI entry point for PythonAnywhere and other hosts |
| `flip7/cards.py` | The 94-card deck and card labels |
| `flip7/scoring.py` | Score calculation: numbers, then ×2, then +N, then +15 for Flip 7 |
| `flip7/deck.py` | Deck, table and discard tracking; blocks impossible cards; reshuffles |
| `flip7/engine.py` | Rules engine that replays the stored entries; also provides Undo |
| `flip7/chart.py` | Server-rendered SVG chart of running totals |
| `flip7/db.py` | SQLite storage of accounts, games and scorekeeper entries |
