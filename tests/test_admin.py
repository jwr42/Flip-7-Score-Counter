import sqlite3

from conftest import PASSWORD, add_user, logged_in, login, make_app, player_ids as ids, post


def user_id(app, username):
    from flip7 import db
    with app.app_context():
        return db.get_user_by_name(username)["id"]


def count(app, table):
    from flip7 import db
    with app.app_context():
        return db.get_db().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def share_token(app, game_id):
    from flip7 import db
    with app.app_context():
        return db.get_db().execute("SELECT share_token FROM games WHERE id = ?",
                                   (game_id,)).fetchone()[0]


def test_admin_login_opens_the_account_manager(app):
    add_user(app, "boss", is_admin=True)
    c = app.test_client()
    resp = c.post("/login", data={"username": "boss", "password": PASSWORD, "next": "/games/1"})
    assert resp.headers["Location"] == "/admin"
    page = c.get("/admin").get_data(as_text=True)
    assert "Add user" in page and 'class="brand" href="/admin"' in page
    for url in ("/", "/games/1", "/games/1/summary"):
        assert c.get(url).headers["Location"] == "/admin", url
    assert c.post("/games", data={"names": "Ann\nBen\nCat"}).headers["Location"] == "/admin"


def test_account_manager_is_hidden_from_everyone_else(client, app):
    add_user(app, "boss", is_admin=True)
    boss = user_id(app, "boss")
    tester = user_id(app, "tester")
    anon = app.test_client()
    assert anon.get("/admin").headers["Location"].startswith("/login")
    for method, url in [("get", "/admin"), ("post", "/admin/users"),
                        ("get", f"/admin/users/{tester}"), ("post", f"/admin/users/{tester}"),
                        ("post", f"/admin/users/{tester}/delete")]:
        assert getattr(client, method)(url, data={"username": "x", "password": PASSWORD}) \
            .status_code == 404, url
    assert client.get("/").status_code == 200   # tester was not deleted

    admin = app.test_client()
    login(admin, "boss")
    assert "boss" not in admin.get("/admin").get_data(as_text=True).split("<h2>Users")[1]
    assert admin.get(f"/admin/users/{boss}").status_code == 404     # no editing the admin
    assert admin.post(f"/admin/users/{boss}/delete").status_code == 404
    assert admin.get("/admin/users/999").status_code == 404


def test_admin_creates_users(app):
    admin = logged_in(app, "boss", is_admin=True)
    assert b"at least 8 characters" in post(admin, "/admin/users", username="ann",
                                            password="short").data
    assert b"1 to 40 characters" in post(admin, "/admin/users", username="  ",
                                         password=PASSWORD).data
    assert b"Added Ann." in post(admin, "/admin/users", username=" Ann ", password=PASSWORD).data
    assert b"That username is taken" in post(admin, "/admin/users", username="ANN",
                                             password=PASSWORD).data
    assert b"That username is taken" in post(admin, "/admin/users", username="boss",
                                             password=PASSWORD).data
    page = admin.get("/admin").get_data(as_text=True)
    assert "Ann</a>" in page and "0 games" in page

    c = app.test_client()
    assert b"New game" in login(c, "ann").data


def test_admin_updates_users(app):
    admin = logged_in(app, "boss", is_admin=True)
    add_user(app, "ann")
    add_user(app, "ben")
    ann = user_id(app, "ann")
    assert b'value="ann"' in admin.get(f"/admin/users/{ann}").data

    assert b"That username is taken" in post(admin, f"/admin/users/{ann}", username="BEN",
                                             password="").data
    assert b"at least 8 characters" in post(admin, f"/admin/users/{ann}", username="ann",
                                            password="short").data
    resp = post(admin, f"/admin/users/{ann}", username="Annie", password="")
    assert b"Saved Annie." in resp.data
    assert b"New game" in login(app.test_client(), "annie").data   # blank kept the password
    assert b"Wrong username" in login(app.test_client(), "ann").data

    resp = post(admin, f"/admin/users/{ann}", username="Annie", password="new password")
    assert b"Saved Annie and their new password." in resp.data
    assert b"Wrong username" in login(app.test_client(), "annie").data
    assert b"New game" in login(app.test_client(), "annie", "new password").data
    assert b"Saved" in post(admin, f"/admin/users/{ann}", username="annie", password="").data


def test_deleting_a_user_deletes_their_games(app):
    admin = logged_in(app, "boss", is_admin=True)
    ann = logged_in(app, "ann")
    ben = logged_in(app, "ben")
    for names in ("Ann\nBen\nCat", "Dee\nEli\nFay"):
        post(ann, "/games", names=names)
    post(ben, "/games", names="Gil\nHal\nIvy")
    post(ann, "/games/1/draw", player_id=ids(ann, 1)["Ann"], card="9")
    token = share_token(app, 1)
    assert "2 games" in admin.get("/admin").get_data(as_text=True)

    resp = post(admin, f"/admin/users/{user_id(app, 'ann')}/delete")
    assert b"Deleted ann and 2 games." in resp.data
    assert "ann</a>" not in resp.get_data(as_text=True)
    assert count(app, "games") == 1 and count(app, "players") == 3 and count(app, "events") == 1
    assert app.test_client().get(f"/watch/{token}").status_code == 404
    assert ann.get("/").headers["Location"].startswith("/login")   # logged out
    assert b"Wrong username" in login(app.test_client(), "ann").data
    assert "Gil, Hal, Ivy" in ben.get("/").get_data(as_text=True)


def test_create_admin_command(app):
    run = app.test_cli_runner().invoke
    result = run(args=["create-admin", "boss"], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert "Created admin boss." in result.output
    c = app.test_client()
    assert c.post("/login", data={"username": "boss", "password": PASSWORD}) \
        .headers["Location"] == "/admin"

    result = run(args=["create-admin", "boss", "--password", "brand new pw"])
    assert "Reset the password for admin boss." in result.output
    assert b"Add user" in login(app.test_client(), "boss", "brand new pw").data

    add_user(app, "ann")
    result = run(args=["create-admin", "ann", "--password", PASSWORD])
    assert result.exit_code != 0 and "scorekeeper account" in result.output
    result = run(args=["create-admin", "zed", "--password", "short"])
    assert result.exit_code != 0 and "at least 8 characters" in result.output


def test_accounts_database_is_migrated_to_admins(tmp_path):
    path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO users (username, password_hash) VALUES ('old', 'x');
        PRAGMA user_version = 1;
    """)
    conn.close()

    app = make_app(tmp_path)
    make_app(tmp_path)   # a second start must not migrate again
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert conn.execute("SELECT is_admin FROM users WHERE username = 'old'").fetchone()[0] == 0
    conn.close()
    assert "old</a>" in logged_in(app, "boss", is_admin=True).get("/admin").get_data(as_text=True)
