"""SQLite persistence. Only the scorekeeper's entries are stored; everything else is
derived by replaying them through the rules engine."""
import sqlite3

from flask import current_app, g

from .engine import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    player_id INTEGER,
    target_id INTEGER,
    card TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (game_id, seq)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        get_db().executescript(SCHEMA)


def create_game(names):
    db = get_db()
    game_id = db.execute("INSERT INTO games DEFAULT VALUES").lastrowid
    db.executemany("INSERT INTO players (game_id, seat, name) VALUES (?, ?, ?)",
                   [(game_id, seat, name) for seat, name in enumerate(names)])
    db.execute("INSERT INTO events (game_id, seq, type) VALUES (?, 1, 'start_round')", (game_id,))
    db.commit()
    return game_id


def list_games():
    return get_db().execute(
        "SELECT g.id, g.created_at, g.status, "
        "       (SELECT group_concat(name, ', ') FROM "
        "           (SELECT name FROM players WHERE game_id = g.id ORDER BY seat)) AS names "
        "FROM games g ORDER BY g.id DESC"
    ).fetchall()


def get_game(game_id):
    return get_db().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()


def get_players(game_id):
    rows = get_db().execute("SELECT id, name FROM players WHERE game_id = ? ORDER BY seat",
                            (game_id,)).fetchall()
    return [(row["id"], row["name"]) for row in rows]


def get_events(game_id):
    rows = get_db().execute(
        "SELECT seq, type, player_id, target_id, card FROM events WHERE game_id = ? ORDER BY seq",
        (game_id,)).fetchall()
    return [Event(**dict(row)) for row in rows]


def add_event(game_id, event, status):
    db = get_db()
    db.execute("INSERT INTO events (game_id, seq, type, player_id, target_id, card) "
               "VALUES (?, ?, ?, ?, ?, ?)",
               (game_id, event.seq, event.type, event.player_id, event.target_id, event.card))
    db.execute("UPDATE games SET status = ? WHERE id = ?", (status, game_id))
    db.commit()


def delete_last_event(game_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE game_id = ? AND seq = "
               "(SELECT MAX(seq) FROM events WHERE game_id = ?)", (game_id, game_id))
    db.execute("UPDATE games SET status = 'active' WHERE id = ?", (game_id,))
    db.commit()


def delete_game(game_id):
    """Remove a game; its players and entries go with it (ON DELETE CASCADE).

    IDs are never reused while other games exist, but once the last game is gone the
    ID counters are reset so the next game is Game 1 again.
    """
    db = get_db()
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    if db.execute("SELECT NOT EXISTS (SELECT 1 FROM games)").fetchone()[0]:
        db.execute("UPDATE sqlite_sequence SET seq = 0 "
                   "WHERE name IN ('games', 'players', 'events')")
    db.commit()
