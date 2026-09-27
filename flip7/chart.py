"""Server-rendered SVG line chart of each player's running total by round (no JavaScript).

Colors come from CSS classes (.series-1 ... .series-8) defined in static/style.css so the
chart follows light and dark mode. Hovering a point shows its value via an SVG <title>.
"""
from html import escape
from math import ceil

from .cards import WIN_SCORE

WIDTH, HEIGHT = 720, 340
LEFT, RIGHT, TOP, BOTTOM = 44, 96, 16, 36
MAX_SERIES = 8


def _nice_max(value):
    return max(WIN_SCORE, int(ceil(value / 50.0)) * 50)


def score_chart(series, names):
    """series: {player_id: [0, total after round 1, ...]}; names: {player_id: name}."""
    rounds = max((len(v) for v in series.values()), default=1) - 1
    y_max = _nice_max(max((max(v) for v in series.values()), default=0))
    plot_w = WIDTH - LEFT - RIGHT
    plot_h = HEIGHT - TOP - BOTTOM

    def x(i):
        return LEFT + (plot_w * i / rounds if rounds else plot_w / 2)

    def y(v):
        return TOP + plot_h - plot_h * v / y_max

    parts = [f'<svg class="chart" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
             f'aria-labelledby="chart-title">',
             '<title id="chart-title">Running score total after each round</title>']

    step = 50 if y_max <= 300 else 100
    for v in range(0, y_max + 1, step):
        parts.append(f'<line class="grid" x1="{LEFT}" x2="{WIDTH - RIGHT}" '
                     f'y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        parts.append(f'<text class="tick" x="{LEFT - 8}" y="{y(v):.1f}" text-anchor="end" '
                     f'dominant-baseline="middle">{v}</text>')
    parts.append(f'<line class="axis" x1="{LEFT}" x2="{WIDTH - RIGHT}" '
                 f'y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    for i in range(rounds + 1):
        parts.append(f'<text class="tick" x="{x(i):.1f}" y="{HEIGHT - BOTTOM + 18}" '
                     f'text-anchor="middle">{"Start" if i == 0 else f"R{i}"}</text>')
    parts.append(f'<line class="target" x1="{LEFT}" x2="{WIDTH - RIGHT}" '
                 f'y1="{y(WIN_SCORE):.1f}" y2="{y(WIN_SCORE):.1f}"/>')
    parts.append(f'<text class="target-label" x="{LEFT + 6}" y="{y(WIN_SCORE) - 6:.1f}">'
                 f'{WIN_SCORE} to win</text>')

    # Direct labels (<= 4 players) sit at the line ends, nudged apart so they never overlap.
    label_y = {}
    if len(series) <= 4 and rounds:
        placed = sorted(series, key=lambda pid: y(series[pid][-1]))
        prev = None
        for pid in placed:
            ly = y(series[pid][-1])
            if prev is not None and ly - prev < 14:
                ly = prev + 14
            label_y[pid] = prev = ly
    for idx, (pid, values) in enumerate(series.items()):
        cls = f"series-{idx % MAX_SERIES + 1}"
        name = escape(names[pid])
        points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
        parts.append(f'<g class="{cls}">')
        if len(values) > 1:
            parts.append(f'<polyline points="{points}"/>')
        for i, v in enumerate(values):
            when = "Start" if i == 0 else f"After round {i}"
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4">'
                         f'<title>{name}: {v} ({when})</title></circle>')
        if pid in label_y:
            parts.append(f'<text class="direct-label" x="{x(rounds) + 8:.1f}" '
                         f'y="{label_y[pid]:.1f}" dominant-baseline="middle">{name}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts)
