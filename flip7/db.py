"""SQLite persistence. Only the scorekeeper's entries are stored; everything else is
derived by replaying them through the rules engine."""
import secrets
import sqlite3

from flask import current_app, g

from .engine import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'active',
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    number INTEGER,
    share_token TEXT
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

# Columns added to games when accounts arrived; databases made before that lack them.
GAME_COLUMNS_V1 = {
    "user_id": "INTEGER REFERENCES users(id) ON DELETE CASCADE",
    "number": "INTEGER",
    "share_token": "TEXT",
}


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


def new_token():
    return secrets.token_urlsafe(16)


def migrate(db):
    """Bring a database made before accounts existed up to the current schema. Its games
    get no owner until `flask claim-games` assigns them."""
    if db.execute("PRAGMA user_version").fetchone()[0] >= 1:
        return
    have = {row["name"] for row in db.execute("PRAGMA table_info(games)")}
    for name, decl in GAME_COLUMNS_V1.items():
        if name not in have:
            db.execute(f"ALTER TABLE games ADD COLUMN {name} {decl}")
    for (game_id,) in db.execute("SELECT id FROM games WHERE share_token IS NULL").fetchall():
        db.execute("UPDATE games SET share_token = ? WHERE id = ?", (new_token(), game_id))
    db.execute("UPDATE games SET number = id WHERE number IS NULL")
    db.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS games_share_token ON games(share_token);
        CREATE INDEX IF NOT EXISTS games_user ON games(user_id);
        PRAGMA user_version = 1;
    """)
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        migrate(db)


def create_user(username, password_hash):
    db = get_db()
    user_id = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, password_hash)).lastrowid
    db.commit()
    return user_id


def get_user(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_name(username):
    return get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def next_game_number(db, user_id):
    return db.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM games WHERE user_id = ?",
                      (user_id,)).fetchone()[0]


def create_game(user_id, names):
    """Store a new game for `user_id`. Its number counts up from that user's highest, so
    once a user has deleted all their games the next one is Game 1 again."""
    db = get_db()
    game_id = db.execute("INSERT INTO games (user_id, number, share_token) VALUES (?, ?, ?)",
                         (user_id, next_game_number(db, user_id), new_token())).lastrowid
    db.executemany("INSERT INTO players (game_id, seat, name) VALUES (?, ?, ?)",
                   [(game_id, seat, name) for seat, name in enumerate(names)])
    db.execute("INSERT INTO events (game_id, seq, type) VALUES (?, 1, 'start_round')", (game_id,))
    db.commit()
    return game_id


def list_games(user_id):
    return get_db().execute(
        "SELECT g.id, g.number, g.created_at, g.status, "
        "       (SELECT group_concat(name, ', ') FROM "
        "           (SELECT name FROM players WHERE game_id = g.id ORDER BY seat)) AS names "
        "FROM games g WHERE g.user_id = ? ORDER BY g.id DESC", (user_id,)
    ).fetchall()


def get_game(game_id, user_id):
    """The game, or None if it does not exist or belongs to someone else."""
    return get_db().execute("SELECT * FROM games WHERE id = ? AND user_id = ?",
                            (game_id, user_id)).fetchone()


def get_game_by_token(token):
    return get_db().execute("SELECT * FROM games WHERE share_token = ?", (token,)).fetchone()


def regenerate_share_token(game_id):
    db = get_db()
    db.execute("UPDATE games SET share_token = ? WHERE id = ?", (new_token(), game_id))
    db.commit()


def claim_unowned_games(user_id):
    """Give games made before accounts existed to `user_id`, numbered after their own."""
    db = get_db()
    rows = db.execute("SELECT id FROM games WHERE user_id IS NULL ORDER BY id").fetchall()
    number = next_game_number(db, user_id)
    for offset, row in enumerate(rows):
        db.execute("UPDATE games SET user_id = ?, number = ? WHERE id = ?",
                   (user_id, number + offset, row["id"]))
    db.commit()
    return len(rows)


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
    """Remove a game; its players and entries go with it (ON DELETE CASCADE)."""
    db = get_db()
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
