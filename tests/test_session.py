import json
import pathlib
import unittest

from bridge.session import ActionError, Session

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "smoke"


def load(n):
    return json.loads((FIXTURES / f"{n:04d}.json").read_text(encoding="utf-8"))


class ReplayLink:
    """Replays the recorded smoke run: each game command moves to the next recorded state."""

    def __init__(self, start):
        self.index = start
        self.sent = []

    def get(self):
        return load(self.index)

    def send(self, command):
        if command.startswith("wait"):
            return load(self.index)
        self.sent.append(command)
        self.index += 1
        return load(self.index)


class SessionTest(unittest.TestCase):
    def test_whole_turn_uses_fixed_letters(self):
        link = ReplayLink(6)
        session = Session(link)
        session.text()  # the LLM sees the hand before acting, which fixes the letters
        out = session.act("play a 0; play b 0; play c; end")
        self.assertEqual(link.sent, ["play 1 0", "play 1 0", "play 1", "end"])
        self.assertTrue(out.startswith("Done 4/4."))
        self.assertIn("Combat T2", out)

    def test_card_names_work_as_well_as_letters(self):
        link = ReplayLink(6)
        session = Session(link)
        session.act("play Strike 0")
        self.assertEqual(link.sent, ["play 1 0"])

    def test_bad_action_reports_error(self):
        session = Session(ReplayLink(6))
        out = session.act("play z")
        self.assertIn("ERR", out)

    def test_inspect_card(self):
        session = Session(ReplayLink(6))
        self.assertIn("Deal 10 damage. Apply 3 Vulnerable.", session.inspect("card Bash"))
        self.assertIn("Strike x5", session.inspect("deck"))


if __name__ == "__main__":
    unittest.main()


class MenuLink:
    """Main menu with a saved run."""

    def __init__(self):
        self.sent = []

    def get(self):
        return {"in_game": False, "ready_for_command": True, "available_commands": ["start", "continue", "state"]}

    def send(self, command):
        self.sent.append(command)
        return {"error": "stop here"}


class SavedRunTest(unittest.TestCase):
    def test_start_refuses_to_overwrite_saved_run(self):
        link = MenuLink()
        session = Session(link)
        with self.assertRaises(ActionError) as caught:
            session.start_run()
        self.assertIn("continue_run", str(caught.exception))
        self.assertEqual(link.sent, [])

    def test_continue_sends_continue(self):
        link = MenuLink()
        with self.assertRaises(ActionError):
            Session(link).continue_run()
        self.assertEqual(link.sent, ["continue"])
