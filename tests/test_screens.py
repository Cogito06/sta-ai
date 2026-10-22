"""Rendering of made-up states for every screen and for combat edge cases."""
import unittest

from bridge.render import Renderer
from tests.states import card, combat_message, message, monster, potion, power


def render(msg, renderer=None):
    return (renderer or Renderer()).render(msg)


class ScreenTest(unittest.TestCase):
    def test_event_shows_body_options_and_disabled(self):
        msg = message("EVENT", {"event_name": "Big Fish", "body_text": "You find a fish.", "options": [
            {"text": "[Banana] Heal 26 HP.", "label": "Banana", "disabled": False, "choice_index": 0},
            {"text": "[Locked] Requires 100 gold.", "label": "Locked", "disabled": True},
            {"text": "[Box] Obtain a Relic. Become Cursed: Regret.", "label": "Box", "disabled": False, "choice_index": 1}]},
            commands=("choose", "state"), choices=["banana", "box"])
        text = render(msg)
        self.assertIn("== Event: Big Fish ==", text)
        self.assertIn("You find a fish.", text)
        self.assertIn(" 0 [Banana] Heal 26 HP.", text)
        self.assertIn(" - [Locked] Requires 100 gold. [disabled]", text)
        self.assertIn(" 1 [Box]", text)

    def test_shop_indexes_match_choice_list(self):
        cards = [dict(card("Inflame", cost=1), price=150), dict(card("Carnage", cost=2), price=80)]
        relics = [dict({"id": "Vajra", "name": "Vajra", "counter": -1}, price=140)]
        potions = [dict(potion("Fire Potion", target=True), price=50), dict(potion("Fire Potion", target=True), price=52)]
        # purge (75) and Inflame (150) affordable with 150 gold; Vajra too; both potions
        choices = ["purge", "inflame", "carnage", "vajra", "fire potion", "fire potion"]
        msg = message("SHOP_SCREEN", {"cards": cards, "relics": relics, "potions": potions, "purge_available": True,
                                      "purge_cost": 75}, commands=("choose", "leave", "state"), choices=choices)
        text = render(msg)
        self.assertIn(" 1 [150g] Inflame", text)
        self.assertIn(" 2 [80g] Carnage", text)
        self.assertIn(" 3 [140g] Vajra", text)
        self.assertIn(" 4 [50g] Fire Potion", text)
        self.assertIn(" 5 [52g] Fire Potion", text)
        self.assertIn(" 0 [75g] Remove a card", text)

    def test_shop_marks_unaffordable_items(self):
        cards = [dict(card("Inflame", cost=1), price=150), dict(card("Anger", cost=0), price=45)]
        msg = message("SHOP_SCREEN", {"cards": cards, "relics": [], "potions": [], "purge_available": True,
                                      "purge_cost": 75}, commands=("choose", "leave"), choices=["anger"], gold=60)
        text = render(msg)
        self.assertIn(" - [150g (can't afford)] Inflame", text)
        self.assertIn(" 0 [45g] Anger", text)
        self.assertIn(" - [75g (can't afford)] Remove a card", text)

    def test_shop_room_and_chest_show_their_options(self):
        text = render(message("SHOP_ROOM", {}, commands=("choose", "proceed"), choices=["shop"], room_type="ShopRoom"))
        self.assertIn("0 shop", text.lower())
        text = render(message("CHEST", {"chest_type": "SmallChest", "chest_open": False}, commands=("choose", "proceed"),
                              choices=["open"], room_type="TreasureRoom"))
        self.assertIn("0 open", text.lower())

    def test_rest_site_heal_amount(self):
        text = render(message("REST", {"has_rested": False, "rest_options": ["rest", "smith"]},
                              commands=("choose",), choices=["rest", "smith"], current_hp=50, max_hp=80))
        self.assertIn(" 0 Rest (heal 24)", text)
        self.assertIn(" 1 Smith", text)

    def test_rest_heal_is_capped_by_missing_hp(self):
        text = render(message("REST", {}, commands=("choose",), choices=["rest", "smith"], current_hp=75, max_hp=80))
        self.assertIn("Rest (heal 5)", text)

    def test_boss_relic(self):
        relics = [{"id": "Black Star", "name": "Black Star", "counter": -1},
                  {"id": "Coffee Dripper", "name": "Coffee Dripper", "counter": -1}]
        text = render(message("BOSS_REWARD", {"relics": relics}, commands=("choose", "skip"),
                              choices=["black star", "coffee dripper"]))
        self.assertIn(" 0 Black Star - ", text)
        self.assertIn(" 1 Coffee Dripper - ", text)

    def test_grid_upgrade(self):
        cards = [card("Strike_R"), card("Bash", cost=2)]
        text = render(message("GRID", {"cards": cards, "selected_cards": [], "num_cards": 1, "any_number": False,
                                       "for_upgrade": True, "for_transform": False, "for_purge": False,
                                       "confirm_up": False}, commands=("choose",), choices=["strike", "bash"]))
        self.assertIn("== Choose 1 card(s) to upgrade ==", text)
        self.assertIn(" 1 Bash 2", text)

    def test_grid_waiting_for_confirm_says_so(self):
        text = render(message("GRID", {"cards": [card("Strike_R")], "selected_cards": [card("Bash", cost=2)],
                                       "num_cards": 1, "any_number": False, "for_upgrade": False,
                                       "for_transform": False, "for_purge": True, "confirm_up": True},
                              commands=("confirm", "cancel"), choices=["strike"]))
        self.assertIn("Selected: Bash", text)
        self.assertIn("confirm", text.lower().split("selected")[1])

    def test_hand_select(self):
        hand = [card("Strike_R"), card("Defend_R", type="SKILL")]
        text = render(message("HAND_SELECT", {"hand": hand, "selected": [], "max_cards": 1, "can_pick_zero": False},
                              commands=("choose",), choices=["strike", "defend"],
                              combat=combat_message(hand, [monster("Cultist", 40)])["game_state"]["combat_state"]))
        self.assertIn("== Choose 1 card(s) from your hand ==", text)
        self.assertIn(" 1 Defend 1", text)

    def test_card_reward_with_singing_bowl(self):
        cards = [card("Pommel Strike", damage=-1, magic_number=-1), card("Shrug It Off", type="SKILL", block=-1, magic_number=-1)]
        text = render(message("CARD_REWARD", {"cards": cards, "bowl_available": True, "skip_available": True},
                              commands=("choose", "skip"), choices=["pommel strike", "shrug it off", "bowl"]))
        self.assertIn(" 0 Pommel Strike 1 - Deal 9 damage. Draw 1 card.", text)
        self.assertIn(" 1 Shrug It Off 1 - Gain 8 Block. Draw 1 card.", text)
        self.assertIn(" 2 Singing Bowl", text)

    def test_combat_reward_kinds(self):
        rewards = [{"reward_type": "GOLD", "gold": 25}, {"reward_type": "POTION", "potion": potion("Block Potion")},
                   {"reward_type": "RELIC", "relic": {"id": "Anchor", "name": "Anchor", "counter": -1}},
                   {"reward_type": "SAPPHIRE_KEY", "link": {"id": "Anchor", "name": "Anchor", "counter": -1}},
                   {"reward_type": "CARD"}]
        text = render(message("COMBAT_REWARD", {"rewards": rewards}, commands=("choose", "proceed")))
        self.assertIn(" 0 25 Gold", text)
        self.assertIn(" 1 Potion: Block Potion - Gain 12 Block.", text)
        self.assertIn(" 2 Relic: Anchor - Start each combat with 10 Block.", text)
        self.assertIn(" 3 Sapphire Key (instead of Anchor)", text)
        self.assertIn(" 4 Card reward", text)

    def test_map_with_boss_next(self):
        text = render(message("MAP", {"current_node": {"x": 3, "y": 14}, "next_nodes": [], "boss_available": True,
                                      "first_node_chosen": True}, commands=("choose",), choices=["boss"]))
        self.assertIn("Next: 0 Boss", text)

    def test_game_over(self):
        text = render(message("GAME_OVER", {"victory": False, "score": 123}, commands=("proceed",)))
        self.assertIn("DEFEAT", text)
        self.assertIn("Score 123", text)

    def test_main_menu(self):
        self.assertEqual(render({"in_game": False, "available_commands": ["start"]}), "Main menu.")

    def test_full_potion_slots_and_target_mark(self):
        msg = message("MAP", {"next_nodes": [], "boss_available": False}, potions=[
            potion("Fire Potion", target=True), potion("Block Potion"), potion("Strength Potion")])
        self.assertIn("Potions: 0 Fire Potion(T) 1 Block Potion 2 Strength Potion", render(msg))


class CombatEdgeTest(unittest.TestCase):
    def test_multi_hit_intent_and_monster_powers(self):
        msg = combat_message([card("Strike_R", damage=6)], [
            monster("Jaw Worm", 40, 44, intent="ATTACK_DEFEND", damage=7, block=6, powers=[power("Strength", 3)]),
            monster("Byrd", 25, intent="ATTACK", damage=1, hits=5, powers=[power("Flight", 3)])])
        text = render(msg)
        self.assertIn(" 0 Jaw Worm 40/44 Blk 6 | intent ATK 7+DEF | Strength 3", text)
        self.assertIn(" 1 Byrd 25/25 | intent ATK 1x5 | Flight 3", text)

    def test_dead_and_reviving_monsters(self):
        msg = combat_message([card("Strike_R", damage=6)], [
            monster("Darkling", 0, 48, gone=True), monster("Darkling", 0, 50, half_dead=True), monster("Darkling", 30, 52)])
        text = render(msg)
        self.assertIn(" 0 Darkling (dead)", text)
        self.assertIn(" 1 Darkling (reviving) 0/50", text)
        self.assertIn(" 2 Darkling 30/52", text)

    def test_x_cost_unplayable_and_status_cards(self):
        hand = [card("Whirlwind", cost=-1, damage=5), card("Wound", cost=-2, type="STATUS", playable=False),
                card("Clash", cost=0, damage=14, playable=False)]
        text = render(combat_message(hand, [monster("Cultist", 48, intent="BUFF")]))
        self.assertIn(" a Whirlwind X - ", text)
        self.assertIn(" b Wound - [can't play]", text)
        self.assertIn(" c Clash 0 [can't play]", text)

    def test_searing_blow_plus_n(self):
        text = render(combat_message([card("Searing Blow", cost=2, upgrades=3, damage=24)], [monster("Cultist", 48)]))
        self.assertIn("Searing Blow+3", text)

    def test_negative_strength_is_shown(self):
        text = render(combat_message([card("Strike_R", damage=5)], [monster("Cultist", 48)],
                                     powers=[power("Strength", -1), power("Vulnerable", 2)]))
        self.assertIn("Strength -1, Vulnerable 2", text)

    def test_ethereal_and_exhaust_flags(self):
        text = render(combat_message([card("Carnage", cost=2, damage=20, ethereal=True),
                                      card("True Grit", cost=1, block=7, exhausts=False)], [monster("Cultist", 48)]))
        self.assertIn("Carnage 2 [Ethereal]", text)

    def test_letters_continue_after_new_cards(self):
        renderer = Renderer()
        a, b = card("Strike_R", damage=6), card("Pommel Strike", damage=9, magic_number=1)
        render(combat_message([a, b], [monster("Cultist", 48)]), renderer)
        c = card("Bash", cost=2, damage=8, magic_number=2)
        text = render(combat_message([a, c], [monster("Cultist", 48)]), renderer)
        self.assertIn(" a Strike", text)
        self.assertIn(" c Bash", text)

    def test_letters_reset_next_turn(self):
        renderer = Renderer()
        render(combat_message([card("Strike_R", damage=6), card("Strike_R", damage=6)], [monster("Cultist", 48)]), renderer)
        text = render(combat_message([card("Bash", cost=2, damage=8, magic_number=2)], [monster("Cultist", 48)], turn=2), renderer)
        self.assertIn(" a Bash", text)

    def test_relic_counters_in_combat(self):
        msg = combat_message([card("Strike_R", damage=6)], [monster("Cultist", 48)],
                             relics=[{"id": "Pen Nib", "name": "Pen Nib", "counter": 9},
                                     {"id": "Burning Blood", "name": "Burning Blood", "counter": -1}])
        self.assertIn("Relic counters: Pen Nib (9)", render(msg))


if __name__ == "__main__":
    unittest.main()


class CardTextModeTest(unittest.TestCase):
    def test_full_text_again_in_the_next_combat(self):
        renderer = Renderer()
        fight = combat_message([card("Dropkick", damage=5)], [monster("Cultist", 48)])
        self.assertIn("Vulnerable", render(fight, renderer))
        self.assertNotIn("Vulnerable", render(fight, renderer))
        render(message("MAP", {"next_nodes": [], "boss_available": False}), renderer)
        self.assertIn("Vulnerable", render(fight, renderer))
