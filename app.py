"""Flip 7 score keeper: Flask routes. Run with `flask --app app run --debug`."""
import os

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from flip7 import db
from flip7.cards import (ACTIONS, DECK_COMPOSITION, FLIP_THREE, FREEZE, MODIFIERS, NUMBERS,
                         WIN_SCORE, RuleViolation, label)
from flip7.chart import score_chart
from flip7.engine import STATUS_LABELS, Event, replay

MAX_PLAYERS = 18  # the rulebook recommends a second deck beyond 18 players
THEMES = ("auto", "light", "dark")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLIP7_SECRET_KEY", "flip7-dev"),
        DATABASE=os.path.join(app.instance_path, "flip7.sqlite"),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    app.jinja_env.globals.update(label=label, STATUS_LABELS=STATUS_LABELS, WIN_SCORE=WIN_SCORE,
                                 NUMBERS=NUMBERS, MODIFIERS=MODIFIERS, ACTIONS=ACTIONS,
                                 DECK_COMPOSITION=DECK_COMPOSITION,
                                 TARGETED_ACTIONS=(FREEZE, FLIP_THREE))

    @app.context_processor
    def inject_theme():
        theme = request.cookies.get("theme", "auto")
        return {"theme": theme if theme in THEMES else "auto"}

    @app.post("/theme")
    def set_theme():
        target = request.form.get("next", "")
        if not target.startswith("/") or target.startswith("//"):
            target = url_for("index")
        resp = redirect(target)
        theme = request.form.get("theme")
        if theme in THEMES:
            resp.set_cookie("theme", theme, max_age=60 * 60 * 24 * 365, samesite="Lax")
        return resp

    def load_state(game_id):
        if db.get_game(game_id) is None:
            abort(404)
        return replay(db.get_players(game_id), db.get_events(game_id))

    def submit(game_id, type_, **fields):
        state = load_state(game_id)
        event = Event(seq=state.last_seq + 1, type=type_, **fields)
        try:
            state.apply(event)
        except RuleViolation as exc:
            flash(str(exc), "error")
        else:
            db.add_event(game_id, event, "finished" if state.game_over else "active")
            if state.game_over:
                return redirect(url_for("summary", game_id=game_id))
        return redirect(url_for("game", game_id=game_id))

    @app.get("/")
    def index():
        return render_template("index.html", games=db.list_games(), max_players=MAX_PLAYERS)

    @app.post("/games")
    def create_game():
        names = [n.strip() for n in request.form.get("names", "").splitlines() if n.strip()]
        if not names:
            flash("Enter at least one player name.", "error")
            return redirect(url_for("index"))
        if len(names) > MAX_PLAYERS:
            flash(f"At most {MAX_PLAYERS} players: the rulebook recommends a second deck "
                  f"beyond that.", "error")
            return redirect(url_for("index"))
        if len({n.lower() for n in names}) != len(names):
            flash("Player names must be unique.", "error")
            return redirect(url_for("index"))
        return redirect(url_for("game", game_id=db.create_game(names)))

    @app.get("/games/<int:game_id>")
    def game(game_id):
        state = load_state(game_id)
        if state.game_over:
            return redirect(url_for("summary", game_id=game_id))
        return render_template("game.html", game_id=game_id, state=state,
                               recent=list(reversed(state.notices))[:12])

    @app.post("/games/<int:game_id>/draw")
    def draw(game_id):
        return submit(game_id, "draw",
                      player_id=request.form.get("player_id", type=int),
                      target_id=request.form.get("target_id", type=int),
                      card=request.form.get("card"))

    @app.post("/games/<int:game_id>/stay")
    def stay(game_id):
        return submit(game_id, "stay", player_id=request.form.get("player_id", type=int))

    @app.post("/games/<int:game_id>/give-second-chance")
    def give_second_chance(game_id):
        return submit(game_id, "give_second_chance",
                      target_id=request.form.get("target_id", type=int))

    @app.post("/games/<int:game_id>/resolve-action")
    def resolve_action(game_id):
        return submit(game_id, "resolve_action", target_id=request.form.get("target_id", type=int))

    @app.post("/games/<int:game_id>/next-round")
    def next_round(game_id):
        return submit(game_id, "start_round")

    @app.post("/games/<int:game_id>/undo")
    def undo(game_id):
        state = load_state(game_id)
        if state.last_seq <= 1:
            flash("Nothing to undo.", "error")
        else:
            db.delete_last_event(game_id)
            flash(f"Undid: {state.log[-1].text}.", "info")
        return redirect(url_for("game", game_id=game_id))

    @app.get("/games/<int:game_id>/summary")
    def summary(game_id):
        state = load_state(game_id)
        series = state.cumulative_totals()
        standings = sorted(state.order, key=lambda pid: -state.totals[pid])
        return render_template("summary.html", game_id=game_id, state=state,
                               standings=standings, series=series,
                               chart=score_chart(series, state.names))

    return app
