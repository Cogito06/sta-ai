"""Manual end-to-end check without Claude: start a seeded run and play a few actions.

Needs the game running with CommunicationMod's command set to bridge/game_link.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from bridge.session import LinkClient, Session  # noqa: E402

session = Session(LinkClient())
print(session.get_state(), "\n" + "=" * 60)
if session.message.get("in_game"):
    sys.exit("A run is already in progress; abandon it or use the main menu first.")
print(session.start_run("SMOKE2"), "\n" + "=" * 60)
for actions in sys.argv[1:] or ["choose 0", "choose 0", "choose 0"]:
    print(f">>> {actions}")
    print(session.act(actions), "\n" + "=" * 60)
