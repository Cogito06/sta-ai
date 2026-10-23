"""Real-game checks for specific situations, set up with BaseMod's dev console.

Run with the game open (CommunicationMod -> bridge/game_link.py):
    python -m bridge.scenarios [name ...]
Each scenario starts a fresh run (this overwrites any saved run), jumps straight to the
situation with `dev` commands, plays it through Session like the LLM would, and checks the
result. `dev` is only used here; the LLM's tools never send it.
"""
import sys
import time

from bridge.session import LinkClient, Session, combat_of, game_state


class Check:
    def __init__(self, name):
        self.name, self.failures, self.log = name, [], []

    def expect(self, ok, what):
        self.log.append(("ok  " if ok else "FAIL") + " " + what)
        if not ok:
            self.failures.append(what)


def dev(session, command):
    reply = session.link.send(f"dev {command}")
    if "error" in reply:
        raise RuntimeError(f"dev {command}: {reply['error']}")
    session.message = reply
    session.wait_for_intents()
    return reply


def end_open_run(session):
    """A scenario that failed midway leaves its run open; die and go back to the main menu."""
    session.message = session.link.get()
    if not session.message.get("in_game"):
        return
    if not combat_of(session.message):
        dev(session, "fight Cultist")
    session.link.send("dev kill self")
    for _ in range(30):
        msg = session.link.send("wait 60")
        if not msg.get("in_game"):
            break
        if "proceed" in msg.get("available_commands", []):
            session.link.send("proceed")
    session.message = session.link.get()
    if session.message.get("in_game"):
        raise RuntimeError("could not end the open run")


def fresh_run(session):
    end_open_run(session)
    session.start_run("SCENARIO1", overwrite=True)
    for _ in range(10):
        if game_state(session.message).get("screen_type") != "EVENT":
            break
        # Neow: take the first option on each page to get into the dungeon.
        session.act("choose 0")


def deck_size(session):
    return len(game_state(session.message).get("deck", []))


def duplicator(session, check):
    fresh_run(session)
    dev(session, "event Duplicator")
    before = deck_size(session)
    out = session.act("choose 0")
    check.expect(game_state(session.message).get("screen_type") == "GRID", "praying opens the card grid")
    out = session.act("choose 0")
    check.log.append(out.splitlines()[0])
    check.expect(deck_size(session) == before + 1, f"deck grew by one ({before} -> {deck_size(session)})")


def golden_idol(session, check):
    fresh_run(session)
    dev(session, "event Golden Idol")
    out = session.act("choose 0")
    check.expect("New relic: Golden Idol" in out, "taking the idol names the new relic")


def awakened_one(session, check):
    fresh_run(session)
    dev(session, "fight Awakened One")
    dev(session, "power Strength 400")
    dev(session, "hand add Strike_R")
    out = session.act("play Strike 0")
    monster = combat_of(session.message)["monsters"][0] if combat_of(session.message) else {}
    check.log.append(out.splitlines()[0])
    check.expect("combat won" not in out, "phase one kill is not reported as a win")
    check.expect(bool(monster.get("half_dead")) or "reviving" in out, "Awakened One shows as reviving")
    dev(session, "kill all")


def deck_view(session, check):
    fresh_run(session)
    dev(session, "fight Cultist")
    session.link.send("key DECK")
    session.message = session.link.get()
    check.expect(game_state(session.message).get("screen_name") == "MASTER_DECK_VIEW", "the deck view is open")
    out = session.act("end")
    check.expect("Closed the master deck view" in out, "the bridge closed it before acting")
    check.expect(not session.overlay_open(), "no view is left open")
    dev(session, "kill all")


SCENARIOS = {"duplicator": duplicator, "golden_idol": golden_idol, "awakened_one": awakened_one, "deck_view": deck_view}


def main(names):
    session = Session(LinkClient())
    failed = 0
    for name in names or SCENARIOS:
        check = Check(name)
        try:
            SCENARIOS[name](session, check)
        except Exception as e:  # report and go on to the next scenario
            check.expect(False, f"crashed: {e!r}")
        failed += bool(check.failures)
        print(f"== {name}: {'FAIL' if check.failures else 'ok'}")
        for line in check.log:
            print("   " + line)
        time.sleep(1)
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
