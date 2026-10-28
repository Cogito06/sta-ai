import json
import pathlib
import unittest

from bridge.render import Renderer

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "smoke"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class RenderTest(unittest.TestCase):
    def test_every_recorded_state_renders(self):
        renderer = Renderer()
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(state=path.name):
                text = renderer.render(json.loads(path.read_text(encoding="utf-8")))
                self.assertTrue(text)

    def test_hand_letters_stay_fixed_within_a_turn(self):
        renderer = Renderer()
        before = renderer.render(load("0007"))
        after = renderer.render(load("0008"))
        self.assertIn(" c Bash 2", before)
        self.assertIn(" c Bash 2", after)
        self.assertNotIn(" a Strike", after)

    def test_card_text_is_shown_once_then_numbers_only(self):
        renderer = Renderer()
        self.assertIn("Deal 8 damage. Apply 2 Vulnerable.", renderer.render(load("0007")))
        self.assertNotIn("Apply 2 Vulnerable", renderer.render(load("0008")))

    def test_draw_pile_is_count_only(self):
        renderer = Renderer()
        text = renderer.render(load("0006"))
        self.assertIn("Draw 6 |", text)
        self.assertNotIn("draw_pile", text)

    def test_intent_waits_for_the_game(self):
        text = Renderer().render(load("0006"))
        self.assertIn("intent (not shown yet)", text)

    def test_map_lists_next_nodes_in_choice_order(self):
        text = Renderer().render(load("0005"))
        self.assertIn("Next (choose <n> or choose x<column>): 0 M(x1)  1 M(x3)  2 M(x4)", text)



class HandOrderTest(unittest.TestCase):
    def test_hand_is_listed_in_letter_order(self):
        from tests.states import card, combat_message, monster
        r = Renderer()
        first = combat_message([card("Strike_R", uuid="s"), card("Defend_R", uuid="d")], [monster("Cultist", 50)])
        r.render(first)
        # Strike was played, two new cards came in and the game put one before Defend.
        later = combat_message([card("Bash", uuid="b", cost=2), card("Defend_R", uuid="d"), card("Inflame", uuid="i")],
                               [monster("Cultist", 50)])
        text = r.render(later)
        hand = [line.strip()[:1] for line in text.split("Hand (3/10):")[1].splitlines()[1:4]]
        self.assertEqual(hand, ["b", "c", "d"])


class CardFaceTest(unittest.TestCase):
    def test_reward_cards_without_computed_values_use_the_catalog(self):
        card = {"id": "Heavy Blade", "upgrades": 0, "cost": 2, "damage": -1, "magic_number": 3, "uuid": "x"}
        self.assertEqual(Renderer().card_face(card), "Deal 14 damage. Strength affects this card 3 times.")


if __name__ == "__main__":
    unittest.main()
