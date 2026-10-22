"""Smoke test for the modified CommunicationMod.

Starts an Ironclad A0 run with a fixed seed and plays very simply (first
playable card on the first living enemy, otherwise end turn; first option on
other screens) until the first combat is won. Every state is saved to
runs/smoke/<timestamp>/NNNN.json, and every command to commands.log.
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "smoke" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
SEED = "SMOKE1"
MAX_STEPS = 300


def pick_command(msg):
    cmds = msg.get("available_commands", [])
    if not msg.get("in_game"):
        return f"start ironclad 0 {SEED}" if "start" in cmds else None
    gs = msg["game_state"]
    combat = gs.get("combat_state")
    if combat and "play" in cmds:
        targets = [i for i, m in enumerate(combat["monsters"]) if not m["is_gone"]]
        for i, card in enumerate(combat["hand"], start=1):
            if card.get("is_playable"):
                if card["has_target"]:
                    return f"play {i} {targets[0]}" if targets else None
                return f"play {i}"
    if "end" in cmds:
        return "end"
    if "choose" in cmds and gs.get("choice_list"):
        return "choose 0"
    for c in ("proceed", "confirm", "skip", "leave", "cancel", "return"):
        if c in cmds:
            return c
    return "state"


def main():
    # The modified CommunicationMod always sends UTF-8.
    sys.stdin.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    log = open(OUT / "commands.log", "w", encoding="utf-8")
    print("ready", flush=True)
    won_first_combat = False
    for n, line in enumerate(sys.stdin):
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        (OUT / f"{n:04d}.json").write_text(json.dumps(msg, indent=1), encoding="utf-8")
        if n >= MAX_STEPS or won_first_combat:
            continue
        gs = msg.get("game_state", {})
        if gs.get("screen_type") == "COMBAT_REWARD":
            won_first_combat = True
            log.write(f"{n}: first combat won, stopping\n")
            log.flush()
            continue
        if not msg.get("ready_for_command"):
            continue
        cmd = pick_command(msg)
        if cmd:
            log.write(f"{n}: {cmd}\n")
            log.flush()
            print(cmd, flush=True)


if __name__ == "__main__":
    main()
