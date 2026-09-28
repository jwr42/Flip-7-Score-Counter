import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flip7.engine import Event, GameState  # noqa: E402


class Game:
    """Drives the engine the same way the scorekeeper does, by name."""

    def __init__(self, *names):
        self.ids = {name: i + 1 for i, name in enumerate(names)}
        self.state = GameState(list((i, n) for n, i in self.ids.items()))
        self.seq = 0
        self.start()

    def _apply(self, type_, **fields):
        self.seq += 1
        self.state.apply(Event(self.seq, type_, **fields))
        return self.state.log[-1]

    def start(self):
        return self._apply("start_round")

    def draw(self, who, card, on=None):
        return self._apply("draw", player_id=self.ids[who], card=str(card),
                           target_id=self.ids[on] if on else None)

    def stay(self, who):
        return self._apply("stay", player_id=self.ids[who])

    def give(self, to):
        return self._apply("give_second_chance", target_id=self.ids[to])

    def assign(self, to):
        return self._apply("resolve_action", target_id=self.ids[to])

    def hand(self, who):
        return self.state.round.hands[self.ids[who]]

    def total(self, who):
        return self.state.totals[self.ids[who]]

    def score(self, who):
        return self.state.round.scores[self.ids[who]]


def notice_text(entry):
    return " ".join(n.text for n in entry.notices)


@pytest.fixture
def game():
    return Game("Ann", "Ben", "Cat")


PASSWORD = "correct horse"


def make_app(tmp_path, **config):
    from app import create_app
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"), **config})


def register(client, username, password=PASSWORD):
    return post(client, "/register", username=username, password=password)


def login(client, username, password=PASSWORD):
    return post(client, "/login", username=username, password=password)


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def client(app):
    """A scorekeeper who is registered and logged in as `tester`."""
    client = app.test_client()
    register(client, "tester")
    return client


@pytest.fixture
def other_client(app):
    """A second scorekeeper, `rival`, using the same app and database."""
    client = app.test_client()
    register(client, "rival")
    return client


def post(client, url, **data):
    return client.post(url, data=data, follow_redirects=True)


def player_ids(client, game_id):
    from flip7 import db
    with client.application.app_context():
        return {name: pid for pid, name in db.get_players(game_id)}
