"""Flip 7 score keeper: Flask routes. Run with `flask --app app run --debug`."""
import functools
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import click
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from flip7 import db
from flip7.cards import (ACTIONS, DECK_COMPOSITION, FLIP_THREE, FREEZE, MODIFIERS, NUMBERS,
                         WIN_SCORE, RuleViolation, label)
from flip7.chart import score_chart
from flip7.engine import STATUS_LABELS, Event, replay

MAX_PLAYERS = 18  # the rulebook recommends a second deck beyond 18 players
THEMES = ("auto", "light", "dark")
MAX_USERNAME = 40
MIN_PASSWORD = 8


def safe_next(target, default):
    """Only follow same-site paths, never `//host` or absolute URLs."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return default
    return target


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(**kwargs)
    return wrapped


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLIP7_SECRET_KEY", "flip7-dev"),
        DATABASE=os.environ.get("FLIP7_DATABASE",
                                os.path.join(app.instance_path, "flip7.sqlite")),
        # IANA zone for displayed times; None means the time zone of this machine.
        TIMEZONE=os.environ.get("FLIP7_TIMEZONE"),
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        ALLOW_REGISTRATION=True,
    )
    # Deployment settings (SECRET_KEY, TIMEZONE, SESSION_COOKIE_SECURE, ...) live in
    # instance/config.py, which is kept out of git.
    app.config.from_pyfile("config.py", silent=True)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    app.jinja_env.globals.update(label=label, STATUS_LABELS=STATUS_LABELS, WIN_SCORE=WIN_SCORE,
                                 NUMBERS=NUMBERS, MODIFIERS=MODIFIERS, ACTIONS=ACTIONS,
                                 DECK_COMPOSITION=DECK_COMPOSITION,
                                 TARGETED_ACTIONS=(FREEZE, FLIP_THREE))

    @app.template_filter("localtime")
    def localtime(utc_text):
        """Show a stored UTC timestamp (SQLite datetime('now')) in local time."""
        when = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        tz = ZoneInfo(app.config["TIMEZONE"]) if app.config["TIMEZONE"] else None
        return when.astimezone(tz).strftime("%-d %b %Y, %H:%M %Z")

    @app.context_processor
    def inject_theme():
        theme = request.cookies.get("theme", "auto")
        return {"theme": theme if theme in THEMES else "auto"}

    @app.before_request
    def load_user():
        user_id = session.get("user_id")
        g.user = db.get_user(user_id) if user_id is not None else None

    @app.before_request
    def reject_cross_site_posts():
        # Second line of defence against CSRF after the SameSite=Lax session cookie.
        # Compare hosts only: behind a proxy the scheme Flask sees may differ from the browser's.
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.host:
            abort(403)

    def log_in(user_id):
        session.clear()
        session.permanent = True
        session["user_id"] = user_id

    @app.cli.command("claim-games")
    @click.argument("username")
    def claim_games(username):
        """Give games made before accounts existed to USERNAME."""
        user = db.get_user_by_name(username)
        if user is None:
            raise click.ClickException(f"No user named {username!r}.")
        click.echo(f"Gave {db.claim_unowned_games(user['id'])} game(s) to {user['username']}.")

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if not app.config["ALLOW_REGISTRATION"]:
            abort(404)
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or len(username) > MAX_USERNAME:
                flash(f"Choose a username of 1 to {MAX_USERNAME} characters.", "error")
            elif len(password) < MIN_PASSWORD:
                flash(f"Use a password of at least {MIN_PASSWORD} characters.", "error")
            elif db.get_user_by_name(username) is not None:
                flash("That username is taken.", "error")
            else:
                log_in(db.create_user(username, generate_password_hash(password)))
                return redirect(url_for("index"))
        return render_template("register.html", min_password=MIN_PASSWORD,
                               max_username=MAX_USERNAME)

    @app.route("/login", methods=("GET", "POST"))
    def login():
        target = safe_next(request.values.get("next"), url_for("index"))
        if request.method == "POST":
            user = db.get_user_by_name(request.form.get("username", "").strip())
            if user and check_password_hash(user["password_hash"],
                                            request.form.get("password", "")):
                log_in(user["id"])
                return redirect(target)
            flash("Wrong username or password.", "error")
        return render_template("login.html", next=target)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.post("/theme")
    def set_theme():
        resp = redirect(safe_next(request.form.get("next"), url_for("index")))
        theme = request.form.get("theme")
        if theme in THEMES:
            resp.set_cookie("theme", theme, max_age=60 * 60 * 24 * 365, samesite="Lax")
        return resp

    def own_game(game_id):
        game = db.get_game(game_id, g.user["id"])
        if game is None:
            abort(404)   # someone else's game looks the same as a missing one
        return game

    def load_state(game_id):
        return replay(db.get_players(game_id), db.get_events(game_id))

    def submit(game_id, type_, **fields):
        own_game(game_id)
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

    @app.get("/favicon.ico")
    def favicon():
        # Browsers request /favicon.ico directly; serve the SVG icon linked in base.html.
        return send_from_directory(app.static_folder, "favicon.svg", mimetype="image/svg+xml")

    @app.get("/")
    @login_required
    def index():
        return render_template("index.html", games=db.list_games(g.user["id"]),
                               max_players=MAX_PLAYERS)

    @app.post("/games")
    @login_required
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
        return redirect(url_for("game", game_id=db.create_game(g.user["id"], names)))

    @app.get("/games/<int:game_id>")
    @login_required
    def game(game_id):
        row = own_game(game_id)
        state = load_state(game_id)
        if state.game_over:
            return redirect(url_for("summary", game_id=game_id))
        return render_template("game.html", game_id=game_id, game=row, state=state,
                               recent=list(reversed(state.notices))[:12])

    @app.post("/games/<int:game_id>/share-link")
    @login_required
    def new_share_link(game_id):
        own_game(game_id)
        db.regenerate_share_token(game_id)
        flash("Made a new watch link. The old one no longer works.", "info")
        return redirect(url_for("game", game_id=game_id))

    @app.post("/games/<int:game_id>/draw")
    @login_required
    def draw(game_id):
        return submit(game_id, "draw",
                      player_id=request.form.get("player_id", type=int),
                      target_id=request.form.get("target_id", type=int),
                      card=request.form.get("card"))

    @app.post("/games/<int:game_id>/stay")
    @login_required
    def stay(game_id):
        return submit(game_id, "stay", player_id=request.form.get("player_id", type=int))

    @app.post("/games/<int:game_id>/give-second-chance")
    @login_required
    def give_second_chance(game_id):
        return submit(game_id, "give_second_chance",
                      target_id=request.form.get("target_id", type=int))

    @app.post("/games/<int:game_id>/resolve-action")
    @login_required
    def resolve_action(game_id):
        return submit(game_id, "resolve_action", target_id=request.form.get("target_id", type=int))

    @app.post("/games/<int:game_id>/next-round")
    @login_required
    def next_round(game_id):
        return submit(game_id, "start_round")

    @app.post("/games/<int:game_id>/undo")
    @login_required
    def undo(game_id):
        own_game(game_id)
        state = load_state(game_id)
        if state.last_seq <= 1:
            flash("Nothing to undo.", "error")
        else:
            db.delete_last_event(game_id)
            flash(f"Undid: {state.log[-1].text}.", "info")
        return redirect(url_for("game", game_id=game_id))

    @app.post("/games/<int:game_id>/delete")
    @login_required
    def delete_game(game_id):
        row = own_game(game_id)
        names = ", ".join(name for _, name in db.get_players(game_id))
        db.delete_game(game_id)
        flash(f"Deleted Game {row['number']} ({names}).", "info")
        return redirect(url_for("index"))

    def render_summary(row, read_only):
        state = load_state(row["id"])
        series = state.cumulative_totals()
        standings = sorted(state.order, key=lambda pid: -state.totals[pid])
        return render_template("summary.html", game_id=row["id"], game=row, state=state,
                               standings=standings, series=series, read_only=read_only,
                               chart=score_chart(series, state.names))

    @app.get("/games/<int:game_id>/summary")
    @login_required
    def summary(game_id):
        return render_summary(own_game(game_id), read_only=False)

    def shared_game(token):
        row = db.get_game_by_token(token)
        if row is None:
            abort(404)
        return row

    @app.get("/watch/<token>")
    def watch(token):
        row = shared_game(token)
        state = load_state(row["id"])
        if state.game_over:
            return redirect(url_for("watch_summary", token=token))
        return render_template("watch.html", game=row, state=state, read_only=True,
                               recent=list(reversed(state.notices))[:12])

    @app.get("/watch/<token>/summary")
    def watch_summary(token):
        return render_summary(shared_game(token), read_only=True)

    return app
