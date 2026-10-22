"""Probe for the modified CommunicationMod.

Set this script as CommunicationMod's external command. It never sends game
commands: you play by hand, and it saves every state the mod sends to
runs/probe/<timestamp>/NNNN.json so we can check the exported fields.
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "probe" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # CommunicationMod waits for "ready" before it starts sending states.
    print("ready", flush=True)
    for n, line in enumerate(sys.stdin):
        line = line.strip()
        if not line:
            continue
        try:
            state = json.loads(line)
        except json.JSONDecodeError:
            (OUT / f"{n:04d}.txt").write_text(line, encoding="utf-8")
            continue
        (OUT / f"{n:04d}.json").write_text(json.dumps(state, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
