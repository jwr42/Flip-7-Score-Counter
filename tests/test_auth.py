import sqlite3

from conftest import PASSWORD, add_user, logged_in, login, make_app, player_ids as ids, post


def share_token(client, game_id):
    from flip7 import db
    with client.application.app_context():
        return db.get_db().execute("SELECT share_token FROM games WHERE id = ?",
                                   (game_id,)).fetchone()[0]


def test_pages_require_login(app):
    anon = app.test_client()
    for method, url in [("get", "/"), ("post", "/games"), ("get", "/games/1"),
                        ("post", "/games/1/draw"), ("get", "/games/1/summary")]:
        resp = getattr(anon, method)(url)
        assert resp.status_code == 302 and resp.headers["Location"].startswith("/login"), url
    assert "next=/games/1" in anon.get("/games/1").headers["Location"]


def test_there_is_no_self_registration(app):
    anon = app.test_client()
    assert anon.get("/register").status_code == 404
    assert anon.post("/register", data={"username": "ann", "password": PASSWORD}) \
        .status_code == 404
    assert b"Ask the site's admin" in anon.get("/login").data


def test_login_logout_and_next(app):
    add_user(app, "ann")
    c = app.test_client()
    assert b"Wrong username or password" in login(c, "ann", "nope nope").data
    assert b"Wrong username or password" in login(c, "nobody").data
    resp = c.post("/login", data={"username": "ann", "password": PASSWORD, "next": "/games/7"})
    assert resp.headers["Location"] == "/games/7"
    c.post("/logout")
    assert c.get("/").status_code == 302
    resp = c.post("/login", data={"username": "ann", "password": PASSWORD,
                                  "next": "//evil.example"})
    assert resp.headers["Location"] == "/"


def test_users_only_see_and_change_their_own_games(client, other_client):
    post(client, "/games", names="Ann\nBen\nCat")
    p = ids(client, 1)
    for method, url in [("get", "/games/1"), ("get", "/games/1/summary"),
                        ("post", "/games/1/draw"), ("post", "/games/1/stay"),
                        ("post", "/games/1/undo"), ("post", "/games/1/next-round"),
                        ("post", "/games/1/share-link"), ("post", "/games/1/delete")]:
        assert getattr(other_client, method)(url, data={"player_id": p["Ann"], "card": "7"}) \
            .status_code == 404, url
    assert "Ann, Ben, Cat" not in other_client.get("/").get_data(as_text=True)
    assert client.get("/games/1").status_code == 200   # untouched by the attempts
    assert b"Nothing to undo" in post(client, "/games/1/undo").data


def test_each_user_numbers_their_games_from_1(client, other_client):
    post(client, "/games", names="Ann\nBen\nCat")
    post(other_client, "/games", names="Dee\nEli\nFay")
    assert "Game 1<" in client.get("/").get_data(as_text=True)
    page = other_client.get("/").get_data(as_text=True)
    assert "Game 1<" in page and "Game 2<" not in page


def test_watch_link_is_read_only_and_live(client, app):
    post(client, "/games", names="Ann\nBen\nCat")
    post(client, "/games/1/draw", player_id=ids(client, 1)["Ann"], card="9")
    token = share_token(client, 1)
    assert f"/watch/{token}" in client.get("/games/1").get_data(as_text=True)

    viewer = app.test_client()   # not logged in
    page = viewer.get(f"/watch/{token}").get_data(as_text=True)
    assert "Ann" in page and "Round 1" in page and 'http-equiv="refresh"' in page
    for action in ("/draw", "/stay", "/undo", "/delete", "/share-link"):
        assert action not in page
    summary = viewer.get(f"/watch/{token}/summary").get_data(as_text=True)
    assert "Draw log" in summary and "/undo" not in summary
    assert f'href="/watch/{token}"' in summary


def test_new_watch_link_revokes_the_old_one(client, app):
    post(client, "/games", names="Ann\nBen\nCat")
    old = share_token(client, 1)
    assert b"Made a new watch link" in post(client, "/games/1/share-link").data
    new = share_token(client, 1)
    viewer = app.test_client()
    assert new != old
    assert viewer.get(f"/watch/{old}").status_code == 404
    assert viewer.get(f"/watch/{new}").status_code == 200


def test_finished_game_watch_link_goes_to_summary(client, app):
    post(client, "/games", names="Ann\nBen\nCat")
    p = ids(client, 1)
    for rnd in range(3):
        for n in (12, 11, 10, 9, 8, 7, 6):
            post(client, "/games/1/draw", player_id=p["Ann"], card=str(n))
        if rnd < 2:
            post(client, "/games/1/next-round")
    token = share_token(client, 1)
    resp = app.test_client().get(f"/watch/{token}")
    assert resp.headers["Location"] == f"/watch/{token}/summary"
    page = app.test_client().get(f"/watch/{token}/summary").get_data(as_text=True)
    assert "Ann wins!" in page and "Undo" not in page and "refresh" not in page


def test_cross_site_posts_are_rejected(client):
    resp = client.post("/games", data={"names": "Ann\nBen\nCat"},
                       headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    resp = client.post("/games", data={"names": "Ann\nBen\nCat"},
                       headers={"Origin": "http://localhost"})
    assert resp.status_code == 302


def test_old_database_is_migrated_and_games_can_be_claimed(tmp_path):
    path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE games (id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT NOT NULL DEFAULT 'active');
        CREATE TABLE players (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER NOT NULL
            REFERENCES games(id) ON DELETE CASCADE, seat INTEGER NOT NULL, name TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER NOT NULL
            REFERENCES games(id) ON DELETE CASCADE, seq INTEGER NOT NULL, type TEXT NOT NULL,
            player_id INTEGER, target_id INTEGER, card TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (game_id, seq));
        INSERT INTO games DEFAULT VALUES;
        INSERT INTO players (game_id, seat, name) VALUES (1, 0, 'Old'), (1, 1, 'Timer');
        INSERT INTO events (game_id, seq, type) VALUES (1, 1, 'start_round');
    """)
    conn.close()

    app = make_app(tmp_path)
    make_app(tmp_path)   # a second start must not migrate again
    c = logged_in(app, "ann")
    assert "Old, Timer" not in c.get("/").get_data(as_text=True)   # unowned until claimed

    result = app.test_cli_runner().invoke(args=["claim-games", "ann"])
    assert "Gave 1 game(s) to ann." in result.output
    page = c.get("/").get_data(as_text=True)
    assert "Old, Timer" in page and "Game 1<" in page
    assert c.get("/games/1").status_code == 200
    assert app.test_cli_runner().invoke(args=["claim-games", "zed"]).exit_code != 0
