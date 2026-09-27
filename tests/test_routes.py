from conftest import player_ids as ids, post


def test_full_game_flow(client):
    resp = post(client, "/games", names="Ann\nBen\nCat")
    assert b"Round 1" in resp.data
    p = ids(client, 1)

    post(client, "/games/1/draw", player_id=p["Ann"], card="7")
    resp = post(client, "/games/1/draw", player_id=p["Ann"], card="7")
    assert b"BUST! Ann drew a second 7" in resp.data

    resp = post(client, "/games/1/draw", player_id=p["Ben"], card="freeze")
    assert b"Choose which active player the Freeze is played on" in resp.data

    resp = post(client, "/games/1/draw", player_id=p["Ben"], card="12")
    resp = post(client, "/games/1/stay", player_id=p["Ben"])
    assert b"Ben stays and banks 12 points" in resp.data

    resp = post(client, "/games/1/undo")
    assert b"Undid: Ben stayed" in resp.data
    resp = post(client, "/games/1/stay", player_id=p["Ben"])

    post(client, "/games/1/draw", player_id=p["Cat"], card="+4")
    resp = post(client, "/games/1/stay", player_id=p["Cat"])
    assert b"Round 1 results" in resp.data
    resp = post(client, "/games/1/next-round")
    assert b"Round 2" in resp.data

    resp = client.get("/games/1/summary")
    assert resp.status_code == 200
    assert b"<svg" in resp.data and b"Draw log" in resp.data
    assert b"BUST! Ann drew a second 7" in resp.data


def test_game_over_redirects_to_summary(client):
    post(client, "/games", names="Ann\nBen\nCat")
    p = ids(client, 1)
    for rnd in range(3):
        for n in (12, 11, 10, 9, 8, 7, 6):
            resp = post(client, "/games/1/draw", player_id=p["Ann"], card=str(n))
        if rnd < 2:
            post(client, "/games/1/next-round")
    assert b"Ann wins!" in resp.data
    assert client.get("/games/1").status_code == 302


def test_impossible_card_is_blocked(client):
    post(client, "/games", names="Ann\nBen\nCat")
    p = ids(client, 1)
    post(client, "/games/1/draw", player_id=p["Ann"], card="1")
    resp = post(client, "/games/1/draw", player_id=p["Ben"], card="1")
    assert b"There are no 1 cards left in the deck" in resp.data


def test_rejects_bad_player_lists(client):
    assert b"unique" in post(client, "/games", names="Ann\nann").data
    assert b"at least one" in post(client, "/games", names="  ").data


def test_theme_switch_sets_cookie_and_html_attribute(client):
    assert b"data-theme" not in client.get("/").data          # auto: follow the device
    resp = client.post("/theme", data={"theme": "light", "next": "/?"})
    assert resp.status_code == 302 and resp.headers["Location"].startswith("/")
    page = client.get("/").data
    assert b'<html lang="en" data-theme="light">' in page
    assert b'value="light" aria-pressed="true"' in page
    client.post("/theme", data={"theme": "dark", "next": "/"})
    assert b'data-theme="dark"' in client.get("/").data


def test_theme_switch_rejects_offsite_redirects_and_bad_values(client):
    resp = client.post("/theme", data={"theme": "neon", "next": "//evil.example"})
    assert resp.headers["Location"] == "/"
    assert b"data-theme" not in client.get("/").data
