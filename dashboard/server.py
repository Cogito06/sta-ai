"""Local web dashboard for the runs, lessons and guides (read-only).

python -m dashboard.server [--port 8780]  then open http://localhost:8780

Reads runs/<run>/run.jsonl and raw/*.json, runs/lessons.json, guides/*.md, runs/eval1/*.patch and
docs/eval-baseline.md. Never writes anything and never talks to the game.
"""
import argparse
import http.server
import json
import mimetypes
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
STATIC = Path(__file__).resolve().parent / "static"

# Per-run caches, keyed by run id and invalidated when run.jsonl changes.
_summary_cache = {}
_detail_cache = {}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def game_state(message):
    return (message or {}).get("game_state") or {}


def read_log(run_dir):
    entries = []
    try:
        lines = (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries
    for line in lines:
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries


def raw_files(run_dir):
    return sorted((run_dir / "raw").glob("*.json"))


def run_dirs():
    return sorted((d for d in RUNS.iterdir() if (d / "run.jsonl").exists()), reverse=True)


def log_mtime(run_dir):
    return (run_dir / "run.jsonl").stat().st_mtime


def summarize(run_dir):
    key = run_dir.name
    mtime = log_mtime(run_dir)
    cached = _summary_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    log = read_log(run_dir)
    raws = raw_files(run_dir)
    first = game_state(read_json(raws[0])) if raws else {}
    last = game_state(read_json(raws[-1])) if raws else {}
    seed = run_dir.name.split("_seed-", 1)[-1]
    start = next((e["input"] for e in log if str(e.get("input", "")).startswith("start_run")), "")
    # "start_run EVAL3 A5" names the seed; "start_run A5" (random seed) does not.
    named_seed = next((w for w in start.split()[1:] if not re.fullmatch(r"A\d+", w)), "")
    over = next((e for e in reversed(log) if e.get("screen") == "GAME_OVER"), None)
    result = "进行中"
    score = None
    if last.get("screen_type") == "GAME_OVER":
        state = last.get("screen_state") or {}
        result = "胜利" if state.get("victory") else "阵亡"
        score = state.get("score")
    elif over:
        result = "阵亡"
    summary = {
        "id": run_dir.name,
        "seed": named_seed or seed,
        "ascension": first.get("ascension_level", last.get("ascension_level")),
        "class": first.get("class") or last.get("class"),
        "started": log[0]["t"] if log else None,
        "ended": log[-1]["t"] if log else None,
        "steps": len(log),
        "floor": max((e.get("floor") or 0 for e in log), default=0),
        "act": last.get("act"),
        "hp": last.get("current_hp"),
        "max_hp": last.get("max_hp"),
        "gold": last.get("gold"),
        "result": result,
        "score": score,
        "memory": next((e.get("memory") for e in log if "memory" in e), None),
        "boss": last.get("act_boss"),
        "resumed": any(str(e.get("input", "")).startswith("continue_run") for e in log),
    }
    _summary_cache[key] = (mtime, summary)
    return summary


def chosen_node(gs, command):
    """The node a map command picks: "choose x3" names the column, "choose 1" the index in next_nodes."""
    nodes = (gs.get("screen_state") or {}).get("next_nodes") or []
    m = re.fullmatch(r"choose\s+x(\d+)", command)
    if m:
        return next(((n["x"], n["y"]) for n in nodes if n["x"] == int(m.group(1))), None)
    m = re.fullmatch(r"choose\s+(\d+)", command)
    if m and int(m.group(1)) < len(nodes):
        n = nodes[int(m.group(1))]
        return n["x"], n["y"]
    return None


def visited_path(log, states, maps):
    """Map nodes walked per act: current_node on MAP screens, the node each map command picked,
    and the gaps between them (rooms the bridge walked through by itself) filled along the map."""
    known = {}
    floors = {}
    for i, gs in enumerate(states):
        act, floor = gs.get("act"), gs.get("floor")
        if act is None:
            continue
        if floor:
            floors.setdefault(act, set()).add(floor)
        if gs.get("screen_type") == "MAP":
            node = (gs.get("screen_state") or {}).get("current_node")
            if node and node.get("y", -1) >= 0:
                known.setdefault(act, set()).add((node["x"], node["y"]))
            # The next command sent from this screen (inspect/note entries in between change nothing).
            command = next((str(e["input"]) for e in log[i + 1:] if "input" in e), "").split(";")[0].strip()
            picked = chosen_node(gs, command)
            if picked:
                known.setdefault(act, set()).add(picked)
    out = {}
    for act, nodes in known.items():
        children = {(n["x"], n["y"]): [(c["x"], c["y"]) for c in n.get("children", [])] for n in maps.get(act, [])}
        path = sorted(nodes, key=lambda n: n[1])
        filled = path[:1]
        for nxt in path[1:]:
            filled += walk_between(filled[-1], nxt, children)
        # After the last known node, follow single exits for as many floors as were visited in this act.
        top = max((f for f in floors.get(act, ())), default=0) - (1 + 17 * (act - 1))
        while filled and filled[-1][1] < top:
            exits = children.get(filled[-1], [])
            if len(exits) != 1 or exits[0][1] > top:
                break
            filled.append(exits[0])
        out[act] = [{"x": x, "y": y} for x, y in filled]
    return out


def walk_between(start, goal, children):
    """Nodes after start up to goal along the map (any path when several exist); [goal] if none."""
    frontier = [[start]]
    while frontier:
        route = frontier.pop(0)
        if route[-1] == goal:
            return route[1:]
        for nxt in children.get(route[-1], []):
            if nxt[1] <= goal[1]:
                frontier.append(route + [nxt])
    return [goal]


def slim_state(gs):
    """What the replay view needs from one raw state (drops piles' long uuids and the map)."""
    combat = gs.get("combat_state") or {}

    def cards(pile):
        return [{"id": c.get("id"), "name": c.get("name"), "cost": c.get("cost"), "type": c.get("type"),
                 "upgrades": c.get("upgrades", 0), "ethereal": c.get("ethereal"), "exhausts": c.get("exhausts"),
                 "playable": c.get("is_playable")} for c in pile or []]

    out = {k: gs.get(k) for k in ("floor", "act", "current_hp", "max_hp", "gold", "screen_type", "room_type",
                                  "ascension_level", "class", "act_boss", "relics", "potions", "screen_state")}
    out["deck"] = cards(gs.get("deck"))
    if combat:
        out["combat"] = {
            "turn": combat.get("turn"),
            "player": combat.get("player"),
            "monsters": combat.get("monsters"),
            "hand": cards(combat.get("hand")),
            "draw": len(combat.get("draw_pile") or []),
            "discard": len(combat.get("discard_pile") or []),
            "exhaust": len(combat.get("exhaust_pile") or []),
        }
    return out


def detail(run_id):
    run_dir = RUNS / run_id
    if not (run_dir / "run.jsonl").exists():
        return None
    mtime = log_mtime(run_dir)
    cached = _detail_cache.get(run_id)
    if cached and cached[0] == mtime:
        return cached[1]
    log = read_log(run_dir)
    states = [game_state(read_json(p)) for p in raw_files(run_dir)]
    timeline = [{"step": i + 1, "floor": gs.get("floor"), "act": gs.get("act"), "hp": gs.get("current_hp"),
                 "max_hp": gs.get("max_hp"), "gold": gs.get("gold"), "screen": gs.get("screen_type"),
                 "room": gs.get("room_type")} for i, gs in enumerate(states)]
    maps = {}
    for gs in states:
        if gs.get("map") and gs.get("act") not in maps:
            maps[gs.get("act")] = gs["map"]
    memory = read_json(run_dir / "memory.json")
    data = {"summary": summarize(run_dir), "log": log, "timeline": timeline, "maps": maps,
            "path": visited_path(log, states, maps), "memory": memory}
    _detail_cache[run_id] = (mtime, data)
    return data


def step_state(run_id, step):
    path = RUNS / run_id / "raw" / f"{step:05d}.json"
    message = read_json(path)
    return slim_state(game_state(message)) if message else None


def knowledge():
    lessons = read_json(RUNS / "lessons.json") or []
    guides = []
    for path in sorted((ROOT / "guides").glob("*.md")):
        guides.append({"topic": path.stem, "text": path.read_text(encoding="utf-8")})
    patches = []
    for path in sorted(RUNS.glob("eval*/*.patch")):
        # PowerShell's ">" writes UTF-16, Out-File -Encoding utf8 writes UTF-8 with a BOM.
        raw = path.read_bytes()
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = raw.decode("utf-16")
        else:
            text = raw.decode("utf-8-sig", errors="replace")
        patches.append({"name": f"{path.parent.name}/{path.name}", "text": text})
    docs = {}
    for name in ("eval-baseline.md",):
        path = ROOT / "docs" / name
        if path.exists():
            docs[name] = path.read_text(encoding="utf-8")
    return {"lessons": lessons, "guides": guides, "patches": patches, "docs": docs}


def catalog():
    out = {}
    for name in ("cards", "relics", "potions"):
        out[name] = read_json(ROOT / "catalog" / f"{name}.json") or {}
    return out


def live():
    dirs = run_dirs()
    if not dirs:
        return {"run": None}
    newest = max(dirs, key=log_mtime)
    log = read_log(newest)
    return {"run": newest.name, "steps": len(log), "mtime": log_mtime(newest), "recent": log[-12:]}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not path.is_file() or STATIC not in path.resolve().parents:
            self.send_error(404)
            return
        body = path.read_bytes()
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind.endswith("javascript"):
            kind += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
        if not parts:
            return self.send_file(STATIC / "index.html")
        if parts[0] == "static":
            return self.send_file(STATIC.joinpath(*parts[1:]))
        if parts[0] != "api":
            return self.send_error(404)
        route = parts[1:]
        # Run ids are folder names; refuse anything that could leave runs/.
        if len(route) >= 2 and not re.fullmatch(r"[\w\-]+", route[1]):
            return self.send_json({"error": "bad run id"}, 400)
        if route == ["runs"]:
            return self.send_json([summarize(d) for d in run_dirs()])
        if len(route) == 2 and route[0] == "run":
            data = detail(route[1])
            return self.send_json(data) if data else self.send_json({"error": "no such run"}, 404)
        if len(route) == 4 and route[0] == "run" and route[2] == "step" and route[3].isdigit():
            data = step_state(route[1], int(route[3]))
            return self.send_json(data) if data else self.send_json({"error": "no such step"}, 404)
        if route == ["knowledge"]:
            return self.send_json(knowledge())
        if route == ["catalog"]:
            return self.send_json(catalog())
        if route == ["live"]:
            return self.send_json(live())
        return self.send_json({"error": "unknown endpoint"}, 404)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # 8765 is the game link's port (bridge/game_link.py).
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard: http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
